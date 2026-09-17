#!/usr/bin/env python3
"""v0.9.0 SL-2 AC-10：v0.8.1 之后 13 条拒绝里 10 条是摩擦（0 条防住真问题）。每项一个守护用例。"""

import refusal_guard  # noqa: F401
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_plan_test_gate import GateHarness, run_gate
import test_closure_routing


def refusals(home):
    path = os.path.join(home, "refusals.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class EvidencePathTest(GateHarness):
    def setUp(self):
        super().setUp()
        self.init([{"scenario_id": "S-1", "required": True}])
        self.artifact("artifacts/probe.log", "ok\n")

    def attach_path(self, path, cwd=None):
        return run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path", path,
                         "--kind", "primary", "--scenario", "S-1"], cwd=cwd)

    def stored_paths(self):
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as fh:
            return [e["path"] for e in json.load(fh).get("evidence") or []]

    def test_repo_relative_path_is_normalized_to_run_relative(self):
        res = self.attach_path("verification/run-1/artifacts/probe.log", cwd=self.tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.stored_paths(), ["artifacts/probe.log"])

    def test_absolute_path_inside_run_dir_is_accepted(self):
        res = self.attach_path(os.path.join(self.run_dir, "artifacts", "probe.log"))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.stored_paths(), ["artifacts/probe.log"])

    def test_run_relative_path_still_works(self):
        res = self.attach_path("artifacts/probe.log")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_missing_file_lists_both_resolutions(self):
        res = self.attach_path("artifacts/nope.log", cwd=self.tmp)
        self.assertEqual(res.returncode, 2)
        self.assertIn("EVIDENCE_PATH_NOT_FOUND", res.stderr)
        self.assertIn("按相对 run-dir解析", res.stderr)
        self.assertIn("按相对当前目录/绝对解析", res.stderr)

    @unittest.skipUnless(sys.platform == "darwin", "大小写不敏感文件系统")
    def test_absolute_path_with_different_case_is_accepted(self):
        """code review F-4：macOS 上路径大小写与 run-dir 不一致时曾被误拒为"须在 run-dir 内"。"""
        res = self.attach_path(os.path.join(self.run_dir, "ARTIFACTS", "probe.log"))
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_file_outside_run_dir_is_rejected(self):
        outside = self.write("elsewhere/probe.log", "x\n")
        res = self.attach_path(outside)
        self.assertEqual(res.returncode, 2)
        self.assertIn("须在 run-dir 内", res.stderr)

    def test_audit_accepts_absolute_input_and_output(self):
        inp = self.artifact("audit/input.md", "facts\n")
        out = self.artifact("audit/output.json", json.dumps({"verdict": "PASS", "findings": []}))
        res = run_gate(["audit", "--run-dir", self.run_dir, "--input", inp, "--output", out,
                        "--verdict", "PASS", "--engine", "opus-5"])
        self.assertEqual(res.returncode, 0, res.stderr)
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as fh:
            auditor = json.load(fh)["auditor"]
        # 旧代码把绝对路径原样存进账本；现在归一成 run 相对，与 run 相对传参的账本一致
        self.assertEqual((auditor["input_path"], auditor["output_path"]),
                         ("audit/input.md", "audit/output.json"))
        outside = self.write("elsewhere/audit.json", json.dumps({"verdict": "PASS", "findings": []}))
        rejected = run_gate(["audit", "--run-dir", self.run_dir, "--input", inp, "--output", outside,
                             "--verdict", "PASS", "--engine", "opus-5"])
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("须在 run-dir 内", rejected.stderr)
        missing = run_gate(["audit", "--run-dir", self.run_dir, "--input", "audit/none.md",
                            "--output", out, "--verdict", "PASS", "--engine", "opus-5"])
        self.assertEqual(missing.returncode, 2)
        self.assertIn("按相对 run-dir解析", missing.stderr)


