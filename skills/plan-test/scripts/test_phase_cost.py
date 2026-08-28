#!/usr/bin/env python3
"""T6 遥测的测试：phase-end --subagents/--rounds 入账，render 尾部输出"本 run 开销表"。

运行：python skills/plan-test/scripts/test_phase_cost.py
账本经 canonical CLI 路径构造，与 test_gate_stats.py 同一套 fixture 手法。
"""

import refusal_guard  # noqa: F401  测试隔离：把 refusal 写入引到 tmpdir（s1a AC-7，见该模块 docstring）
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
GATE = os.path.join(HERE, "plan_test_gate.py")


def run_gate(args):
    return subprocess.run([sys.executable, GATE] + args, capture_output=True,
                          text=True)


class PhaseCostTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-cost-")
        subprocess.run(["git", "init", "-q", self.tmp], check=True,
                       capture_output=True)
        self.run_dir = os.path.join(self.tmp, "plans", "p", "verification", "r1")
        os.makedirs(os.path.join(self.run_dir, "artifacts"))
        acc = os.path.join(self.tmp, "acceptance.md")
        with open(acc, "w", encoding="utf-8") as f:
            f.write("AC-1 必须：X\n")
        manifest = {
            "run_id": "run-cost",
            "fixture_only": True,
            "source_request_text": "phase cost 测试",
            "scenarios": [{"scenario_id": "S-1", "required": True}],
            "baseline": {"head": "deadbeef", "dirty_patch_sha256": "0" * 64},
            "acceptance_file": acc,
            "applicability": {
                "input_sensitive": {"value": False, "decided_by": "agent",
                                    "rationale": "被测对象是确定性 CLI，输出不随输入语义变化"},
                "llm_payload_driven": {"value": False, "decided_by": "agent",
                                       "rationale": "无 LLM 载荷驱动端侧状态机"},
                "stateful_init": {"value": False, "decided_by": "agent",
                                  "rationale": "无异步注册服务或登录态依赖"},
            },
        }
        mf = os.path.join(self.tmp, "manifest.json")
        with open(mf, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mf])
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def report(self):
        run_gate(["render", "--run-dir", self.run_dir])  # BLOCKED 也照样写 report
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            return f.read()

    def test_cost_table_with_telemetry(self):
        r = run_gate(["phase-start", "--run-dir", self.run_dir, "--phase", "phase-3"])
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_gate(["phase-end", "--run-dir", self.run_dir, "--phase", "phase-3",
                      "--subagents", "4", "--rounds", "2"])
        self.assertEqual(r.returncode, 0, r.stderr)
        report = self.report()
        self.assertIn("本 run 开销表", report)
        row = next(l for l in report.splitlines() if l.startswith("| phase-3 |"))
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertEqual(cells[3], "4")   # 子代理派发
        self.assertEqual(cells[4], "2")   # 轮次
        # 事件跨度非负数字
        self.assertGreaterEqual(float(cells[1]), 0.0)

    def test_telemetry_recorded_in_ledger(self):
        run_gate(["phase-start", "--run-dir", self.run_dir, "--phase", "phase-4"])
        run_gate(["phase-end", "--run-dir", self.run_dir, "--phase", "phase-4",
                  "--subagents", "7", "--rounds", "3"])
        with open(os.path.join(self.run_dir, "plan-test-run.json"),
                  encoding="utf-8") as f:
            ledger = json.load(f)
        ends = [e for e in ledger["events"]
                if e.get("type") == "phase" and e.get("action") == "end"]
        self.assertEqual(ends[-1]["subagents"], 7)
        self.assertEqual(ends[-1]["rounds"], 3)

    def test_no_phase_events_no_table(self):
        self.assertNotIn("本 run 开销表", self.report())

    def test_unpaired_start_does_not_crash(self):
        run_gate(["phase-start", "--run-dir", self.run_dir, "--phase", "phase-5"])
        report = self.report()
        self.assertIn("| phase-5 | 0.0 | 0.0 | 0 | 0 |", report)

    def test_end_without_telemetry_defaults_zero(self):
        run_gate(["phase-start", "--run-dir", self.run_dir, "--phase", "phase-2"])
        run_gate(["phase-end", "--run-dir", self.run_dir, "--phase", "phase-2"])
        report = self.report()
        row = next(l for l in report.splitlines() if l.startswith("| phase-2 |"))
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertEqual(cells[3], "0")
        self.assertEqual(cells[4], "0")


if __name__ == "__main__":
    unittest.main(verbosity=1)
