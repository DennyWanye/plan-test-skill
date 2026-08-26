#!/usr/bin/env python3
"""判档反查：堵"压根不建账本"这一列（hooks/README.md 能力矩阵里 Stop hook 与 pre-push
都如实标 ✗ 的那一列）。

Stop hook / pre-push 只在仓库里**已存在** gate 记账物时才生效——代理把改动判成 DIRECT
（或干脆不开账本）直接收尾，两者无感。唯一的堵法是反过来问：**这次改动面按项目自己的
声明属于高风险，账本在哪？**

  - 项目根 `.claude/plan-test-risk.globs` 声明高风险路径（一行一个 glob，# 注释）；
  - 输入 `git diff --name-only <base>...HEAD`（merge-base 语义，PR 场景的标准口径）；
  - 命中高风险 glob，却没有任何**新建/更新的 run 账本**（按内容形状识别，与 gate_scan.py
    同判据：同时含 schema_version / run_id / scenarios / integrity 四键的 JSON）→ 非零退出，
    列出命中文件与命中的 glob。

设计边界（如实声明）：
  - 没配 globs 文件的项目本检查是空转（exit 0）——glob 内容依赖项目结构，机制与规则分离；
  - 账本识别按形状不按名字（名字由被测者定，基于名字的识别被独立审计打穿过两次）；
  - 它只证明"高风险改动伴随了账本活动"，不证明账本闭环——闭环由 CI 里逐账本的
    `finalize --check-only` 负责，两个 step 缺一不可；
  - 把账本 gitignore 掉的仓库（账本证明当前 HEAD，提交即过期的布局）在 CI 的 diff 里
    永远看不到账本更新——这样的项目不要启用本检查，或在 CI 里换用工作区扫描。

用法：tier_check.py --base <ref> [--globs <path>] [--repo <dir>]
退出码：0 放行 / 1 高风险改动无账本 / 2 用法或环境错误。
"""

import argparse
import json
import os
import re
import subprocess
import sys

GLOBS_DEFAULT = ".claude/plan-test-risk.globs"
LEDGER_KEYS = ("schema_version", "run_id", "scenarios", "integrity")
MAX_BYTES = 8 * 1024 * 1024


def glob_to_regex(pat):
    """`**` 跨目录、`*`/`?` 不跨 `/`——与 gitignore/CI 常见语义一致。"""
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if c == "*":
            if pat[i:i + 3] == "**/":
                out.append(r"(?:[^/]+/)*")
                i += 3
                continue
            if pat[i:i + 2] == "**":
                out.append(r".*")
                i += 2
                continue
            out.append(r"[^/]*")
        elif c == "?":
            out.append(r"[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def load_globs(path):
    pats = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            pats.append((line, glob_to_regex(line)))
    return pats


def changed_files(repo, base):
    cmd = ["git", "-C", repo, "diff", "--name-only", f"{base}...HEAD"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"git diff 失败：{' '.join(cmd)}\n{out.stderr.strip()}")
    return [l for l in out.stdout.splitlines() if l.strip()]


def is_ledger(repo, rel):
    """与 gate_scan.py 同判据：四键形状。文件不在工作树（如被删）不算账本活动。"""
    if not rel.endswith(".json"):
        return False
    path = os.path.join(repo, rel)
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return False
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and all(k in obj for k in LEDGER_KEYS)


def main(argv=None):
    ap = argparse.ArgumentParser(description="高风险改动面反查 run 账本")
    ap.add_argument("--base", required=True, help="对比基准 ref（PR base 或主干）")
    ap.add_argument("--globs", default=None, help=f"glob 声明文件（缺省 <repo>/{GLOBS_DEFAULT}）")
    ap.add_argument("--repo", default=".", help="仓库根目录（缺省当前目录）")
    args = ap.parse_args(argv)

    globs_path = args.globs or os.path.join(args.repo, GLOBS_DEFAULT)
    if not os.path.isfile(globs_path):
        print(f"tier_check: 未找到 {globs_path}——本项目未声明高风险路径，跳过。")
        return 0

    pats = load_globs(globs_path)
    if not pats:
        print(f"tier_check: {globs_path} 没有有效 glob，跳过。")
        return 0

    try:
        changed = changed_files(args.repo, args.base)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        print(f"tier_check: {e}", file=sys.stderr)
        return 2

    hits = []
    for rel in changed:
        norm = rel.replace(os.sep, "/")
        for raw, rx in pats:
            if rx.match(norm):
                hits.append((norm, raw))
                break
    if not hits:
        print(f"tier_check: 改动 {len(changed)} 个文件，未命中高风险 glob，放行。")
        return 0

    ledgers = [rel for rel in changed if is_ledger(args.repo, rel)]
    if ledgers:
        print(f"tier_check: 命中高风险 glob {len(hits)} 处，且本次改动含 run 账本活动，放行：")
        for l in ledgers:
            print(f"  · 账本 {l}")
        return 0

    print("tier_check FAIL: 以下改动命中项目声明的高风险路径，但本次 diff 里没有任何"
          "新建/更新的 run 账本（按内容形状识别）：", file=sys.stderr)
    for norm, raw in hits:
        print(f"  · {norm}  ← {raw}", file=sys.stderr)
    print("高风险改动必须走 plan-test 流程并把账本提交进同一批改动；"
          "确属误报请调整 .claude/plan-test-risk.globs（改 glob 本身会留在 diff 里）。",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
