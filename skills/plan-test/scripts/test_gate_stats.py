#!/usr/bin/env python3
"""stats 子命令的测试（T4：规则退休的数据来源）。

运行：python skills/plan-test/scripts/test_gate_stats.py
账本全部经 canonical CLI 路径构造（init/record-run/…），不手写账本 JSON——
手写的四键 JSON 过不了 validate 的链校验，测出来的是解析失败路径而不是统计路径。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
GATE = os.path.join(HERE, "plan_test_gate.py")
FIXTURE_EXIT = 3


def run_gate(args, cwd=None):
    return subprocess.run([sys.executable, GATE] + args, capture_output=True,
                          text=True, cwd=cwd)


class StatsHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-stats-")
        subprocess.run(["git", "init", "-q", self.tmp], check=True,
                       capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, content):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def make_run(self, name, scenarios, run_id=None):
        run_dir = os.path.join(self.tmp, "plans", name, "verification", "r1")
        os.makedirs(os.path.join(run_dir, "artifacts"), exist_ok=True)
        acc = self.write("plans/%s/acceptance.md" % name, "AC-1 必须：X\n")
        manifest = {
            "run_id": run_id or ("run-%s" % name),
            "fixture_only": True,
            "source_request_text": "stats 测试",
            "scenarios": scenarios,
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
        mf = self.write("plans/%s/manifest.json" % name,
                        json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", run_dir, "--manifest", mf])
        self.assertEqual(r.returncode, 0, r.stderr)
        return run_dir

    def record(self, run_dir, scenario, **kw):
        args = ["record-run", "--run-dir", run_dir, "--scenario", scenario,
                "--kind", "root", "--result", "pass"]
        for k, v in kw.items():
            args += ["--" + k.replace("_", "-"), v]
        r = run_gate(args)
        self.assertEqual(r.returncode, 0, r.stderr)

    def stats(self, *extra):
        return run_gate(["stats", "--root", self.tmp] + list(extra))

    def stats_json(self, *extra):
        r = run_gate(["stats", "--root", self.tmp, "--json"] + list(extra))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class StatsTest(StatsHarness):
    def test_no_ledgers(self):
        r = self.stats()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("没有可统计的账本", r.stdout)

    def test_counts_triggered_code_and_lists_zero(self):
        run_dir = self.make_run("p1", [{"scenario_id": "S-1", "required": True},
                                       {"scenario_id": "S-2", "required": True}])
        self.record(run_dir, "S-1")  # S-2 未跑 → REQUIRED_SCENARIO_NOT_RUN
        data = self.stats_json()
        self.assertEqual(data["runs_scanned"], 1)
        self.assertEqual(data["receipts"], 0)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", data["per_code"])
        self.assertEqual(data["per_code"]["REQUIRED_SCENARIO_NOT_RUN"]["runs"], 1)
        self.assertEqual(data["per_code"]["REQUIRED_SCENARIO_NOT_RUN"]["last_run"],
                         "run-p1")
        self.assertNotIn("LEDGER_TAMPERED", data["per_code"])
        # 样本 1 < 默认窗口 5 → 不出退休结论
        self.assertEqual(data["retirement_candidates"], [])
        text = self.stats()
        self.assertIn("样本不足", text.stdout)

    def test_window_retirement_candidates(self):
        run_dir = self.make_run("p1", [{"scenario_id": "S-1", "required": True},
                                       {"scenario_id": "S-2", "required": True}])
        self.record(run_dir, "S-1")
        data = self.stats_json("--window", "1")
        self.assertIn("LEDGER_TAMPERED", data["retirement_candidates"])
        self.assertNotIn("REQUIRED_SCENARIO_NOT_RUN", data["retirement_candidates"])
        text = self.stats("--window", "1")
        self.assertIn("退休候选", text.stdout)

    def test_fixtures_dir_and_nonledger_skipped(self):
        self.write("fixtures/fake/plan-test-run.json", json.dumps({
            "schema_version": "x", "run_id": "x", "scenarios": [], "integrity": {}}))
        self.write("docs/notes.json", json.dumps({"just": "data"}))
        data = self.stats_json()
        self.assertEqual(data["runs_scanned"], 0)

    def test_receipt_counted_and_multi_run(self):
        # run A：完整 PASS 路径 → 有 receipt
        run_a = self.make_run("pa", [{"scenario_id": "S-1", "required": True,
                                      "ui": True, "gate_type": "positive-value",
                                      "expected_run_created": True}],
                              run_id="run-pa")
        shot = os.path.join(run_a, "artifacts", "s1.png")
        with open(shot, "w", encoding="utf-8") as f:
            f.write("shot")
        r = run_gate(["attach-evidence", "--run-dir", run_a,
                      "--path", "artifacts/s1.png", "--kind", "primary",
                      "--scenario", "S-1", "--ui-action"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.record(run_a, "S-1", business_terminal="completed+valid",
                    run_id_under_test="run-uuid-1", session_id="sess-new")
        for name, content in (("auditor-input.json", '{"frozen": true}'),
                              ("auditor-output.json", '{"verdict": "PASS"}')):
            with open(os.path.join(run_a, name), "w", encoding="utf-8") as f:
                f.write(content)
        r = run_gate(["audit", "--run-dir", run_a, "--verdict", "PASS",
                      "--engine", "opus-auditor", "--input", "auditor-input.json",
                      "--output", "auditor-output.json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_gate(["finalize", "--run-dir", run_a])
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout + r.stderr)
        # run B：未闭环
        run_b = self.make_run("pb", [{"scenario_id": "S-1", "required": True}],
                              run_id="run-pb")
        data = self.stats_json()
        self.assertEqual(data["runs_scanned"], 2)
        self.assertEqual(data["receipts"], 1)
        self.assertEqual(data["per_code"]["REQUIRED_SCENARIO_NOT_RUN"]["last_run"],
                         "run-pb")


if __name__ == "__main__":
    unittest.main(verbosity=1)
