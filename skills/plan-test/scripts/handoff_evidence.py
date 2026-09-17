#!/usr/bin/env python3
"""交接证据提取：从 Claude Code 会话原始记录里列出交接前做过的真实操作。

为什么要有它（2026-09-15 回放实测）：评估员看到的"我已经点测过了"是主 agent 自述，
而 e2 那次自述"品牌池页面和认领弹窗每一步都通过"，原始记录里真实点击是 0 次、
JS 驱动 22 次。证据由被评者组装 = 评估失真的根因，本脚本是唯一不经他手的事实源。

输出给评估员用：每步一个 S<n>，标明动作类别与是否真的执行成功（ok / error / 未执行）。
"""
import argparse
import glob
import json
import os
import re
import sys

# 真实交互：人手能做的动作
REAL_COMPUTER = {"left_click", "right_click", "double_click", "triple_click", "type", "key",
                 "left_click_drag", "scroll", "hover", "click", "drag", "menu"}
REAL_IOS = {"tap", "swipe", "text", "button", "touch_path", "touch2_path"}
REAL_TOOLS = {"app_click", "app_type", "app_key", "app_drag", "app_scroll", "app_menu",
              "file_upload", "upload_image", "shortcuts_execute"}
OBSERVE = {"screenshot", "zoom", "wait", "scroll_to", "inspect", "attach", "detach", "launch",
           "find", "read_page", "get_page_text", "read_console_messages", "read_network_requests",
           "tabs_context", "tabs_context_mcp", "tabs_create", "tabs_create_mcp", "tabs_close",
           "tabs_close_mcp", "tabs_select", "resize_window", "preview_start", "preview_stop",
           "preview_list", "preview_logs", "app_screenshot", "app_ax_find", "app_list_windows",
           "list_apps", "list_granted_applications", "request_access", "open_application"}
UI_FAMILY = re.compile(r"^mcp__(Claude_Browser|claude-in-chrome|computer-use|"
                       r"Claude_Code_iOS_Simulator|playwright|puppeteer)")
CODE_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
LOOKUP_TOOLS = {"Read", "Grep", "Glob", "WebFetch", "WebSearch"}
BATCH = {"browser_batch", "app_batch", "computer_batch", "teach_batch"}

JS_DRIVE = re.compile(r"""\.click\s*\(|dispatchEvent\s*\(|new\s+(Mouse|Keyboard|Input|Pointer|Submit|Change)Event|
    \$wire\.(set|call|\$set|\$call|dispatch|upload)\b|\$wire\.\w+\s*=(?!=)|Livewire\.(dispatch|emit)|
    \.(value|checked|selected|selectedIndex|innerHTML|innerText|textContent)\s*=(?!=)|
    (requestSubmit|submit)\s*\(|mountAction|callMountedAction|
    (localStorage|sessionStorage)\.(setItem|removeItem|clear)|document\.cookie\s*=(?!=)|
    location\.(href\s*=(?!=)|assign|replace|reload)|history\.(push|replace)State""", re.X)
JS_NET = re.compile(r"\bfetch\s*\(|XMLHttpRequest|\baxios\.|\$\.(ajax|post|get)\b")
JS_NET_WRITE = re.compile(r"""method\s*:\s*['"`](POST|PUT|PATCH|DELETE)|axios\.(post|put|patch|delete)|\$\.post""", re.I)
BASH_DRIVER = re.compile(r"playwright|puppeteer|selenium|cypress|xdotool|cliclick|"
                         r"osascript[^\n]*click|artisan\s+tinker|curl[^\n]*(-X\s*(POST|PUT|PATCH|DELETE)|--data|\s-d\s)", re.I)
HEREDOC_BODY = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1\b", re.S)
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")
ENV_PREFIX = re.compile(r"^\s*(\w+=\S*\s+)*")
READ_ONLY_HEAD = re.compile(r"(echo|printf|wc|cd|export|true|sort|uniq|cut|tr|jq|diff|shasum)\b")


def is_read_segment(seg):
    seg = seg.strip()
    if re.fullmatch(r"\w+=\S*", seg):
        return True  # 只是给变量赋值
    seg = ENV_PREFIX.sub("", seg)
    return bool(READ_LOOKUP.match(seg) or READ_ONLY_HEAD.match(seg) or re.match(r"(psql|mysql)\b", seg))


