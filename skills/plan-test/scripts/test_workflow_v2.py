#!/usr/bin/env python3
"""Focused regression tests for the opt-in workflow extensions."""

import hashlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_plan_test_gate as gate_tests
from test_plan_test_gate import GateHarness, run_gate


class WorkflowV2TestCase(GateHarness):
    def test_evidence_contract_requires_trusted_metadata(self):
        scenario = {
            "scenario_id": "S-1", "required": True,
            "evidence_contract": {
                "producer_types": ["runtime-probe"],
                "required_artifact_kinds": ["business-result"],
                "required_identity": ["root_run_id", "session_id"],
                "required_business_facts": ["answer"],
                "required_timestamps": True,
            },
        }
        self.init([scenario])
        self.record("S-1")
        missing = self.finalize(check_only=True)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("PRIMARY_EVIDENCE_MISSING", missing.stdout)

        self.artifact("artifacts/result.json", '{"answer":"ok"}')
        metadata = self.write("metadata.json", json.dumps({
            "producer_type": "runtime-probe",
            "producer_version": "1",
            "artifact_kind": "business-result",
            "generated_at": "2026-08-24T00:00:00+0000",
            "root_run_id": "root-1",
            "session_id": "session-1",
            "business_facts": {"answer": "ok"},
        }))
        attached = run_gate([
            "attach-evidence", "--run-dir", self.run_dir,
            "--path", "artifacts/result.json", "--kind", "primary",
            "--scenario", "S-1", "--metadata", metadata,
        ])
        self.assertEqual(attached.returncode, 0, attached.stderr)
        ready = self.finalize(check_only=True)
        self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)

    def test_untrusted_record_cannot_complete_trusted_evidence_contract(self):
        contract = {
            "producer_types": ["trusted-probe"],
            "required_artifact_kinds": ["business-result"],
            "required_identity": ["root_run_id"],
            "required_business_facts": ["answer"],
            "required_timestamps": True,
        }
        self.init([{"scenario_id": "S-1", "required": True,
                    "evidence_contract": contract}])
        self.record("S-1")
        self.artifact("artifacts/trusted.log", "empty trusted record")
        trusted_meta = self.write("trusted-meta.json", json.dumps({
            "producer_type": "trusted-probe", "artifact_kind": "diagnostic",
        }))
        self.assertEqual(run_gate([
            "attach-evidence", "--run-dir", self.run_dir,
            "--path", "artifacts/trusted.log", "--kind", "primary",
            "--scenario", "S-1", "--metadata", trusted_meta,
        ]).returncode, 0)
        self.artifact("artifacts/self-report.json", "{}")
        untrusted_meta = self.write("untrusted-meta.json", json.dumps({
            "producer_type": "self-report", "artifact_kind": "business-result",
            "generated_at": "2026-08-24T00:00:00+0000", "root_run_id": "root-1",
            "business_facts": {"answer": "ok"},
        }))
        self.assertEqual(run_gate([
            "attach-evidence", "--run-dir", self.run_dir,
            "--path", "artifacts/self-report.json", "--kind", "primary",
            "--scenario", "S-1", "--metadata", untrusted_meta,
        ]).returncode, 0)
        checked = self.finalize(check_only=True)
        self.assertEqual(checked.returncode, 1, checked.stdout)
        self.assertIn("EVIDENCE_CONTRACT_UNSATISFIED", checked.stdout)

    def test_compile_manifest_checks_traceability_and_full_case_set(self):
        acceptance = self.write("acceptance.md", "AC-1\n")
        assurance = self.write("assurance.json", json.dumps({
            "acceptance_ids": ["AC-1"],
        }))
        testcase = self.write("testcase/tc-1.md", "steps\n")
        inventory = self.write("testcase/index.json", json.dumps({
            "testcases": [{"id": "TC-1", "path": testcase, "status": "active",
                           "purpose": "prove AC-1", "surface": "cli", "type": "scripted",
                           "obligations": ["TO-1"], "revision": 1}],
        }))
        reuse = self.write("reuse.json", json.dumps({
            "decisions": [{"obligation_id": "TO-1", "decision": "reuse-as-is",
                           "candidates": ["TC-1"],
                           "selected_testcases": ["TC-1"]}],
        }))
        spec = self.write("spec.json", json.dumps({
            "acceptance_file": acceptance,
            "assurance_contract": assurance,
            "testcase_inventory": inventory,
            "reuse_report": reuse,
            "obligations": [{"obligation_id": "TO-1", "ac_ids": ["AC-1"]}],
            "scenarios": [{"scenario_id": "S-1", "required": True,
                           "testcase_ids": ["TC-1"],
                           "evidence_contract": {
                               "producer_types": ["gate-exec"],
                               "required_artifact_kinds": ["execution-log"],
                               "required_identity": ["root_run_id"],
                               "required_timestamps": True,
                           }}],
            "manifest": {"fixture_only": True, "source_request_text": "request",
                         "applicability": self.applicability()},
        }))
        output = os.path.join(self.tmp, "compiled.json")
        compiled = run_gate(["compile-manifest", "--spec", spec, "--output", output])
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        with open(spec, encoding="utf-8") as handle:
            empty_contract_data = json.load(handle)
        empty_contract_data["scenarios"][0]["evidence_contract"] = {}
        empty_contract_spec = self.write("empty-contract-spec.json", json.dumps(empty_contract_data))
        empty_contract = run_gate([
            "compile-manifest", "--spec", empty_contract_spec,
            "--output", os.path.join(self.tmp, "empty-contract-manifest.json"),
        ])
        self.assertEqual(empty_contract.returncode, 2, empty_contract.stderr)
        self.assertIn("EVIDENCE_CONTRACT_INVALID", empty_contract.stderr)
        with open(output, encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["compiled_manifest"]["case_sets"]["full"], ["S-1"])
        self.assertTrue(manifest["structured_audit_required"])
        self.assertFalse(manifest["active_run_required"])
        initialized = run_gate(["init", "--run-dir", self.run_dir, "--manifest", output])
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.artifact("auditor-input.json", '{}')
        self.artifact("auditor-output.md", 'VERDICT: FAIL\n')
        legacy_audit = run_gate([
            "audit", "--run-dir", self.run_dir, "--verdict", "FAIL",
            "--engine", "opus-auditor", "--input", "auditor-input.json",
            "--output", "auditor-output.md",
        ])
        self.assertEqual(legacy_audit.returncode, 2, legacy_audit.stderr)
        self.assertIn("STRUCTURED_AUDIT_REQUIRED", legacy_audit.stderr)
        manifest["scenarios"] = []
        manifest["compiled_manifest"]["case_sets"]["full"] = []
        tampered = self.write("tampered-compiled.json", json.dumps(manifest))
        rejected = run_gate([
            "init", "--run-dir", os.path.join(self.tmp, "tampered-run"),
            "--manifest", tampered,
        ])
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertIn("COMPILED_MANIFEST_SEAL_MISMATCH", rejected.stderr)
        with open(spec, encoding="utf-8") as handle:
            delivery_spec_data = json.load(handle)
        delivery_spec_data["manifest"].pop("fixture_only")
        delivery_spec = self.write("delivery-spec.json", json.dumps(delivery_spec_data))
        delivery_output = os.path.join(self.tmp, "delivery-manifest.json")
        self.assertEqual(run_gate([
            "compile-manifest", "--spec", delivery_spec, "--output", delivery_output,
        ]).returncode, 0)
        with open(delivery_output, encoding="utf-8") as handle:
            self.assertTrue(json.load(handle)["active_run_required"])

    def test_clustered_challenge_requires_specialist_synthesis_and_closure(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        plan = self.write("plan.md", "task\n")
        contract = self.write("assurance.json", json.dumps({
            "profile": "standard",
            "acceptance_ids": ["AC-1"],
            "protected_assets": [{"id": "ASSET-1", "description": "plan"}],
            "trusted_assumptions": [],
            "in_scope_failures": [{"id": "FAIL-1", "description": "incomplete"}],
            "in_scope_adversaries": [],
            "out_of_scope_conditions": [],
            "maximum_acceptable_impact": "no missing required work",
        }))
        started = run_gate([
            "start-challenge-loop", "--run-dir", self.run_dir,
            "--loop-type", "plan-iteration", "--target-file", plan,
            "--assurance-contract", contract, "--orchestration", "clustered",
        ])
        self.assertEqual(started.returncode, 0, started.stderr)
        loop_id = started.stdout.strip().splitlines()[-1]
        with open(plan, "rb") as plan_file:
            plan_hash = hashlib.sha256(plan_file.read()).hexdigest()
        finding = {
            "id": "finding-one", "severity": "P1", "scope_relation": "in-scope",
            "origin": "pre-existing", "violated_acceptance_ids": ["AC-1"],
            "assurance_contract_ids": ["FAIL-1"], "evidence": "plan",
            "status": "open", "root_cause": "missing detail",
        }
        payload = self.write("round1.json", json.dumps({
            "review_mode": "breadth",
            "coverage": {key: True for key in (
                "acceptance_coverage", "entry_and_trust_chain", "data_flow_and_persistence",
                "identity_permissions_concurrency_cleanup", "failure_and_recovery",
                "tests_and_evidence", "release_and_rollback", "trusted_boundary_stop")},
            "findings": [finding],
        }))
        first = run_gate([
            "record-challenge-round", "--run-dir", self.run_dir, "--loop-id", loop_id,
            "--round", "1", "--plan-hash", plan_hash, "--findings", payload,
        ])
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("SPECIALIST_CHALLENGE_REQUIRED", run_gate([
            "check-loop-limit", "--run-dir", self.run_dir, "--loop-id", loop_id,
        ]).stdout)
        clusters = self.write("clusters.json", json.dumps({
            "primary_contradiction": {"id": "pc-one", "summary": "missing detail",
                                      "acceptance_ids": ["AC-1"]},
            "challenge_clusters": [{
                "cluster_id": "cluster-one", "parent_finding_ids": ["finding-one"],
                "specialty": "architecture", "question": "what detail is required?",
                "required_evidence": ["plan"], "specialist_required": True,
            }],
        }))
        self.assertEqual(run_gate([
            "record-challenge-clusters", "--run-dir", self.run_dir,
            "--loop-id", loop_id, "--input", clusters,
        ]).returncode, 0)
        bad_specialist = self.write("bad-specialist.json", json.dumps({
            "cluster_id": "cluster-one", "parent_finding_ids": ["finding-one"],
            "specialty": "architecture", "findings": [], "cross_cluster_refs": [],
            "conclusion": {"status": "confirmed", "summary": "claims coverage"},
        }))
        rejected_specialist = run_gate([
            "record-specialist-challenge", "--run-dir", self.run_dir,
            "--loop-id", loop_id, "--cluster-id", "cluster-one",
            "--status", "completed", "--output", bad_specialist,
        ])
        self.assertEqual(rejected_specialist.returncode, 2, rejected_specialist.stderr)
        self.assertIn("缺少 parent findings", rejected_specialist.stderr)
        specialist = self.write("specialist.json", json.dumps({
            "cluster_id": "cluster-one", "parent_finding_ids": ["finding-one"],
            "specialty": "architecture", "findings": [finding],
            "cross_cluster_refs": [],
            "conclusion": {"status": "confirmed", "summary": "confirmed"},
        }))
        self.assertEqual(run_gate([
            "record-specialist-challenge", "--run-dir", self.run_dir,
            "--loop-id", loop_id, "--cluster-id", "cluster-one",
            "--status", "completed", "--output", specialist,
        ]).returncode, 0)
        synthesis = self.write("synthesis.json", json.dumps({
            "source_cluster_ids": ["cluster-one"],
            "canonical_findings": [dict(finding, status="resolved")],
            "resolved_finding_ids": ["finding-one"], "open_finding_ids": [],
            "decisions": [{"canonical_finding_id": "finding-one",
                           "source_finding_ids": ["finding-one"],
                           "action": "plan-change", "rationale": "add detail"}],
            "conflicts": [], "required_spikes": [], "plan_actions": ["add detail"],
        }))
        self.assertEqual(run_gate([
            "record-challenge-synthesis", "--run-dir", self.run_dir,
            "--loop-id", loop_id, "--input", synthesis,
        ]).returncode, 0)
        resolved = dict(finding, status="resolved")
        round2 = self.write("round2.json", json.dumps({
            "review_mode": "diff", "findings": [resolved],
        }))
        unchanged = run_gate([
            "record-challenge-round", "--run-dir", self.run_dir, "--loop-id", loop_id,
            "--round", "2", "--plan-hash", plan_hash,
            "--based-on-plan-hash", plan_hash, "--findings", round2,
        ])
        self.assertEqual(unchanged.returncode, 2, unchanged.stderr)
        self.assertIn("CLOSURE_PLAN_UNCHANGED", unchanged.stderr)
        plan = self.write("plan.md", "task\nadd required detail\n")
        with open(plan, "rb") as handle:
            revised_plan_hash = hashlib.sha256(handle.read()).hexdigest()
        closure = run_gate([
            "record-challenge-round", "--run-dir", self.run_dir, "--loop-id", loop_id,
            "--round", "2", "--plan-hash", revised_plan_hash,
            "--based-on-plan-hash", plan_hash, "--findings", round2,
        ])
        self.assertEqual(closure.returncode, 0, closure.stderr)
        self.assertIn("LOOP_STATE: CONVERGED", closure.stdout)

    def test_audit_findings_block_until_resolved_and_reaudited(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1")
        self.artifact("auditor-input.json", '{"scope":"all"}')
        self.artifact("auditor-output.json", json.dumps({
            "verdict": "FAIL",
            "findings": [{
                "id": "audit-one", "severity": "P1", "status": "open",
                "type": "evidence", "summary": "missing proof", "ac_ids": ["AC-1"],
                "scenario_ids": ["S-1"], "required_retest": False,
            }],
        }))
        audit = run_gate([
            "audit", "--run-dir", self.run_dir, "--verdict", "FAIL",
            "--engine", "opus-auditor", "--input", "auditor-input.json",
            "--output", "auditor-output.json",
        ])
        self.assertEqual(audit.returncode, 0, audit.stderr)
        blocked = self.finalize(check_only=True)
        self.assertIn("OPEN_AUDIT_FINDINGS", blocked.stdout)
        self.artifact("artifacts/resolution.log", "proof added")
        self.attach("artifacts/resolution.log", scenario="S-1")
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as handle:
            evidence_id = json.load(handle)["evidence"][-1]["evidence_id"]
        resolved = run_gate([
            "resolve-audit-finding", "--run-dir", self.run_dir,
            "--finding-id", "audit-one", "--resolution", "proof added",
            "--evidence-ids", evidence_id,
        ])
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        listed = run_gate(["list-audit-findings", "--run-dir", self.run_dir])
        self.assertIn("audit-one\tP1\tresolved", listed.stdout)

    def test_structured_fail_requires_actionable_finding_and_retest_scope(self):
        self.init([{"scenario_id": "S-1", "required": True}],
                  structured_audit_required=True)
        self.artifact("auditor-input.json", '{}')
        self.artifact("auditor-output.json", json.dumps({
            "verdict": "FAIL", "findings": [],
        }))
        empty = run_gate([
            "audit", "--run-dir", self.run_dir, "--verdict", "FAIL",
            "--engine", "opus-auditor", "--input", "auditor-input.json",
            "--output", "auditor-output.json",
        ])
        self.assertEqual(empty.returncode, 2, empty.stderr)
        self.assertIn("AUDIT_FAIL_FINDING_REQUIRED", empty.stderr)
        self.artifact("auditor-output.json", json.dumps({
            "verdict": "FAIL", "findings": [{
                "id": "needs-retest", "severity": "P1", "status": "open",
                "type": "code", "summary": "must rerun", "ac_ids": ["AC-1"],
                "scenario_ids": [], "required_retest": True,
            }],
        }))
        unbound = run_gate([
            "audit", "--run-dir", self.run_dir, "--verdict", "FAIL",
            "--engine", "opus-auditor", "--input", "auditor-input.json",
            "--output", "auditor-output.json",
        ])
        self.assertEqual(unbound.returncode, 2, unbound.stderr)
        self.assertIn("required_retest=true", unbound.stderr)

    def test_receipt_counts_shared_content_once(self):
        self.init([{"scenario_id": "S-1", "required": True},
                   {"scenario_id": "S-2", "required": True}])
        self.artifact("artifacts/a.log", "same original bytes")
        self.artifact("artifacts/b.log", "same original bytes")
        self.attach("artifacts/a.log", scenario="S-1")
        self.attach("artifacts/b.log", scenario="S-2")
        self.record("S-1")
        self.record("S-2")
        self.audit_pass()
        finalized = self.finalize()
        self.assertEqual(finalized.returncode, 3, finalized.stdout + finalized.stderr)
        with open(os.path.join(self.run_dir, "gate-receipt.json"), encoding="utf-8") as handle:
            summary = json.load(handle)["evidence_summary"]
        self.assertEqual(summary["records"], 2)
        self.assertEqual(summary["distinct_artifacts"], 1)
        self.assertEqual(len(summary["shared_artifact_sha256"]), 1)


class ActiveRunWorkflowTestCase(unittest.TestCase):
    setUp = gate_tests.RealRepoAttestationTestCase.setUp
    tearDown = gate_tests.RealRepoAttestationTestCase.tearDown
    git = gate_tests.RealRepoAttestationTestCase.git
    write = gate_tests.RealRepoAttestationTestCase.write
    init_real_run = gate_tests.RealRepoAttestationTestCase.init_real_run
    check = gate_tests.RealRepoAttestationTestCase.check

    def test_activate_run_is_required_and_does_not_change_candidate_digest(self):
        self.init_real_run(active_run_required=True)
        before = self.check()
        self.assertEqual(before.returncode, 1, before.stdout)
        self.assertIn("ACTIVE_RUN_MISMATCH", before.stdout)

        activated = run_gate(["activate-run", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(activated.returncode, 0, activated.stderr)
        after = self.check()
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
        self.assertNotIn("TESTED_RUNTIME_MISMATCH", after.stdout)
        with open(os.path.join(self.run_dir, "auditor-input.json"), "w", encoding="utf-8") as h:
            h.write('{"scope":"all"}')
        with open(os.path.join(self.run_dir, "auditor-output.json"), "w", encoding="utf-8") as h:
            h.write('{"verdict":"PASS","findings":[]}')
        audited = run_gate([
            "audit", "--run-dir", self.run_dir, "--verdict", "PASS",
            "--engine", "opus-auditor", "--input", "auditor-input.json",
            "--output", "auditor-output.json",
        ], cwd=self.repo)
        self.assertEqual(audited.returncode, 0, audited.stderr)
        finalized = run_gate(["finalize", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(finalized.returncode, 0, finalized.stdout + finalized.stderr)
        with open(os.path.join(self.repo, ".plan-test", "active-run.json"),
                  encoding="utf-8") as handle:
            registry = json.load(handle)
        self.assertTrue(registry["latest_valid_receipt_digest"])


if __name__ == "__main__":
    unittest.main()
