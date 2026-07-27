#!/usr/bin/env python3
"""plan_test_gate.py 自测。

运行：python skills/plan-test/scripts/test_plan_test_gate.py
覆盖 handoff §8 要求的关键 fixture：状态矛盾、required NOT_RUN、证据缺失/篡改、
循环证据、frozen oracle 变异、audit 后 stale、receipt 幂等、Companion 历史三冲突
dogfood，以及一条完整 PASS 路径。全部经 canonical CLI 路径执行，不绕过 finalize。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "plan_test_gate.py")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_utf8(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def run_gate(args, cwd=None):
    return subprocess.run([sys.executable, GATE] + args, capture_output=True,
                          text=True, cwd=cwd)


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-test-")
        self.run_dir = os.path.join(self.tmp, "verification", "run-1")
        os.makedirs(os.path.join(self.run_dir, "artifacts"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- helpers ----------

    def write(self, rel, content):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def artifact(self, rel, content):
        p = os.path.join(self.run_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def manifest(self, scenarios, **extra):
        m = {
            "run_id": "t-run",
            "fixture_only": True,
            "source_request_text": "原始用户请求：新话题必须创建新 Session",
            "scenarios": scenarios,
            "baseline": {"head": "deadbeef", "dirty_patch_sha256": "0" * 64},
        }
        acc = self.write("acceptance.md", "AC-1 必须：点击新话题创建新 UUID Session\n")
        m["acceptance_file"] = acc
        m.update(extra)
        return self.write("manifest.json", json.dumps(m, ensure_ascii=False))

    def init(self, scenarios, **extra):
        r = run_gate(["init", "--run-dir", self.run_dir,
                      "--manifest", self.manifest(scenarios, **extra)])
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def record(self, scenario, result="pass", kind="root", **kw):
        args = ["record-run", "--run-dir", self.run_dir, "--scenario", scenario,
                "--kind", kind, "--result", result]
        for k, v in kw.items():
            args += ["--" + k.replace("_", "-"), v]
        r = run_gate(args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def attach(self, path, kind="primary", scenario=None, ui_action=False,
               negative=False, depends_on=None):
        args = ["attach-evidence", "--run-dir", self.run_dir,
                "--path", path, "--kind", kind]
        if scenario:
            args += ["--scenario", scenario]
        if ui_action:
            args += ["--ui-action"]
        if negative:
            args += ["--negative-assertion"]
        if depends_on:
            args += ["--depends-on"] + depends_on
        r = run_gate(args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def audit_pass(self):
        self.artifact("auditor-input.json", '{"frozen": true}')
        self.artifact("auditor-output.json", '{"verdict": "PASS"}')
        r = run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                      "--input", "auditor-input.json",
                      "--output", "auditor-output.json"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def finalize(self, check_only=False):
        args = ["finalize", "--run-dir", self.run_dir]
        if check_only:
            args.append("--check-only")
        return run_gate(args)

    def full_pass_run(self):
        """一条证据完整的合法 PASS 路径（防 gate 只会拒绝）。"""
        self.init([{"scenario_id": "S-1", "required": True, "ui": True,
                    "gate_type": "positive-value", "expected_run_created": True}])
        self.artifact("artifacts/s1-click.png", "screenshot-bytes")
        self.attach("artifacts/s1-click.png", scenario="S-1", ui_action=True)
        self.record("S-1", business_terminal="completed+valid",
                    run_id_under_test="run-uuid-1", session_id="sess-new")
        self.audit_pass()

    # ---------- PASS path ----------

    def test_full_pass_path_and_receipt_idempotent(self):
        self.full_pass_run()
        r1 = self.finalize()
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        self.assertIn("GATE RECEIPT:", r1.stdout)
        with open(os.path.join(self.run_dir, "gate-receipt.json"), encoding="utf-8") as f:
            receipt1 = json.load(f)
        r2 = self.finalize()  # 幂等：同输入同 digest，复用首次 finalized_at
        self.assertEqual(r2.returncode, 0)
        with open(os.path.join(self.run_dir, "gate-receipt.json"), encoding="utf-8") as f:
            receipt2 = json.load(f)
        self.assertEqual(receipt1["content_digest"], receipt2["content_digest"])
        self.assertEqual(receipt1["finalized_at"], receipt2["finalized_at"])
        self.assertTrue(receipt1["fixture_only"])
        rr = run_gate(["render", "--run-dir", self.run_dir])
        self.assertEqual(rr.returncode, 0, rr.stdout)
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            report = f.read()
        self.assertIn("STATE: SHIPPABLE", report)
        self.assertIn("FIXTURE-ONLY", report)

    def test_check_only_ready_without_audit(self):
        """预检不因'审计尚未执行'而无法进入审计阶段。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("READY_FOR_AUDIT", r.stdout)

    # ---------- FAIL fixtures (handoff §8) ----------

    def test_required_scenario_not_run(self):
        self.init([{"scenario_id": "S-1", "required": True},
                   {"scenario_id": "S-2", "required": True}])
        self.record("S-1")
        self.audit_pass()
        r = self.finalize()
        self.assertEqual(r.returncode, 1)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "gate-receipt.json")))

    def test_delivery_ship_with_partial_manual_test(self):
        """delivery=SHIP + manual-test=PARTIAL → FAIL。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="partial")
        run_gate(["set-delivery", "--run-dir", self.run_dir, "--verdict", "SHIP"])
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DELIVERY_VERDICT_CONTRADICTS_LEDGER", r.stdout)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stdout)

    def test_status_conflict_declared_pass_vs_ledger(self):
        """RESULTS 声称 PASS 而账本 NOT_RUN → STATUS_CONFLICT。"""
        self.init([{"scenario_id": "S-2", "required": True}])
        run_gate(["declare-status", "--run-dir", self.run_dir,
                  "--source", "manual-results.md", "--scenario", "S-2",
                  "--status", "PASS"])
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("STATUS_CONFLICT", r.stdout)

    def test_evidence_missing_and_hash_mismatch(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        p = self.artifact("artifacts/log.txt", "original")
        escaped = run_gate(["attach-evidence", "--run-dir", self.run_dir,
                            "--path", "..\\outside.txt", "--kind", "primary"])
        self.assertEqual(escaped.returncode, 2)
        self.assertIn("逃逸 run-dir", escaped.stderr)
        absolute = run_gate(["attach-evidence", "--run-dir", self.run_dir,
                             "--path", p, "--kind", "primary"])
        self.assertEqual(absolute.returncode, 2)
        self.assertIn("不能是绝对路径", absolute.stderr)
        self.attach("artifacts\\log.txt", scenario="S-1")
        self.record("S-1")
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["evidence"][0]["path"], "artifacts/log.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("tampered")  # 篡改
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("EVIDENCE_HASH_MISMATCH", r.stdout)
        os.unlink(p)  # 删除
        r = self.finalize(check_only=True)
        self.assertIn("EVIDENCE_MISSING", r.stdout)

    def test_evidence_dependency_cycle(self):
        """manual-results 与 delivery-audit 互相引用 → 拒绝环。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.artifact("artifacts/a.md", "cites b")
        self.artifact("artifacts/b.md", "cites a")
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                  "artifacts/a.md", "--kind", "derived", "--id", "ev-a",
                  "--depends-on", "ev-b"])
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                  "artifacts/b.md", "--kind", "derived", "--id", "ev-b",
                  "--depends-on", "ev-a"])
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("EVIDENCE_DEPENDENCY_CYCLE", r.stdout)

    def test_derived_only_evidence_rejected(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        self.artifact("artifacts/summary.md", "we tested it, trust us")
        self.attach("artifacts/summary.md", kind="derived", scenario="S-1")
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DERIVED_EVIDENCE_ONLY", r.stdout)

    def test_ui_scenario_needs_ui_action_evidence(self):
        self.init([{"scenario_id": "S-1", "required": True, "ui": True}])
        self.artifact("artifacts/code-review.md", "代码审计通过")
        self.attach("artifacts/code-review.md", scenario="S-1")  # primary 但非 ui_action
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("UI_EVIDENCE_MISSING", r.stdout)

    def test_expected_run_created_unverified(self):
        """多阶段场景缺 Session/Run ID → FAIL。"""
        self.init([{"scenario_id": "S-1", "required": True,
                    "expected_run_created": True}])
        self.record("S-1")  # 未记录 run_id_under_test
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RUN_CREATION_UNVERIFIED", r.stdout)

    def test_frozen_oracle_mutation_without_approval(self):
        """既有测试 oracle 被放宽/反转但无 behavior_change_id → FAIL。"""
        tc = self.write("testcase/s1.md", "预期：点击新话题创建新 UUID Session")
        self.init([{"scenario_id": "S-1", "required": True}],
                  testcase_files=[tc])
        with open(tc, "w", encoding="utf-8") as f:
            f.write("预期：同一 Session 新 root（same-session）")  # 反转 oracle
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FROZEN_ORACLE_CHANGED", r.stdout)

    def test_behavior_change_without_approval_artifact(self):
        self.init([{"scenario_id": "S-1", "required": True}],
                  behavior_changes=[{"behavior_change_id": "bc-1",
                                     "old_behavior": "UUID session",
                                     "new_behavior": "same session"}])
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BEHAVIOR_APPROVAL_REQUIRED", r.stdout)

    def test_audit_stale_after_fact_change(self):
        """full-audit 后结果变更 → 旧审计 PASS 失效。"""
        self.full_pass_run()
        r = self.finalize()
        self.assertEqual(r.returncode, 0)
        self.record("S-1", result="fail")  # 审计后又跑出失败
        r = self.finalize()
        self.assertEqual(r.returncode, 1)
        self.assertIn("AUDITOR_INPUT_STALE", r.stdout)
        rr = run_gate(["render", "--run-dir", self.run_dir])
        self.assertEqual(rr.returncode, 1)
        self.assertIn("RECEIPT_STALE", rr.stdout)

    def test_invalidate_receipt(self):
        self.full_pass_run()
        self.assertEqual(self.finalize().returncode, 0)
        r = run_gate(["invalidate", "--run-dir", self.run_dir,
                      "--reason", "生产缺陷：新话题仍复用 Session"])
        self.assertEqual(r.returncode, 0)
        rr = run_gate(["render", "--run-dir", self.run_dir])
        self.assertEqual(rr.returncode, 1)
        self.assertIn("RECEIPT_STALE", rr.stdout)

    def test_release_unit_too_large(self):
        """计划超复杂度预算未拆 slice → FAIL（Companion: 16 MUST AC / 17 Task / 4676 行）。"""
        self.init([{"scenario_id": "S-1", "required": True}],
                  release_unit={"must_ac_count": 16, "task_count": 17,
                                "plan_lines": 4676})
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RELEASE_UNIT_TOO_LARGE", r.stdout)

    def test_required_lane_closure(self):
        """fresh lane PASS、history lane 未执行 → FAIL。"""
        self.init([{"scenario_id": "S-1", "required": True,
                    "required_lanes": ["fresh", "history-upgrade"]}])
        self.record("S-1", lane="fresh")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RISK_CLOSURE_MISSING", r.stdout)

    def test_stochastic_sampling(self):
        """高风险非确定性场景 1/3 成功 → 采样不足，不得 SHIP。"""
        self.init([{"scenario_id": "S-1", "required": True, "min_root_runs": 2}])
        self.record("S-1", result="fail")
        self.record("S-1", result="fail")
        self.record("S-1", result="pass")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        # roots 含 fail → 场景 FAIL → REQUIRED_SCENARIO_NOT_RUN；未解释失败不被最后一次成功覆盖
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stdout)

    def test_stochastic_single_run_insufficient(self):
        self.init([{"scenario_id": "S-1", "required": True, "min_root_runs": 2}])
        self.record("S-1")  # 只跑 1 次
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("STABILITY_SAMPLES_INSUFFICIENT", r.stdout)

    def test_retry_does_not_count_as_root(self):
        """retry/continuation 不能冒充独立场景执行。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", kind="retry")
        self.record("S-1", kind="continuation")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stdout)

    def test_positive_value_needs_business_terminal(self):
        """engine completed 但业务终态 insufficient → 不算正向 PASS。"""
        self.init([{"scenario_id": "S-1", "required": True,
                    "gate_type": "positive-value"}])
        self.record("S-1", engine_terminal="completed",
                    business_terminal="insufficient")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stdout)

    def test_adapter_unknown_blocks(self):
        """运行旧 binary/身份无法闭环（adapter UNKNOWN）→ FAIL。"""
        self.init([{"scenario_id": "S-1", "required": True}],
                  runtime_attestation={"adapter_status": "UNKNOWN"})
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_record_run_rejects_unknown_scenario(self):
        """不许测后补场景。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario",
                      "S-99", "--kind", "root", "--result", "pass"])
        self.assertEqual(r.returncode, 2)

    # ---------- Companion 历史 dogfood ----------

    def test_companion_history_dogfood_three_conflicts(self):
        """normalized fixture 复刻 2026-07-24 Companion 计划的真实矛盾：
        manual-test = PARTIAL/BLOCKED/NOT RUN，manual-results = 6/6 PASS，
        task16-delivery-audit = 100% COMPLETE / SHIP。
        必须依次暴露三个具体冲突码，不能只返回泛化错误。"""
        scenarios = [{"scenario_id": "S-%d" % i, "required": True} for i in range(1, 7)]
        self.init(scenarios, run_id="companion-2026-07-24-dogfood",
                  release_unit={"must_ac_count": 16, "task_count": 17,
                                "plan_lines": 4676})
        # 唯一真实执行过的只有 S-1（终点式 E2E）；S-2~S-5、S-6 NOT RUN
        self.record("S-1")
        # 冻结 testcase 头声明 PARTIAL/BLOCKED；RESULTS 声称 6/6 PASS
        for i in range(1, 7):
            run_gate(["declare-status", "--run-dir", self.run_dir,
                      "--source", "evidence/manual-results.md",
                      "--scenario", "S-%d" % i, "--status", "PASS"])
        run_gate(["declare-status", "--run-dir", self.run_dir,
                  "--source", "testcase/manual-test.md",
                  "--scenario", "S-2", "--status", "NOT RUN"])
        # 互相引用的两份汇总（manual-results ↔ task16-delivery-audit）
        self.artifact("artifacts/manual-results.md", "6/6 PASS，详见 delivery-audit")
        self.artifact("artifacts/task16-delivery-audit.md",
                      "100% COMPLETE / SHIP，真人证据见 manual-results")
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                  "artifacts/manual-results.md", "--kind", "derived",
                  "--id", "ev-results", "--depends-on", "ev-audit"])
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                  "artifacts/task16-delivery-audit.md", "--kind", "derived",
                  "--id", "ev-audit", "--depends-on", "ev-results"])
        run_gate(["set-delivery", "--run-dir", self.run_dir,
                  "--verdict", "SHIP"])
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        for code in ("REQUIRED_SCENARIO_NOT_RUN", "STATUS_CONFLICT",
                     "DELIVERY_VERDICT_CONTRADICTS_LEDGER"):
            self.assertIn(code, r.stdout,
                          "dogfood 必须暴露 %s，实际输出:\n%s" % (code, r.stdout))
        self.assertIn("EVIDENCE_DEPENDENCY_CYCLE", r.stdout)
        self.assertIn("RELEASE_UNIT_TOO_LARGE", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "gate-receipt.json")))


