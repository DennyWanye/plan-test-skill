#!/usr/bin/env python3
"""v0.9.0 SL-2 AC-7a：clustered closure 按矛盾地位路由。

phase-2 的重点论（次要部分 primary 覆盖一次即收）此前只在文档里；gate 要求 closure 与
synthesis canonical 集完全相等，FULL 每轮重审全部 finding（exec-002：2 条次要 AC 跑 5 轮）。
这里守两侧：合法省略放行；碰主要矛盾 / P0 / 仍 open / 未显式标注的一律仍须复核。"""

import refusal_guard  # noqa: F401
import hashlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_plan_test_gate import GateHarness, run_gate

COVERAGE = {k: True for k in (
    "acceptance_coverage", "entry_and_trust_chain", "data_flow_and_persistence",
    "identity_permissions_concurrency_cleanup", "failure_and_recovery",
    "tests_and_evidence", "release_and_rollback", "trusted_boundary_stop")}


def finding(fid, ac, severity="P1", status="open"):
    return {"id": fid, "severity": severity, "scope_relation": "in-scope",
            "origin": "pre-existing", "violated_acceptance_ids": [ac] if ac else [],
            "assurance_contract_ids": ["FAIL-1"] if ac else [], "evidence": "plan",
            "status": status, "root_cause": "gap"}