GIT_COMMIT = re.compile(r"\bgit\s+(commit|merge|rebase|revert|cherry-pick)\b")
READ_LOOKUP = re.compile(r"\b(grep|rg|cat|head|tail|sed -n|awk|find|ls|git (log|show|blame|diff|status))\b|SELECT\s|artisan\s+(tinker|route:list)|psql|mysql", re.I)
HANDOFF_LINE = re.compile(r"交接评估[：:]\s*(PASS|FAIL|DISPUTED|文字类已改)")
EVALUATOR_DISPATCH = re.compile(r"test-result-evaluator|测试结果评估员")


# 窗口起点比记录起点早几秒是调用方取整造成的，不是证据缺失；超过这个容差才告警。
START_GAP_TOLERANCE_S = 120


def gap_seconds(a, b):
    from datetime import datetime

    def parse(x):
        x = x.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(x)
        except ValueError:
            return datetime.fromisoformat(x[:19] + "+00:00")

    try:
        return abs((parse(b) - parse(a)).total_seconds())
    except Exception:
        return 10 ** 9


def classify_js(code):
    if JS_DRIVE.search(code):
        return "JS驱动"
    if JS_NET.search(code):
        return "JS接口写" if JS_NET_WRITE.search(code) else "JS接口读"
    return "JS读取"


def leaf(name, inp):
    """把一次 tool_use 拆成 [(类别, 动作, 摘要)]；批量调用展开。"""
    short = name.rsplit("__", 1)[-1] if "__" in name else name
    inp = inp if isinstance(inp, dict) else {}
    if short in BATCH:
        out = []
        for a in inp.get("actions") or []:
            if not isinstance(a, dict):
                continue
            if "name" in a:                       # 内置 Browser / chrome 批量：带 name
                out += leaf(a.get("name", ""), a.get("input") or {})
            else:                                  # computer-use 批量：只有 action 键
                out += leaf("computer", a)
        return out
    if short in ("computer", "control"):
        act = inp.get("action", "")
        if act in REAL_COMPUTER or act in REAL_IOS:
            return [("真实交互", act, str(inp.get("text") or inp.get("coordinate") or "")[:60])]
        return [("观察", act or short, "")]
    if short == "form_input":
        return [("表单直填", "form_input", str(inp.get("value"))[:60])]
    if short == "javascript_tool":
        code = inp.get("text", "") or ""
        return [(classify_js(code), "javascript_tool", code[:80].replace("\n", " "))]
    if short == "navigate":
        return [("导航", "navigate", str(inp.get("url"))[:60])]
    if short in REAL_TOOLS:
        return [("真实交互", short, "")]
    if short in OBSERVE:
        return [("观察", short, "")]
    if short == "Bash":
        full = inp.get("command") or ""
        cmd = full[:120].replace("\n", " ")
        if GIT_COMMIT.search(full):
            return [("代码改动", "git", cmd)]
        if BASH_DRIVER.search(full):
            return [("脚本自动化(Bash)", "bash", cmd)]
        segs = [x for x in SEGMENT_SPLIT.split(HEREDOC_BODY.sub("", full)) if x.strip()]
        if segs and all(is_read_segment(x) for x in segs):
            # 读代码/查记录也是"断言有没有来源"的证据：不列出来，评估员会把
            # "读过代码才写下的结论"误判成无来源（2026-09-16 留出集 2 核查实测）。
            return [("来源线索", "bash", cmd)]
        # 命令行工具的交付，终端里跑用户会敲的命令就是真实操作，评估员要能引用步骤号
        return [("命令运行", "bash", cmd)] if segs else []
    if short in CODE_EDIT_TOOLS:
        return [("代码改动", short, str(inp.get("file_path") or "")[-60:])]
    if short in LOOKUP_TOOLS:
        return [("来源线索", short, str(inp.get("file_path") or inp.get("pattern") or inp.get("query") or "")[-60:])]
    return []


def iter_records(path):
    bad = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                bad += 1
                if bad > 50:
                    raise ValueError("记录格式无法解析：%s" % path)


def session_files(session_id, root):
    root = os.path.expanduser(root)
    main = glob.glob(os.path.join(root, "*", session_id + ".jsonl"))
    files = [(p, "main") for p in main]
    for p in main:
        sub = os.path.join(os.path.dirname(p), session_id, "subagents", "*.jsonl")
        files += [(q, "subagent:" + os.path.basename(q)[:-6]) for q in sorted(glob.glob(sub))]
    return files


def first_real_ts(path):
    """会话记录起点 = 第一条 user/assistant 记录；队列/系统类记录不算（否则误报窗口越界）。"""
    for d in iter_records(path):
        if d.get("type") in ("user", "assistant") and d.get("timestamp"):
            return d["timestamp"]
    return None


