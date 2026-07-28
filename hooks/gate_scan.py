#!/usr/bin/env python3
"""扫描工作区里的 gate 记账物——**按内容形状识别，不靠文件名，也不靠目录名**。

为什么不靠名字（两轮独立审计各打穿一次）：
  - 第八轮：hook 只扫 `*/verification/*`，把 run-dir 放到 `plans/run-x/` 就整体绕过唯一强制点；
  - 第九轮：改成按文件名 `plan-test-run.json` 找，把账本改名为 `ledger.archived.json` 又绕过
    ——本仓当时的"归档"方案自己就是这条逃逸的一个实例。

名字由被测者定，任何基于名字的识别都会输。账本的**形状**是它无法在保持可用的前提下改变的：
同时含 schema_version / run_id / scenarios / integrity 四个键的 JSON 就是账本。

用 `git ls-files -c -o --exclude-standard` 而不是 `find`：尊重 .gitignore（否则 .venv 里几百个
manifest.json 会把每次 Stop 拖到 7 秒以上，还会误报），且未跟踪但未忽略的新文件同样在列。

输出：两段，`LEDGERS` 与 `HALVES`，各自每行一个相对路径。
"""

import json
import os
import subprocess
import sys

MAX_BYTES = 8 * 1024 * 1024
LEDGER_KEYS = ("schema_version", "run_id", "scenarios", "integrity")
MANIFEST_MARKERS = ("applicability", "source_request_text", "source_request_file", "run_id")


def candidate_files():
    try:
        out = subprocess.run(["git", "ls-files", "-c", "-o", "--exclude-standard"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.splitlines() if p.endswith(".json")]


def load(rel):
    try:
        if os.path.getsize(rel) > MAX_BYTES:
            return None
        with open(rel, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def is_gate_manifest(obj):
    """gate manifest 的形状：scenarios 是带 scenario_id 的对象数组 + 一个 gate 专属键。

    按形状而非键名区分，BDD/测试清单那种字符串数组不会误报（第八轮审计实测过误报）。
    """
    sc = obj.get("scenarios")
    shaped = isinstance(sc, list) and len(sc) > 0 and all(
        isinstance(x, dict) and "scenario_id" in x for x in sc)
    return shaped and any(k in obj for k in MANIFEST_MARKERS)


def main():
    ledgers, halves = [], []
    for rel in candidate_files():
        norm = rel.replace(os.sep, "/")
        if "/fixtures/" in norm or norm.startswith("fixtures/"):
            continue
        obj = load(rel)
        if obj is None:
            continue
        if all(k in obj for k in LEDGER_KEYS):
            ledgers.append(norm)
        elif is_gate_manifest(obj):
            halves.append(norm)
    ledger_dirs = {os.path.dirname(x) for x in ledgers}
    print("LEDGERS")
    for x in sorted(ledgers):
        print(x)
    print("HALVES")
    for x in sorted(halves):
        if os.path.dirname(x) not in ledger_dirs:   # 同目录已有账本 = 正常 run，不算半截
            print(x)


if __name__ == "__main__":
    main()