class TimingTestCase(GateTestCase):
    """timing contract（slice-1a plan §2）与诊断排序（§3）。"""

    def test_exec_mode_measures_monotonic(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "phase-4", "--task", "t", "--test-count", "1",
                      "--activity-class", "automated_test",
                      "--exec", "--", sys.executable, "-c", "pass"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("measured=true", r.stdout)
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            t = json.load(f)["timing"][0]
        self.assertTrue(t["measured"])
        self.assertGreaterEqual(t["elapsed_ms"], 0)
        self.assertTrue(t["started_at"].endswith("Z"))

    def test_exec_failure_propagates_exit_code(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "phase-4", "--activity-class", "automated_test",
                      "--exec", "--", sys.executable, "-c", "import sys; sys.exit(7)"])
        self.assertEqual(r.returncode, 7)  # 如实透传，但 timing fact 已入账
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["timing"]), 1)

    def test_declared_mode_forced_unmeasured(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "phase-4", "--activity-class", "manual_e2e",
                      "--declared-start", "2026-07-27T09:00:00Z",
                      "--declared-end", "2026-07-27T09:10:00Z"])
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            t = json.load(f)["timing"][0]
        self.assertFalse(t["measured"])
        self.assertEqual(t["elapsed_ms"], 600000)

    def test_declared_rejects_bad_rfc3339_and_negative(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "p", "--activity-class", "manual_e2e",
                      "--declared-start", "2026/07/27 09:00",
                      "--declared-end", "2026-07-27T09:10:00Z"])
        self.assertEqual(r.returncode, 2)
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "p", "--activity-class", "manual_e2e",
                      "--declared-start", "2026-07-27T09:10:00Z",
                      "--declared-end", "2026-07-27T09:00:00Z"])
        self.assertEqual(r.returncode, 2)

    def test_activity_class_and_wait_reason_enforced(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "p", "--activity-class", "coffee_break",
                      "--declared-start", "2026-07-27T09:00:00Z",
                      "--declared-end", "2026-07-27T09:01:00Z"])
        self.assertEqual(r.returncode, 2)
        # provider_wait 缺 wait_reason → 拒绝
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "p", "--activity-class", "provider_wait",
                      "--declared-start", "2026-07-27T09:00:00Z",
                      "--declared-end", "2026-07-27T09:01:00Z"])
        self.assertEqual(r.returncode, 2)
        # 非 wait 类给了 wait_reason → 拒绝
        r = run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "p", "--activity-class", "implementation",
                      "--wait-reason", "quota_limit",
                      "--declared-start", "2026-07-27T09:00:00Z",
                      "--declared-end", "2026-07-27T09:01:00Z"])
        self.assertEqual(r.returncode, 2)

    def test_timing_gap_advisory_does_not_block(self):
        self.full_pass_run()
        for s, e in (("2026-07-27T09:00:00Z", "2026-07-27T09:05:00Z"),
                     ("2026-07-27T13:00:00Z", "2026-07-27T13:05:00Z")):  # 中隔 >120min
            run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "phase-4", "--activity-class", "manual_e2e",
                      "--declared-start", s, "--declared-end", e])
        self.audit_pass()  # timing 追加改变了 facts，须重审
        r = self.finalize()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # advisory 不拦截
        self.assertIn("ADVISORY TIMING_GAP", r.stdout)
        rr = run_gate(["render", "--run-dir", self.run_dir])
        self.assertEqual(rr.returncode, 0, rr.stdout)
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            report = f.read()
        self.assertIn("耗时分解", report)
        self.assertIn("manual_e2e", report)

    def test_schema_major_mismatch_rejected(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        p = os.path.join(self.run_dir, "plan-test-run.json")
        with open(p, encoding="utf-8") as f:
            ledger = json.load(f)
        ledger["schema_version"] = "2.0.0"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ledger, f)
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("SCHEMA_INVALID", r.stdout)

    def test_diag_order_canonical_and_idempotent(self):
        """Companion 组合下 DIAG 顺序 = canonical 序，且两次重跑逐字节相同。"""
        scenarios = [{"scenario_id": "S-%d" % i, "required": True} for i in range(1, 4)]
        self.init(scenarios, release_unit={"must_ac_count": 16})
        self.record("S-1")
        run_gate(["declare-status", "--run-dir", self.run_dir,
                  "--source", "results.md", "--scenario", "S-2", "--status", "PASS"])
        run_gate(["set-delivery", "--run-dir", self.run_dir, "--verdict", "SHIP"])
        r1 = self.finalize(check_only=True)
        r2 = self.finalize(check_only=True)
        self.assertEqual(r1.stdout, r2.stdout)  # 幂等
        lines = [l for l in r1.stdout.splitlines() if l.startswith("DIAG")]
        codes = [l.split()[1].rstrip(":") for l in lines]
        self.assertEqual(codes, sorted(codes, key=lambda c:
            ["REQUIRED_SCENARIO_NOT_RUN", "STATUS_CONFLICT",
             "DELIVERY_VERDICT_CONTRADICTS_LEDGER", "RELEASE_UNIT_TOO_LARGE"].index(c)))
        # 类别内第二键：S-2 在 S-3 之前
        req = [l for l in lines if "REQUIRED_SCENARIO_NOT_RUN" in l]
        self.assertIn("S-2", req[0])
        self.assertIn("S-3", req[1])

    def test_checkpoint_recorded(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = run_gate(["checkpoint", "--run-dir", self.run_dir,
                      "--slice", "slice-1a", "--note", "测试中"])
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            evs = [e for e in json.load(f)["events"] if e["type"] == "checkpoint"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["slice"], "slice-1a")


FIXTURES_DIR = os.path.join(os.path.dirname(HERE), "fixtures", "gate")


def _verify_companion_normalization(fx, sources, steps):
    """在来源可达的机器上复核 normalized fixture 与三份历史原文逐项对应。"""
    manifest = json.loads(read_utf8(os.path.join(fx, "manifest.json")))
    expected_scenarios = ["S-1", "S-2", "S-3", "S-4", "S-5", "S-8"]
    actual_scenarios = [s["scenario_id"] for s in manifest["scenarios"]]
    assert actual_scenarios == expected_scenarios, (
        "normalized 场景集合须对应历史 required 真人场景 S-1～S-5、S-8: %r"
        % actual_scenarios)

    by_name = {os.path.basename(s["source_path"]): s["source_path"] for s in sources}
    manual_test = read_utf8(by_name["manual-test.md"])
    manual_results = read_utf8(by_name["manual-results.md"])
    delivery_audit = read_utf8(by_name["task16-delivery-audit.md"])
    compact_test = " ".join(manual_test.split())
    assert "S-1 只能 记 `PARTIAL / BLOCKED`" in compact_test
    assert "S-2～S-5/S-8 保持 `NOT RUN`" in compact_test
    assert "真人 required 场景：S-1～S-5、S-8，`6/6 PASS`" in manual_results
    for sid in expected_scenarios:
        assert any(line.startswith("| %s " % sid) and line.rstrip().endswith("| PASS |")
                   for line in manual_results.splitlines()), (
                       "manual-results.md 缺少 %s 的 PASS 行" % sid)
    assert "结论：`DECISION: SHIP`" in delivery_audit
    assert "| S-1～S-5、S-8 required 真人场景 | `6/6 PASS` |" in delivery_audit

    declarations = [
        (step["args"][step["args"].index("--source") + 1],
         step["args"][step["args"].index("--scenario") + 1],
         step["args"][step["args"].index("--status") + 1])
        for step in steps if step["cmd"] == "declare-status"
    ]
    expected_declarations = [
        ("evidence/manual-results.md", sid, "PASS") for sid in expected_scenarios
    ] + [
        ("testcase/manual-test.md", "S-1", "PARTIAL"),
    ] + [
        ("testcase/manual-test.md", sid, "NOT RUN")
        for sid in ["S-2", "S-3", "S-4", "S-5", "S-8"]
    ]
    assert declarations == expected_declarations, (
        "declared_statuses 未与历史状态行一一对应:\n实际=%r\n期望=%r"
        % (declarations, expected_declarations))
    root_runs = [step for step in steps if step["cmd"] == "record-run"]
    assert len(root_runs) == 1
    assert root_runs[0]["args"] == [
        "--scenario", "S-1", "--kind", "root", "--result", "pass"]
    deliveries = [step for step in steps if step["cmd"] == "set-delivery"]
    assert len(deliveries) == 1 and deliveries[0]["args"] == ["--verdict", "SHIP"]


def replay_fixture(name, run_dir):
    """按 fixture-contract.md §1 回放：终结命令由 steps.jsonl 显式声明。
    返回 (终结命令结果, provenance_unverified)。"""
    fx = os.path.join(FIXTURES_DIR, name)
    os.makedirs(os.path.join(run_dir, "artifacts"), exist_ok=True)
    art = os.path.join(fx, "artifacts")
    if os.path.isdir(art):
        for f in os.listdir(art):
            shutil.copy(os.path.join(art, f), os.path.join(run_dir, "artifacts", f))
    for f in ("auditor-input.json", "auditor-output.json"):
        if os.path.exists(os.path.join(fx, f)):
            shutil.copy(os.path.join(fx, f), os.path.join(run_dir, f))
    unverified = False
    prov = os.path.join(fx, "provenance.json")
    steps = []
    with open(os.path.join(fx, "steps.jsonl"), encoding="utf-8") as fh:
        steps = [json.loads(line) for line in fh if line.strip()]
    if os.path.exists(prov):
        with open(prov, encoding="utf-8") as fh:
            data = json.load(fh)
        unverified = any(s.get("source_sha256") is None for s in data.get("sources", []))
        if unverified:
            print("PROVENANCE: UNVERIFIED (%s)" % name)
        else:
            for source in data.get("sources", []):
                assert source.get("captured_at"), "provenance 缺 captured_at"
                assert source.get("captured_on"), "provenance 缺 captured_on"
                path = source["source_path"]
                if os.path.exists(path):
                    assert sha256_file(path) == source["source_sha256"], (
                        "provenance hash 不匹配: %s" % path)
            if name == "fail-companion-conflict" and all(
                    os.path.exists(s["source_path"]) for s in data.get("sources", [])):
                _verify_companion_normalization(fx, data["sources"], steps)
            print("PROVENANCE: VERIFIED (%s)" % name)
    last = None
    for step in steps:
        args = [a.replace("{FIXTURE}", fx).replace("{PYTHON}", sys.executable)
                for a in step["args"]]
        last = run_gate([step["cmd"], "--run-dir", run_dir] + args, cwd=fx)
        if step["cmd"] not in ("finalize", "render"):
            assert last.returncode == 0, "%s 步骤失败: %s\n%s" % (
                name, step["cmd"], last.stderr)
    return last, unverified


class FixtureReplayTestCase(unittest.TestCase):
    """静态 fixture 回放（fixture-contract.md）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-fixture-")
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assert_expected(self, name, result):
        fx = os.path.join(FIXTURES_DIR, name)
        with open(os.path.join(fx, "expected-diagnostics.txt"), encoding="utf-8") as f:
            expected = [l for l in f.read().splitlines() if l.strip()]
        # 只比对 DIAG（error）行；ADVISORY 含运行时实测值（如 TIMING_GAP 分钟数），
        # 不可逐字节冻结（fixture-contract.md §1）
        got = [l for l in result.stdout.splitlines() if l.startswith("DIAG")]
        self.assertEqual(got, expected,
                         "%s DIAG 序列与冻结期望不符:\n%s" % (name, result.stdout))
        with open(os.path.join(fx, "expected-state.txt"), encoding="utf-8") as f:
            state = f.read().strip()
        self.assertIn(state, result.stdout)

    def test_pass_minimal(self):
        r, unverified = replay_fixture("pass-minimal", self.run_dir)
        self.assertFalse(unverified)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_expected("pass-minimal", r)
        self.assertIn("GATE RECEIPT:", r.stdout)

    def test_fail_companion_conflict(self):
        r, unverified = replay_fixture("fail-companion-conflict", self.run_dir)
        self.assertFalse(unverified, "1D-delta 后 provenance 必须已采集并复核")
        self.assertEqual(r.returncode, 1)
        self.assert_expected("fail-companion-conflict", r)
        # handoff §10 冻结的前三类顺序
        codes = [l.split()[1].rstrip(":") for l in r.stdout.splitlines()
                 if l.startswith("DIAG")]
        dedup = []
        for c in codes:
            if c not in dedup:
                dedup.append(c)
        self.assertEqual(dedup[:3], ["REQUIRED_SCENARIO_NOT_RUN", "STATUS_CONFLICT",
                                     "DELIVERY_VERDICT_CONTRADICTS_LEDGER"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