class ClosureRoutingTest(GateHarness):
    def setup_loop(self, minor_overrides=None, minor_severity="P2"):
        """走到 synthesis 之后：decisive-gap 绑 AC-1（主要矛盾），minor-gap 绑 AC-2。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.plan = self.write("plan.md", "task\n")
        contract = self.write("assurance.json", json.dumps({
            "profile": "standard", "acceptance_ids": ["AC-1", "AC-2"],
            "protected_assets": [{"id": "ASSET-1", "description": "plan"}],
            "trusted_assumptions": [],
            "in_scope_failures": [{"id": "FAIL-1", "description": "incomplete"}],
            "in_scope_adversaries": [], "out_of_scope_conditions": [],
            "maximum_acceptable_impact": "none"}))
        started = run_gate(["start-challenge-loop", "--run-dir", self.run_dir,
                            "--loop-type", "plan-iteration", "--target-file", self.plan,
                            "--assurance-contract", contract, "--orchestration", "clustered"])
        self.assertEqual(started.returncode, 0, started.stderr)
        self.loop_id = started.stdout.strip().splitlines()[-1]
        self.hash1 = self.plan_hash()
        decisive = finding("decisive-gap", "AC-1")
        minor = finding("minor-gap", getattr(self, "minor_round1_ac", "AC-2"), minor_severity)
        r1 = self.write("r1.json", json.dumps({"review_mode": "breadth", "coverage": COVERAGE,
                                               "findings": [decisive, minor]}))
        self.ok(["record-challenge-round", "--round", "1", "--plan-hash", self.hash1, "--findings", r1])
        clusters = self.write("clusters.json", json.dumps({
            "primary_contradiction": {"id": "pc-one", "summary": "core", "acceptance_ids": ["AC-1"]},
            "challenge_clusters": [{
                "cluster_id": "cluster-one", "parent_finding_ids": ["decisive-gap", "minor-gap"],
                "specialty": "architecture", "question": "q?", "required_evidence": ["plan"],
                "specialist_required": True}]}))
        self.ok(["record-challenge-clusters", "--input", clusters])
        spec = self.write("spec.json", json.dumps({
            "cluster_id": "cluster-one", "parent_finding_ids": ["decisive-gap", "minor-gap"],
            "specialty": "architecture", "findings": [decisive, minor], "cross_cluster_refs": [],
            "conclusion": {"status": "confirmed", "summary": "ok"}}))
        self.ok(["record-specialist-challenge", "--cluster-id", "cluster-one",
                 "--status", "completed", "--output", spec])
        minor_canonical = dict(minor, status="resolved", contradiction_role="secondary")
        minor_canonical.update(minor_overrides or {})
        if minor_canonical.get("contradiction_role") == "__drop__":
            del minor_canonical["contradiction_role"]
        canon = [dict(decisive, status="resolved"), minor_canonical]
        synthesis = self.write("synthesis.json", json.dumps({
            "source_cluster_ids": ["cluster-one"], "canonical_findings": canon,
            "resolved_finding_ids": [f["id"] for f in canon if f["status"] == "resolved"],
            "open_finding_ids": [f["id"] for f in canon if f["status"] == "open"],
            "decisions": [{"canonical_finding_id": f["id"], "source_finding_ids": [f["id"]],
                           "action": "plan-change", "rationale": "fix"} for f in canon],
            "conflicts": [], "required_spikes": [], "plan_actions": ["fix"]}))
        self.synthesis_result = self.gate(["record-challenge-synthesis", "--input", synthesis])
        self.write("plan.md", "task\nfixed\n")
        return decisive

    def plan_hash(self):
        with open(self.plan, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def gate(self, args):
        return run_gate([args[0], "--run-dir", self.run_dir, "--loop-id", self.loop_id] + args[1:])

    def ok(self, args):
        res = self.gate(args)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    def closure(self, findings):
        r2 = self.write("r2.json", json.dumps({"review_mode": "diff", "findings": findings}))
        return self.gate(["record-challenge-round", "--round", "2", "--plan-hash", self.plan_hash(),
                          "--based-on-plan-hash", self.hash1, "--findings", r2])

    def test_secondary_resolved_finding_may_be_skipped_and_loop_converges(self):
        decisive = self.setup_loop()
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 0, res.stderr)
        # 第 1 轮 minor-gap 是 open；没按 synthesis 闭环状态覆盖的话这里会是 CONTINUE
        self.assertIn("LOOP_STATE: CONVERGED", res.stdout)

    def test_decisive_finding_cannot_be_skipped(self):
        self.setup_loop()
        res = self.closure([dict(finding("minor-gap", "AC-2", "P2"), status="resolved")])
        self.assertEqual(res.returncode, 2)
        self.assertIn("缺少: decisive-gap", res.stderr)

    def test_secondary_label_on_primary_contradiction_ac_is_ignored(self):
        """地位由 AC 绑定推导：碰到主要矛盾 AC 的 finding 标 secondary 也不能省。"""
        decisive = self.setup_loop({"violated_acceptance_ids": ["AC-1", "AC-2"]})
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 2)
        self.assertIn("缺少: minor-gap", res.stderr)

    def test_secondary_p0_cannot_be_skipped(self):
        decisive = self.setup_loop(minor_severity="P0")
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("缺少: minor-gap", res.stderr)

    def test_secondary_still_open_cannot_be_skipped(self):
        decisive = self.setup_loop({"status": "open"})
        self.assertEqual(self.synthesis_result.returncode, 0, self.synthesis_result.stderr)
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("缺少: minor-gap", res.stderr)

    def test_legacy_synthesis_without_role_keeps_full_coverage(self):
        """缺字段 = 旧行为：既有账本与 fixture 判定不变。"""
        decisive = self.setup_loop({"contradiction_role": "__drop__"})
        self.assertEqual(self.synthesis_result.returncode, 0, self.synthesis_result.stderr)
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 2)
        self.assertIn("缺少: minor-gap", res.stderr)

    def test_secondary_without_ac_binding_cannot_be_skipped(self):
        """AC-7c 回放：唯一可省的 P1 支撑决定性 AC，只因没填 violated_acceptance_ids 才看似不碰主要矛盾。"""
        self.minor_round1_ac = None  # 各轮与 synthesis 都没绑 AC
        decisive = self.setup_loop({"violated_acceptance_ids": [], "assurance_contract_ids": []})
        self.assertEqual(self.synthesis_result.returncode, 0, self.synthesis_result.stderr)
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("缺少: minor-gap", res.stderr)

    def test_downgrading_round1_p0_in_synthesis_does_not_skip(self):
        """code review F-1：第 1 轮是 P0，synthesis 改写成 P2 + secondary，不能靠改写跳过复核。"""
        decisive = self.setup_loop({"severity": "P2"}, minor_severity="P0")
        self.assertEqual(self.synthesis_result.returncode, 0, self.synthesis_result.stderr)
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("缺少: minor-gap", res.stderr)

    def test_rebinding_away_from_primary_ac_in_synthesis_does_not_skip(self):
        """code review F-1：第 1 轮绑主要矛盾 AC-1，synthesis 换绑 AC-2，按历史并集仍碰主要矛盾。"""
        self.minor_round1_ac = "AC-1"
        decisive = self.setup_loop({"violated_acceptance_ids": ["AC-2"]})
        self.assertEqual(self.synthesis_result.returncode, 0, self.synthesis_result.stderr)
        res = self.closure([dict(decisive, status="resolved")])
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("缺少: minor-gap", res.stderr)

    def test_extra_ids_are_listed(self):
        decisive = self.setup_loop()
        res = self.closure([dict(decisive, status="resolved"),
                            dict(finding("ghost-gap", "AC-2", "P2"), status="resolved", origin="patch-induced")])
        self.assertEqual(res.returncode, 2)
        self.assertIn("多余（不在 canonical 集）: ghost-gap", res.stderr)

    def test_invalid_role_rejected_at_synthesis(self):
        self.setup_loop({"contradiction_role": "minor"})
        self.assertEqual(self.synthesis_result.returncode, 2)
        self.assertIn("contradiction_role", self.synthesis_result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