class UnknownCommandTest(GateHarness):
    def test_unknown_command_is_recorded_with_intent_hint(self):
        home = tempfile.mkdtemp(prefix="refusal-")
        env_home = os.environ.get("PLAN_TEST_REFUSAL_HOME")
        os.environ["PLAN_TEST_REFUSAL_HOME"] = home
        try:
            res = run_gate(["record-behavior-change", "--run-dir", self.run_dir])
        finally:
            if env_home is None:
                os.environ.pop("PLAN_TEST_REFUSAL_HOME")
            else:
                os.environ["PLAN_TEST_REFUSAL_HOME"] = env_home
        self.assertEqual(res.returncode, 2)
        self.assertIn("compile-manifest", res.stderr)
        self.assertNotIn("是不是想敲", res.stderr, "意图提示优先，不再导向字面相近的错误命令")
        rows = refusals(home)
        self.assertEqual(rows[-1]["cmd"], "record-behavior-change")
        self.assertEqual(rows[-1]["code"], "ARGS_INVALID")


class BadArgumentValueTest(GateHarness):
    def test_bad_option_value_keeps_subcommand_name(self):
        """code review F-3：参数值写错（--format primry）时 refusal 的 cmd 仍是子命令名。"""
        home = tempfile.mkdtemp(prefix="refusal-")
        old = os.environ.get("PLAN_TEST_REFUSAL_HOME")
        os.environ["PLAN_TEST_REFUSAL_HOME"] = home
        try:
            run_gate(["print-schema", "--format", "primry"])
        finally:
            if old is None:
                os.environ.pop("PLAN_TEST_REFUSAL_HOME")
            else:
                os.environ["PLAN_TEST_REFUSAL_HOME"] = old
        self.assertEqual(refusals(home)[-1]["cmd"], "print-schema")


class ChallengeMessageTest(test_closure_routing.ClosureRoutingTest):
    """复用 closure 路由的建 loop 流程；只加消息断言，不重复跑父类用例。"""

    def test_synthesis_already_recorded_has_code_and_next_step(self):
        self.setup_loop()
        synthesis = os.path.join(self.tmp, "synthesis.json")
        res = self.gate(["record-challenge-synthesis", "--input", synthesis])
        self.assertEqual(res.returncode, 2)
        self.assertIn("CHALLENGE_SYNTHESIS_ALREADY_RECORDED: ", res.stderr)
        self.assertNotIn("USAGE_ERROR", res.stderr)
        self.assertIn("--round 2", res.stderr)

    def test_primary_challenge_required_reports_round_and_next_step(self):
        self.setup_loop()
        # 新开一个没有任何轮次的 loop，直接记 clusters
        contract = os.path.join(self.tmp, "assurance.json")
        started = run_gate(["start-challenge-loop", "--run-dir", self.run_dir,
                            "--loop-type", "plan-iteration", "--target-file", self.plan,
                            "--assurance-contract", contract, "--orchestration", "clustered"])
        self.assertEqual(started.returncode, 0, started.stderr)
        fresh = started.stdout.strip().splitlines()[-1]
        res = run_gate(["record-challenge-clusters", "--run-dir", self.run_dir, "--loop-id", fresh,
                        "--input", os.path.join(self.tmp, "clusters.json")])
        self.assertEqual(res.returncode, 2)
        self.assertIn("PRIMARY_CHALLENGE_REQUIRED", res.stderr)
        self.assertIn("当前已记 0 轮", res.stderr)
        self.assertIn("record-challenge-round --round 1", res.stderr)

    def test_closure_plan_unchanged_says_edit_plan_first(self):
        self.decisive = self.setup_loop()
        self.write("plan.md", "task\n")  # 改回原样：hash 未变
        res = self.closure([dict(self.decisive, status="resolved")])
        self.assertEqual(res.returncode, 2)
        self.assertIn("CLOSURE_PLAN_UNCHANGED", res.stderr)
        self.assertIn("先按 synthesis 的 plan_actions 修改", res.stderr)


for name in [n for n in dir(test_closure_routing.ClosureRoutingTest) if n.startswith("test_")]:
    setattr(ChallengeMessageTest, name, None)


class PrintSchemaTest(unittest.TestCase):
    def test_clusters_and_synthesis_templates_are_valid_json(self):
        for target, keys in (("clusters", {"primary_contradiction", "challenge_clusters"}),
                             ("synthesis", {"canonical_findings", "decisions"})):
            res = run_gate(["print-schema", "--target", target, "--format", "template"])
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(keys.issubset(json.loads(res.stdout)))
        human = run_gate(["print-schema", "--target", "synthesis"])
        self.assertIn("contradiction_role", human.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