def collect(session_id, root, since, until, include_subagents=True):
    files = session_files(session_id, root)
    if not files:
        raise SystemExit("找不到会话记录：session_id=%s root=%s" % (session_id, root))
    steps, warnings, seen_uuid = [], [], set()
    starts = []
    for path, role in files:
        if role != "main" and not include_subagents:
            continue
        ts0 = first_real_ts(path)
        if ts0:
            starts.append(ts0)
        pending = {}
        for d in iter_records(path):
            uid = d.get("uuid")
            if uid and uid in seen_uuid:
                continue
            if uid:
                seen_uuid.add(uid)
            ts = d.get("timestamp") or ""
            msg = d.get("message") or {}
            content = msg.get("content")
            if d.get("type") == "assistant" and isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        name = b.get("name", "")
                        # SendMessage 续用同一个评估员做重评，也算评估员调用
                        if name in ("Agent", "Task", "SendMessage") and EVALUATOR_DISPATCH.search(
                                json.dumps(b.get("input") or {}, ensure_ascii=False)):
                            steps.append({"ts": ts, "role": role, "cls": "评估员调用", "act": name,
                                          "detail": "test-result-evaluator", "status": "ok"})
                            continue
                        if not (UI_FAMILY.search(name) or name in CODE_EDIT_TOOLS
                                or name in LOOKUP_TOOLS or name == "Bash"):
                            continue
                        for cls, act, detail in leaf(name, b.get("input") or {}):
                            pending.setdefault(b.get("id"), []).append(
                                {"ts": ts, "role": role, "cls": cls, "act": act,
                                 "detail": detail, "status": "未执行"})
                    elif b.get("type") == "text" and HANDOFF_LINE.search(b.get("text") or ""):
                        steps.append({"ts": ts, "role": role, "cls": "交接固定行", "act": "message",
                                      "detail": HANDOFF_LINE.search(b["text"]).group(0), "status": "ok"})
            elif d.get("type") == "user" and isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        for rec in pending.pop(b.get("tool_use_id"), []):
                            text = b.get("content")
                            text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
                            rec["status"] = "error" if (b.get("is_error") or "failed" in text[:200]) else "ok"
                            steps.append(rec)
        for left in pending.values():
            steps.extend(left)
    if starts:
        earliest = min(starts)
        if since and since < earliest and gap_seconds(since, earliest) > START_GAP_TOLERANCE_S:
            warnings.append("窗口起点 %s 早于会话记录起点 %s：更早的操作可能在续接前的其它会话文件里" % (since, earliest))
    steps = [s for s in steps if (not since or s["ts"] >= since) and (not until or s["ts"] <= until)]
    steps.sort(key=lambda s: s["ts"])
    for i, s in enumerate(steps, 1):
        s["step"] = "S%d" % i
    return steps, warnings, files


def audit(steps):
    """交接评估核对：主会话每条交接固定行前面应能找到评估员调用。

    评估员自己的输出里也会引用固定行（如"发送时末行写 交接评估：PASS"），
    只看主会话，否则会吃掉那次评估员调用、把随后真正的交接误报为没评估。
    """
    issues, last_eval = [], None
    for s in steps:
        if s["cls"] == "评估员调用":
            last_eval = s["step"]
        elif s["cls"] == "交接固定行" and s["role"] == "main":
            if last_eval is None:
                issues.append("%s 交接固定行（%s）之前没有评估员调用" % (s["step"], s["detail"]))
            last_eval = None
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(description="提取交接前的真实操作证据")
    ap.add_argument("--session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--root", default="~/.claude/projects")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--no-subagents", action="store_true")
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args(argv)
    if not args.session_id:
        raise SystemExit("缺少 --session-id，且环境变量 CLAUDE_CODE_SESSION_ID 为空")
    try:
        steps, warnings, files = collect(args.session_id, args.root, args.since, args.until,
                                         not args.no_subagents)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    summary = {}
    for s in steps:
        key = s["cls"] + ("" if s["cls"] in ("交接固定行", "评估员调用") else "/" + s["status"])
        summary[key] = summary.get(key, 0) + 1
    out = {
        "files": [{"path": p, "role": r} for p, r in files],
        "window": {"since": args.since, "until": args.until},
        "summary": summary,
        "交接评估核对": audit(steps),
        "warnings": warnings,
    }
    if not args.summary_only:
        out["steps"] = steps
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
