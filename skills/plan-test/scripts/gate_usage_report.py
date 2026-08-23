#!/usr/bin/env python3
"""统计真实 run 中各 gate 诊断的触发频率，为定期合并、降级或退休门禁提供事实。

扫描 tracked、普通 untracked 和被 ignore 的 plans 下账本；对每本执行
``finalize --check-only``。fixture 与随时间自然失效的诊断单独统计。
"""

import argparse
import json
import os
import re
import subprocess
import sys


STALE_CODES = {
    "TESTED_RUNTIME_MISMATCH", "RETEST_REQUIRED_AFTER_CHANGE", "RECEIPT_STALE",
    "AUDITOR_INPUT_STALE", "EVIDENCE_PREDATES_LEDGER", "TIMING_MISSING",
    "TIMING_GAP", "PHASE_UNPAIRED",
}
DIAG_RE = re.compile(r"^(DIAG|ADVISORY) ([A-Z][A-Z0-9_]*):")


def git_ls(repo, args):
    try:
        result = subprocess.run(["git", "ls-files"] + args, cwd=repo,
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def find_ledgers(repo):
    """返回去重后的 tracked/untracked/ignored plan-test 账本相对路径。"""
    found = set()
    for args in (["-c", "-o", "--exclude-standard"],
                 ["-o", "-i", "--exclude-standard", "--", "plans/"]):
        found.update(path for path in git_ls(repo, args)
                     if path.endswith("plan-test-run.json"))
    return sorted(found)


def parse_diagnostics(output):
    parsed = []
    for line in (output or "").splitlines():
        match = DIAG_RE.match(line.strip())
        if match:
            parsed.append((match.group(1), match.group(2)))
    return parsed


def check_one(repo, relative_path):
    gate = os.path.join(os.path.dirname(os.path.realpath(__file__)), "plan_test_gate.py")
    run_dir = os.path.join(repo, os.path.dirname(relative_path))
    try:
        result = subprocess.run([sys.executable, gate, "finalize", "--run-dir", run_dir,
                                 "--check-only"], cwd=repo, capture_output=True, text=True,
                                timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [("DIAG", "USAGE_REPORT_EXECUTION_FAILED")], str(exc)
    return parse_diagnostics(result.stdout), None


def increment(bucket, severity, code):
    counts = bucket.setdefault(code, {"error": 0, "advisory": 0})
    counts["error" if severity == "DIAG" else "advisory"] += 1


def print_bucket(title, bucket, ledger_count):
    print("\n## %s（%d 个账本）" % (title, ledger_count))
    if not bucket:
        print("  （无）")
        return
    for code in sorted(bucket):
        counts = bucket[code]
        print("  %-36s error=%d advisory=%d" %
              (code, counts["error"], counts["advisory"]))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", default=".")
    args = parser.parse_args(argv)
    repo = os.path.abspath(args.repo_dir)
    ledgers = find_ledgers(repo)
    if not ledgers:
        print("未找到 plan-test-run.json 账本。")
        return 0

    real, fixture, stale = {}, {}, {}
    real_count = fixture_count = skipped = 0
    for relative_path in ledgers:
        try:
            with open(os.path.join(repo, relative_path), encoding="utf-8") as handle:
                is_fixture = bool(json.load(handle).get("fixture_only"))
        except (OSError, ValueError):
            skipped += 1
            continue
        fixture_count += int(is_fixture)
        real_count += int(not is_fixture)
        diagnostics, error = check_one(repo, relative_path)
        if error:
            skipped += 1
        for severity, code in diagnostics:
            bucket = stale if code in STALE_CODES else (fixture if is_fixture else real)
            increment(bucket, severity, code)

    print_bucket("真实 run（退休评审的主要依据）", real, real_count)
    print_bucket("fixture-only run", fixture, fixture_count)
    print_bucket("时效性诊断（评审时单独看）", stale, real_count + fixture_count)
    if skipped:
        print("\n跳过或执行失败：%d 本账" % skipped)
    print("\n候选规则：真实 run 从未触发、只在 fixture 触发的门，优先评估合并/降级/删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
