#!/usr/bin/env python3
"""读评估员返回的内容，判定主 agent 该怎么处置。

为什么要有它：评估员的 JSON 决定"能不能交"。它一旦截断、缺字段、夹带解说、重复 ID 或拒答，
"看起来没有 block"极易被当成 PASS 放行——这正是 LLM 输出驱动流程时最典型的失效。
本脚本把处置规则变成可复跑的判定，规则见 checklists/handoff.md「评估员输出异常时的处置」。
"""
import argparse
import json
import re
import sys

SEVERITY_RANK = {"block": 2, "note": 1}
REQUIRED = ("verdict", "findings")


def extract_json(text):
    """容忍前后解说：取出唯一的顶层 JSON 对象；取不到返回 None。"""
    try:
        return json.loads(text)
    except Exception:
        pass
    depth = start = 0
    candidates = []
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start:i + 1]
                try:
                    candidates.append(json.loads(chunk))
                except Exception:
                    pass
    return candidates[0] if len(candidates) == 1 else None


def dedupe(findings):
    """同 ID 重复 → 按最严留一条（block 优先于 note）。"""
    best = {}
    for f in findings:
        fid = f.get("id") or ""
        cur = best.get(fid)
        if cur is None or SEVERITY_RANK.get(f.get("severity"), 0) > SEVERITY_RANK.get(cur.get("severity"), 0):
            best[fid] = f
    return [best[k] for k in sorted(best)]


def judge(text):
    """返回 (处置, 理由, 归一化后的 finding 列表)。"""
    if not text or not text.strip():
        return "retry-then-blocked", "评估员回空", []
    if re.search(r"无法(完成|评估)|拒绝作答|I (can\s*not|cannot)", text) and extract_json(text) is None:
        return "retry-then-blocked", "评估员拒绝作答", []
    data = extract_json(text)
    if data is None:
        return "retry-then-blocked", "JSON 解析失败或不唯一（可能被截断）", []
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        return "retry-then-blocked", "缺必填字段：%s" % ",".join(missing), []
    findings = dedupe(data.get("findings") or [])
    blocks = [f for f in findings if f.get("severity") == "block"]
    bad_class = [f.get("id") for f in blocks if f.get("fix_class") not in ("硬伤", "文字")]
    if bad_class:
        return "retry-then-blocked", "block 缺 fix_class：%s" % ",".join(map(str, bad_class)), findings
    if not blocks:
        return "send", "无 block", findings
    if any(f.get("fix_class") == "硬伤" for f in blocks):
        return "fix-and-reeval", "有硬伤 block，需修好后重评", findings
    return "fix-and-send", "只有文字类 block，改完即可发", findings


def main(argv=None):
    ap = argparse.ArgumentParser(description="判定评估员输出该怎么处置")
    ap.add_argument("path", help="评估员输出文件；- 表示读标准输入")
    args = ap.parse_args(argv)
    text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8", errors="replace").read()
    action, reason, findings = judge(text)
    print(json.dumps({"action": action, "reason": reason,
                      "blocks": [f.get("id") for f in findings if f.get("severity") == "block"]},
                     ensure_ascii=False))
    return 0 if action in ("send", "fix-and-send", "fix-and-reeval") else 1


if __name__ == "__main__":
    sys.exit(main())
