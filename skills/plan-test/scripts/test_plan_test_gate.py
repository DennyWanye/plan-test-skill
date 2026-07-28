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

FIXTURE_EXIT = 3  # fixture-only run 通过（合成数据，非交付通过）

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


class GateHarness(unittest.TestCase):
    """只放 setUp/helpers，不含 test_*；各测试类继承它，避免用例被重复继承执行。"""

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
            "applicability": self.applicability(),
        }
        acc = self.write("acceptance.md", "AC-1 必须：点击新话题创建新 UUID Session\n")
        m["acceptance_file"] = acc
        m.update(extra)
        return self.write("manifest.json", json.dumps(m, ensure_ascii=False))

    def applicability(self, **override):
        """默认：三维皆判「不适用」并附理由——单测被测对象是确定性 CLI。
        需要测条件门兑现的用例用 override 覆盖。"""
        base = {
            "input_sensitive": {"value": False, "decided_by": "agent",
                                "rationale": "被测对象是确定性 CLI，输出不随输入语义变化"},
            "llm_payload_driven": {"value": False, "decided_by": "agent",
                                   "rationale": "无 LLM 载荷驱动端侧状态机"},
            "stateful_init": {"value": False, "decided_by": "agent",
                              "rationale": "无异步注册服务或登录态依赖"},
        }
        base.update(override)
        return base

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
                      "--engine", "opus-auditor",
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



class GateTestCase(GateHarness):
    # ---------- PASS path ----------

    def test_full_pass_path_and_receipt_idempotent(self):
        self.full_pass_run()
        r1 = self.finalize()
        self.assertEqual(r1.returncode, FIXTURE_EXIT, r1.stdout + r1.stderr)
        self.assertIn("FIXTURE-ONLY", r1.stdout)
        self.assertIn("GATE RECEIPT:", r1.stdout)
        with open(os.path.join(self.run_dir, "gate-receipt.json"), encoding="utf-8") as f:
            receipt1 = json.load(f)
        r2 = self.finalize()  # 幂等：同输入同 digest，复用首次 finalized_at
        self.assertEqual(r2.returncode, FIXTURE_EXIT)
        with open(os.path.join(self.run_dir, "gate-receipt.json"), encoding="utf-8") as f:
            receipt2 = json.load(f)
        self.assertEqual(receipt1["content_digest"], receipt2["content_digest"])
        self.assertEqual(receipt1["finalized_at"], receipt2["finalized_at"])
        self.assertTrue(receipt1["fixture_only"])
        rr = run_gate(["render", "--run-dir", self.run_dir])
        self.assertEqual(rr.returncode, FIXTURE_EXIT, rr.stdout)
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
        self.assertEqual(r.returncode, FIXTURE_EXIT)
        self.record("S-1", result="fail")  # 审计后又跑出失败
        r = self.finalize()
        self.assertEqual(r.returncode, 1)
        self.assertIn("AUDITOR_INPUT_STALE", r.stdout)
        rr = run_gate(["render", "--run-dir", self.run_dir])
        self.assertEqual(rr.returncode, 1)
        self.assertIn("RECEIPT_STALE", rr.stdout)

    def test_invalidate_receipt(self):
        self.full_pass_run()
        self.assertEqual(self.finalize().returncode, FIXTURE_EXIT)
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


class TimingTestCase(GateHarness):
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
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout + r.stderr)  # advisory 不拦截
        self.assertIn("ADVISORY TIMING_GAP", r.stdout)
        rr = run_gate(["render", "--run-dir", self.run_dir])
        self.assertEqual(rr.returncode, FIXTURE_EXIT, rr.stdout)
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


class ApplicabilityTestCase(GateHarness):
    """适用性判定入账门：堵"口头判不适用 → 四道条件门合法消失"。"""

    def ledger(self):
        with open(os.path.join(self.run_dir, "plan-test-run.json")) as f:
            return json.load(f)

    def test_undeclared_blocks(self):
        """完全不声明适用性 → 拦截（此前是默认状态，无人可查）。"""
        self.init([{"scenario_id": "S-1", "required": True}], applicability={})
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("APPLICABILITY_UNDECLARED", r.stdout)
        self.assertEqual(r.stdout.count("APPLICABILITY_UNDECLARED"), 3)  # 三个维度各一条

    def test_init_warns_when_undeclared(self):
        r = self.init([{"scenario_id": "S-1", "required": True}], applicability={})
        self.assertIn("APPLICABILITY_UNDECLARED", r.stdout)

    def test_false_declaration_needs_rationale(self):
        """判「不适用」必须写理由——理由本身进 receipt digest，事后可追责。"""
        self.init([{"scenario_id": "S-1", "required": True}],
                  applicability=self.applicability(
                      input_sensitive={"value": False, "decided_by": "agent", "rationale": "不用"}))
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("缺少判定理由", r.stdout)

    def test_decided_by_must_be_agent_or_user(self):
        self.init([{"scenario_id": "S-1", "required": True}],
                  applicability=self.applicability(
                      stateful_init={"value": False, "decided_by": "系统",
                                     "rationale": "无异步注册服务或登录态依赖"}))
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("decided_by", r.stdout)

    def test_input_sensitive_needs_distinct_classes(self):
        """判「适用」就必须真的兑现：语义不等价输入类别 <3 → FAIL。"""
        self.init([{"scenario_id": "S-1", "required": True, "gate_type": "positive-value",
                    "input_class": "自然提问"},
                   {"scenario_id": "S-2", "required": True, "input_class": "自然提问"}],
                  applicability=self.applicability(
                      input_sensitive={"value": True, "decided_by": "user",
                                       "rationale": "LLM 调研 agent，输出随输入语义变化"}))
        self.record("S-1", business_terminal="completed+valid")
        self.record("S-2")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("APPLICABILITY_GATE_UNSATISFIED", r.stdout)
        self.assertIn("语义不等价输入", r.stdout)

    def test_input_sensitive_needs_positive_value_scenario(self):
        """全是负向安全场景 → 「诚实降级成功」不等于产品质量 PASS。"""
        scen = [{"scenario_id": "S-%d" % i, "required": True,
                 "gate_type": "negative-safety", "input_class": "类别-%d" % i}
                for i in (1, 2, 3)]
        self.init(scen, applicability=self.applicability(
            input_sensitive={"value": True, "decided_by": "user",
                             "rationale": "检索增强问答，输出随输入语义变化"}))
        for s in scen:
            self.record(s["scenario_id"])
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("positive-value", r.stdout)

    def test_llm_payload_driven_needs_sampling(self):
        self.init([{"scenario_id": "S-1", "required": True}],
                  applicability=self.applicability(
                      llm_payload_driven={"value": True, "decided_by": "agent",
                                          "rationale": "LLM 生成题卡驱动端侧测验状态机"}))
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("min_root_runs", r.stdout)

    def test_stateful_init_needs_cold_start(self):
        self.init([{"scenario_id": "S-1", "required": True}],
                  applicability=self.applicability(
                      stateful_init={"value": True, "decided_by": "agent",
                                     "rationale": "功能依赖异步注册的同步服务与登录态"}))
        self.record("S-1")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cold_start", r.stdout)

    def test_satisfied_matrix_passes(self):
        """正样本：判「适用」且矩阵真的兑现 → 不产生适用性诊断（防门只会拒绝）。"""
        scen = [{"scenario_id": "S-1", "required": True, "gate_type": "positive-value",
                 "input_class": "自然提问", "min_root_runs": 2, "cold_start": True},
                {"scenario_id": "S-2", "required": True, "input_class": "专业术语"},
                {"scenario_id": "S-3", "required": True, "gate_type": "negative-safety",
                 "input_class": "对抗输入"}]
        self.init(scen, applicability={
            "input_sensitive": {"value": True, "decided_by": "user",
                                "rationale": "LLM 调研 agent，输出质量随输入语义变化"},
            "llm_payload_driven": {"value": True, "decided_by": "user",
                                   "rationale": "报告卡片由 LLM 结构化载荷驱动渲染"},
            "stateful_init": {"value": True, "decided_by": "user",
                              "rationale": "依赖登录态与异步注册的检索服务"}})
        self.record("S-1", business_terminal="completed+valid")
        self.record("S-1", business_terminal="completed+valid")  # min_root_runs=2
        self.record("S-2")
        self.record("S-3")
        r = self.finalize(check_only=True)
        self.assertNotIn("APPLICABILITY", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_declaration_lands_in_report(self):
        """判定必须在人读报告里可见，否则等于没入账。"""
        self.full_pass_run()
        self.finalize()
        run_gate(["render", "--run-dir", self.run_dir])
        with open(os.path.join(self.run_dir, "report.md")) as f:
            report = f.read()
        self.assertIn("适用性判定", report)
        self.assertIn("input_sensitive", report)


class IntegrityTestCase(GateHarness):
    """账本完整性链：绕过 CLI 手改账本会被发现。"""

    def read_ledger(self):
        with open(os.path.join(self.run_dir, "plan-test-run.json")) as f:
            return json.load(f)

    def write_ledger(self, data):
        with open(os.path.join(self.run_dir, "plan-test-run.json"), "w") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_handedited_result_detected(self):
        """把 fail 手改成 pass（不经 CLI）→ LEDGER_TAMPERED。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="fail")
        led = self.read_ledger()
        led["runs"][0]["result"] = "pass"
        self.write_ledger(led)
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("LEDGER_TAMPERED", r.stdout)

    def test_dropped_chain_entry_detected(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1")
        led = self.read_ledger()
        led["integrity"]["log"].pop()
        self.write_ledger(led)
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("LEDGER_TAMPERED", r.stdout)

    def test_tamper_detection_survives_further_writes(self):
        """篡改检测不是一次性的：改完再敲一条无害命令，不能把痕迹盖过去。

        独立审计实测过旧行为——手改 `runs[].result` fail→pass 后跑一次 `checkpoint`，
        新条目拿被篡改的快照重新盖章，`LEDGER_TAMPERED` 永久消失，随后 audit→finalize
        拿到有效 receipt。成本只是"改一行 + 多敲一条命令"。
        """
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="fail")
        led = self.read_ledger()
        led["runs"][0]["result"] = "pass"
        self.write_ledger(led)
        # 任何后续写入都必须被拒绝
        r = run_gate(["checkpoint", "--run-dir", self.run_dir, "--note", "掩盖"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("LEDGER_TAMPERED", r.stderr)
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                      "--kind", "root", "--result", "pass"])
        self.assertEqual(r.returncode, 2)
        # 篡改痕迹仍在
        out = self.finalize(check_only=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("LEDGER_TAMPERED", out.stdout)

    def test_deleting_chain_is_not_an_escape_hatch(self):
        """删掉 integrity 键再写一条命令，不能重建出一条自洽的新链。

        独立审计实测过旧行为：同一次编辑里把 result 改掉 + `del d["integrity"]`，
        下一条 CLI 写入就会在被篡改的事实上重建全新链，随后拿到有效 receipt、hook exit 0。
        成本只是"改一行 + 删一个键 + 敲一条命令"——不是文档所说的"离线重算整条链"。
        """
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="fail")
        led = self.read_ledger()
        led["runs"][0]["result"] = "pass"
        del led["integrity"]
        self.write_ledger(led)
        r = run_gate(["checkpoint", "--run-dir", self.run_dir, "--note", "重建链"])
        self.assertEqual(r.returncode, 2, "删链之后仍可写入")
        self.assertIn("LEDGER_TAMPERED", r.stderr)
        out = self.finalize(check_only=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("LEDGER_TAMPERED", out.stdout)

    def test_rebuilt_chain_without_init_is_rejected(self):
        """即便手工造出一条自洽的链，首条不是 init（或 genesis 不符）也不作数。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="fail")
        led = self.read_ledger()
        led["runs"][0]["result"] = "pass"
        # 手工重算一条"自洽"的链，但只从 checkpoint 开始
        import hashlib
        facts = {k: v for k, v in led.items() if k not in ("revision", "integrity")}
        fd = hashlib.sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
        chain = hashlib.sha256(("" + "checkpoint" + fd).encode()).hexdigest()
        led["integrity"] = {"chain": chain,
                            "log": [{"seq": 1, "op": "checkpoint", "facts_digest": fd,
                                     "chain": chain, "at": "2026-07-28T00:00:00+0800"}]}
        self.write_ledger(led)
        out = self.finalize(check_only=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("LEDGER_TAMPERED", out.stdout)

    def test_truncated_chain_is_rejected(self):
        """把链压成一条 init 同样不作数——链长必须对得上账本里的事实条数。

        独立审计的原探针：`d.pop('integrity'); integrity_append(d, 'init')` 两行，
        此后全走正规 CLI 也能拿到 receipt。只查"链首是 init"拦不住它。
        """
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="fail")
        self.artifact("artifacts/x.log", "log")
        self.attach("artifacts/x.log", scenario="S-1")
        led = self.read_ledger()
        led["runs"][0]["result"] = "pass"
        # 用被测系统自己的函数重建一条"自洽"的单条链
        sys.path.insert(0, HERE)
        import importlib
        gate = importlib.import_module("plan_test_gate")
        led.pop("integrity", None)
        gate.integrity_append(led, "init")
        self.write_ledger(led)
        out = self.finalize(check_only=True)
        self.assertEqual(out.returncode, 1, "截断成一条 init 的链被放行了")
        self.assertIn("LEDGER_TAMPERED", out.stdout)
        # 后续写入同样被拒
        r = run_gate(["checkpoint", "--run-dir", self.run_dir, "--note", "继续"])
        self.assertEqual(r.returncode, 2)

    def test_cli_writes_keep_chain_valid(self):
        """正样本：全程走 CLI 的账本链必须自洽。"""
        self.full_pass_run()
        r = self.finalize()
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout)
        self.assertNotIn("LEDGER_TAMPERED", r.stdout)


class AuditorIndependenceTestCase(GateHarness):
    """审计产物与入账结论一致性 + 独立性曝光。"""

    def test_cli_cannot_overrule_audit_artifact(self):
        """审计报告写 FAIL、命令行敲 PASS → 直接拒绝（exit 2）。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1")
        self.artifact("auditor-input.json", '{"frozen": true}')
        self.artifact("auditor-output.json", '{"verdict": "FAIL", "why": "AC-2 未测"}')
        r = run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                      "--engine", "opus-auditor", "--input", "auditor-input.json",
                      "--output", "auditor-output.json"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("不许命令行改判", r.stderr)

    def test_verdict_line_form_also_checked(self):
        """非 JSON 的审计产物按末行 VERDICT: X 解析（与子代理结论行契约一致）。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1")
        self.artifact("auditor-input.json", '{"frozen": true}')
        self.artifact("auditor-output.json", "审计正文……\nVERDICT: FAIL\n")
        r = run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                      "--engine", "opus-auditor", "--input", "auditor-input.json",
                      "--output", "auditor-output.json"])
        self.assertEqual(r.returncode, 2)

    def test_self_audit_exposed_as_advisory(self):
        """自审自判不拦截，但必须在输出与报告里曝光。"""
        self.init([{"scenario_id": "S-1", "required": True, "ui": True,
                    "gate_type": "positive-value", "expected_run_created": True}],
                  executor_engine="codex-gpt5.5")
        self.artifact("artifacts/s1.png", "shot")
        self.attach("artifacts/s1.png", scenario="S-1", ui_action=True)
        self.record("S-1", business_terminal="completed+valid",
                    run_id_under_test="run-1", session_id="sess-1")
        self.artifact("auditor-input.json", '{"frozen": true}')
        self.artifact("auditor-output.json", '{"verdict": "PASS"}')
        r = run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                      "--engine", "codex-gpt5.5", "--input", "auditor-input.json",
                      "--output", "auditor-output.json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.finalize()
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout)  # advisory 不拦截
        self.assertIn("ADVISORY AUDITOR_INDEPENDENCE_UNVERIFIED", r.stdout)
        self.assertIn("自审自判", r.stdout)


class RealRepoAttestationTestCase(unittest.TestCase):
    """非 fixture 的真实 git 仓库：内容指纹必须分得清「只是提交」与「内容真变了」。

    这是独立审计实测出的死结（AC-6）：原实现按 HEAD + dirty patch 判定，
    `git commit` 一个字节都不改也会 MISMATCH，于是「测完→提交→finalize」永远过不去，
    而不提交又过不了提交态门。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-realrepo-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write("src.py", "print('v1')\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        self.run_dir = os.path.join(self.repo, "plans", "p", "verification", "run-1")
        os.makedirs(os.path.join(self.run_dir, "artifacts"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git"] + list(args), cwd=self.repo,
                              capture_output=True, text=True)

    def write(self, rel, content):
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def applicability_block(self):
        return {
            "input_sensitive": {"value": False, "decided_by": "agent",
                                "rationale": "确定性脚本，输出不随输入语义变化"},
            "llm_payload_driven": {"value": False, "decided_by": "agent",
                                   "rationale": "无 LLM 载荷驱动端侧状态机"},
            "stateful_init": {"value": False, "decided_by": "agent",
                              "rationale": "无异步注册服务或登录态依赖"},
        }

    def init_real_run(self, **extra):
        manifest = {
            "run_id": "real-1",
            "repo_root": self.repo,
            "source_request_text": "真实仓库门禁验证",
            "acceptance_file": self.write("acceptance.md", "AC-1 必须：脚本可运行\n"),
            "applicability": {
                "input_sensitive": {"value": False, "decided_by": "agent",
                                    "rationale": "确定性脚本，输出不随输入语义变化"},
                "llm_payload_driven": {"value": False, "decided_by": "agent",
                                       "rationale": "无 LLM 载荷驱动端侧状态机"},
                "stateful_init": {"value": False, "decided_by": "agent",
                                  "rationale": "无异步注册服务或登录态依赖"},
            },
            "scenarios": [{"scenario_id": "S-1", "required": True}],
        }
        manifest.update(extra)
        mpath = self.write("manifest.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mpath], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                      "--kind", "root", "--result", "pass"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def check(self):
        return run_gate(["finalize", "--run-dir", self.run_dir, "--check-only"], cwd=self.repo)

    def test_commit_without_content_change_still_passes(self):
        """测完之后把改动提交（内容一字未改）→ 门必须仍然绿。"""
        self.init_real_run()
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        self.git("add", "-A")
        self.git("commit", "-qm", "ship tested content")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_content_change_after_test_is_blocked(self):
        """测完之后改一个字节 → 必须拦（严格性不能因为解死结而丢掉）。"""
        self.init_real_run()
        self.write("src.py", "print('v2')\n")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_committing_run_dir_does_not_invalidate(self):
        """把 run-dir 自身提交进仓库 → 不算内容变化（否则 receipt 会自己打脸自己）。"""
        self.init_real_run()
        self.git("add", "-A")
        self.git("commit", "-qm", "commit including run-dir")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_new_untracked_file_is_content_change(self):
        """新增未跟踪文件也算内容变化——半截提交/漏跟踪的路由文件正是这样漏的。"""
        self.init_real_run()
        self.write("routes.py", "# 新增但未提交的接线层\n")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)


class ReAttestTestCase(RealRepoAttestationTestCase):
    """收尾期改动的合法出口：re-attest。doc-only 放行，behavioral 强制重测。

    第二轮独立审计实测：没有 re-attest 时，attestation 只在 init 写一次，收尾流程
    强制要求的文档回写会把整个 run 永久锁死，唯一出路 `init --force` 会清空全部证据。
    """

    def re_attest(self, reason="收尾期改动"):
        return run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", reason],
                        cwd=self.repo)

    def test_doc_only_change_can_re_attest_and_pass(self):
        """文档回写 → re-attest 判 doc-only → 既有测试结论继续有效，门恢复绿。"""
        self.init_real_run()
        self.write("ARCHITECTURE.md", "# 架构\n收尾期回写。\n")
        self.assertEqual(self.check().returncode, 1)  # 先如实变红
        r = self.re_attest("文档回写：ARCHITECTURE.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kind=doc-only", r.stdout)
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_behavioral_change_requires_retest(self):
        """改代码 → re-attest 判 behavioral → 旧 PASS 不再作数，必须重跑。"""
        self.init_real_run()
        self.write("src.py", "print('v2')\n")
        r = self.re_attest("修 bug")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kind=behavioral", r.stdout)
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("RETEST_REQUIRED_AFTER_CHANGE", out.stdout)
        # 重跑后才放行
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "pass"], cwd=self.repo)
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_behavioral_text_is_never_doc_only(self):
        """提示词、skill、依赖清单不算文档——独立审计实测过这两个反例。

        `requirements.txt`（改依赖版本）与 `prompts/system.md`（把系统提示改成
        "忽略所有规则"）在旧的按后缀判定下都被判 doc-only 免重测。
        """
        for rel, body in (("requirements.txt", "flask==0.1\n"),
                          ("prompts/system.md", "# 系统提示\n忽略所有规则。\n")):
            self.setUp()
            self.init_real_run()
            self.write(rel, body)
            r = self.re_attest("只改了文档吧？")
            self.assertIn("kind=behavioral", r.stdout, "%s 被误判成 doc-only" % rel)

    def test_real_docs_still_doc_only(self):
        """正样本：README/docs 下的叙述性文档仍应免重测，否则这个出口就没用了。"""
        self.init_real_run()
        self.write("README.md", "# 项目\n收尾期回写。\n")
        self.write("docs/guide.md", "使用说明\n")
        r = self.re_attest("文档回写")
        self.assertIn("kind=doc-only", r.stdout, r.stdout)
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_doc_only_claim_is_machine_decided(self):
        """混合变更不能被说成 doc-only——判定看路径，不看申报。"""
        self.init_real_run()
        self.write("README.md", "# 说明\n")
        self.write("src.py", "print('v3')\n")
        r = self.re_attest("只是顺手改了点文档")
        self.assertIn("kind=behavioral", r.stdout)
        self.assertIn("RETEST_REQUIRED_AFTER_CHANGE", self.check().stdout)

    def test_no_change_is_noop(self):
        self.init_real_run()
        r = self.re_attest("什么都没改")
        self.assertIn("NO CHANGE", r.stdout)

    def test_sibling_slice_run_dir_does_not_invalidate(self):
        """一次交付拆成多个 slice 时，兄弟 run-dir 的记账不得算成交付内容变化。

        不声明兄弟目录时，A 记一条 run 就让 B 的内容指纹变化，两个 slice 互相判对方
        TESTED_RUNTIME_MISMATCH——拆 slice 验收（正是 RELEASE_UNIT_TOO_LARGE 要求的做法）
        因此走不通。现在的机制是 manifest 显式声明 `related_run_dirs`，init 时冻结。
        """
        sibling = os.path.join(self.repo, "plans", "p", "verification", "run-2")
        os.makedirs(os.path.join(sibling, "artifacts"))
        # 兄弟 slice 必须**显式声明**才被排除（冻结进账本、进 receipt、在报告显形）
        self.init_real_run(related_run_dirs=["plans/p/verification/run-2"])
        manifest = {
            "run_id": "sibling", "repo_root": self.repo,
            "source_request_text": "兄弟 slice",
            "acceptance_file": os.path.join(self.repo, "acceptance.md"),
            "applicability": {
                "input_sensitive": {"value": False, "decided_by": "agent",
                                    "rationale": "确定性脚本，输出不随输入语义变化"},
                "llm_payload_driven": {"value": False, "decided_by": "agent",
                                       "rationale": "无 LLM 载荷驱动端侧状态机"},
                "stateful_init": {"value": False, "decided_by": "agent",
                                  "rationale": "无异步注册服务或登录态依赖"}},
            "scenarios": [{"scenario_id": "S-2", "required": True}],
        }
        # manifest 必须写在 run-dir 内（PROTOCOL §1 的 run 目录布局）——写到仓库其它地方
        # 就是真的新增交付内容，那时被判 MISMATCH 是正确行为，不是误报。
        mp = os.path.join(sibling, "manifest.json")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", sibling, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        run_gate(["record-run", "--run-dir", sibling, "--scenario", "S-2",
                  "--kind", "root", "--result", "pass"], cwd=self.repo)
        # 兄弟 slice 记账之后，本 slice 仍须通过
        out = self.check()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("TESTED_RUNTIME_MISMATCH", out.stdout)

    def test_exclusion_is_init_order_independent(self):
        """先 init 的 slice 不能被后 init 的 slice 弄红。

        历史上曾按"目录里有没有账本"现算排除，于是 B 一 init 就让自己从 A 的条目里消失，
        A 立刻 TESTED_RUNTIME_MISMATCH。现在排除范围在 init 时冻结（声明式），
        与后续谁先 init 无关。
        """
        sibling = os.path.join(self.repo, "plans", "p", "verification", "run-2")
        os.makedirs(os.path.join(sibling, "artifacts"))
        # B 的 manifest 先就位（内容完整，只是还没 init）——这就是拆 slice 的真实顺序
        pending = {
            "run_id": "sibling2", "repo_root": self.repo,
            "source_request_text": "后 init 的兄弟 slice",
            "acceptance_file": os.path.join(self.repo, "acceptance.md"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-9", "required": True}],
        }
        with open(os.path.join(sibling, "manifest.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(pending, ensure_ascii=False))
        self.init_real_run(related_run_dirs=["plans/p/verification/run-2"])  # A 先 init 并声明
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        manifest = {
            "run_id": "sibling2", "repo_root": self.repo,
            "source_request_text": "后 init 的兄弟 slice",
            "acceptance_file": os.path.join(self.repo, "acceptance.md"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-9", "required": True}],
        }
        with open(os.path.join(sibling, "manifest.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", sibling,
                      "--manifest", os.path.join(sibling, "manifest.json")], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.check()                          # A 仍须绿
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_business_dir_named_verification_is_not_excluded(self):
        """项目里真有一个叫 `verification/` 的业务目录时，它的代码**不得**被排除。

        独立审计实测过：只按路径形态排除时，`src/verification/rules/engine.py` 在 audit 之后
        被改成相反实现、还加了后门文件，finalize 仍输出逐字相同的 receipt、exit 0。
        """
        os.makedirs(os.path.join(self.repo, "src", "verification", "rules"))
        self.write("src/verification/rules/engine.py", "def allow(): return True\n")
        self.init_real_run()
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        self.write("src/verification/rules/engine.py", "def allow(): return False\n")
        r = self.check()
        self.assertEqual(r.returncode, 1, "业务目录被误排除了")
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_business_file_named_manifest_is_still_content(self):
        """业务文件哪怕取名 manifest.json / report.md，也不得因文件名被排除。

        独立审计实测：按文件名排除时，`src/verification/cfg/manifest.json` 里的
        `allow_all: true` 在 audit 之后被改掉，receipt 逐字不变、exit 0。
        """
        os.makedirs(os.path.join(self.repo, "src", "verification", "cfg"))
        self.write("src/verification/cfg/manifest.json", '{"allow_all": false}')
        self.write("src/verification/cfg/report.md", "限额 100\n")
        self.init_real_run()
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        self.write("src/verification/cfg/manifest.json", '{"allow_all": true}')
        r = self.check()
        self.assertEqual(r.returncode, 1, "按文件名排除的洞还在")
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_planted_run_dir_after_receipt_cannot_hide_backdoor(self):
        """拿到 receipt 之后现造一个 run 目录塞后门，必须被发现（无需事前埋设的攻击）。

        独立审计实测：`mkdir -p src/verification/z/artifacts && echo '{}' > src/verification/z/plan-test-run.json`
        再往 artifacts 里放 backdoor.py，finalize 仍输出逐字相同的 receipt、STATE: SHIPPABLE。
        """
        self.init_real_run()
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        os.makedirs(os.path.join(self.repo, "src", "verification", "z", "artifacts"))
        self.write("src/verification/z/plan-test-run.json", "{}")
        self.write("src/verification/z/artifacts/backdoor.py", "import os\nos.system('id')\n")
        r = self.check()
        self.assertEqual(r.returncode, 1, "事后现造 run 目录仍能藏后门")
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_related_run_dirs_cannot_exclude_code(self):
        """related_run_dirs 只能声明 `.../verification/<单层>` 形态的既有目录。"""
        os.makedirs(os.path.join(self.repo, "src"), exist_ok=True)
        self.write("src/app.py", "print('x')\n")
        manifest = {
            "run_id": "bad", "repo_root": self.repo, "source_request_text": "x",
            "acceptance_file": self.write("acceptance.md", "AC-1 必须：可运行\n"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-1", "required": True}],
            "related_run_dirs": ["src"],
        }
        mp = self.write("manifest-bad.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("related_run_dirs", r.stderr)

    def test_fake_manifest_cannot_hide_a_directory(self):
        """在 `.../verification/<x>/` 放一个假 manifest，不能把该目录的真实代码藏掉。

        独立审计实测：`src/verification/hide/manifest.json` 只写 `{"run_id":"x"}`（12 字节），
        同目录 `payments.py` 就从头不进指纹；audit 通过后把返回值改成 STOLEN、再加一个跑
        os.system 的 backdoor.py，finalize 仍 SHIPPABLE、receipt 逐字不变。
        """
        os.makedirs(os.path.join(self.repo, "src", "verification", "hide"))
        self.write("src/verification/hide/manifest.json", '{"run_id": "x"}')
        self.write("src/verification/hide/payments.py", "def pay(): return 'OK'\n")
        self.init_real_run()
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        self.write("src/verification/hide/payments.py", "def pay(): return 'STOLEN'\n")
        r = self.check()
        self.assertEqual(r.returncode, 1, "假 manifest 仍能藏住整个目录")
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)
        # 新增后门文件同样要被发现
        self.write("src/verification/hide/backdoor.py", "import os\n")
        self.assertIn("TESTED_RUNTIME_MISMATCH", self.check().stdout)

    def test_custom_doc_globs_can_only_narrow(self):
        """manifest 里的 doc_only_globs 是被测者自写的，只能收窄，不能把 src/** 说成文档。"""
        self.init_real_run(doc_only_globs=["**"])          # 试图全匹配
        self.write("src/app.py", "def f(): pass  # backdoor\n")
        r = self.re_attest("只是改了点文档")
        self.assertIn("kind=behavioral", r.stdout, "自定义 glob 放宽了 doc-only")

    def test_ledger_planted_before_init_cannot_hide_changes(self):
        """在 init **之前**往 src/ 塞账本同样藏不住——排除范围只认 init 时冻结的显式声明。"""
        os.makedirs(os.path.join(self.repo, "src"), exist_ok=True)
        self.write("src/app.py", "print('real')\n")
        self.write("src/plan-test-run.json", '{"schema_version": "1.2.0"}')
        self.init_real_run()
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        self.write("src/app.py", "print('changed after test')\n")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_planted_ledger_cannot_hide_changes(self):
        """不能靠"在某目录塞一个账本文件"把它排除掉来藏改动。

        排除范围只认 init 时冻结的显式声明，塞账本不会扩大它；即便被排除，
        指纹只取文件条目，被排掉的文件会从条目里整体消失，指纹照样变——藏不住。
        """
        self.init_real_run()
        os.makedirs(os.path.join(self.repo, "src"), exist_ok=True)
        self.write("src/app.py", "print('real code')\n")
        run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "新增源码"],
                 cwd=self.repo)
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "pass"], cwd=self.repo)
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        # 改源码 + 在同目录塞一个假账本试图让它被排除
        self.write("src/app.py", "print('changed after test')\n")
        self.write("src/plan-test-run.json", '{"schema_version": "1.2.0"}')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)

    def test_run_dir_excluded_with_relative_path(self):
        """run-dir 用相对路径传入时也必须被排除。

        macOS 的 /var → /private/var 软链会让 abspath 两侧不一致，排除规则静默失效，
        于是 run-dir 自己写的账本被算成"内容变化"，每次 re-attest 都误判成 behavioral。
        这个 bug 是手工跑真实流程时暴露的，自测里没有——补上。
        """
        self.init_real_run()
        rel_run_dir = os.path.relpath(self.run_dir, self.repo)
        r = run_gate(["re-attest", "--run-dir", rel_run_dir, "--reason", "什么都没改"],
                     cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NO CHANGE", r.stdout)

    def test_mode_change_counts_as_content_change(self):
        """可执行位变化也是交付差异（独立审计点名的缺口）。"""
        self.init_real_run()
        os.chmod(os.path.join(self.repo, "src.py"), 0o755)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)


class EvidenceRefreshTestCase(GateHarness):
    """重测后证据文件更新，必须有合法的更新路径（否则只能整轮重来）。"""

    def test_stale_evidence_blocks_until_replaced(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        self.artifact("artifacts/run.log", "第一次执行\n")
        self.attach("artifacts/run.log", scenario="S-1")
        self.record("S-1")
        self.assertEqual(self.finalize(check_only=True).returncode, 0)
        # 重跑测试 → 证据文件变了 → 如实变红
        self.artifact("artifacts/run.log", "第二次执行\n")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("EVIDENCE_HASH_MISMATCH", r.stdout)
        # --replace 顶替旧条目后恢复
        r = run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                      "artifacts/run.log", "--kind", "primary", "--scenario", "S-1",
                      "--replace"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.finalize(check_only=True)
        self.assertEqual(out.returncode, 0, out.stdout)
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            led = json.load(f)
        self.assertEqual(len(led["superseded_evidence"]), 1)  # 旧条目留痕，不是静默覆盖

    def test_replace_is_recorded_in_integrity_chain(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        self.artifact("artifacts/run.log", "a\n")
        self.attach("artifacts/run.log", scenario="S-1")
        self.artifact("artifacts/run.log", "b\n")
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                  "artifacts/run.log", "--kind", "primary", "--replace"])
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            led = json.load(f)
        ops = [e["op"] for e in led["integrity"]["log"]]
        self.assertEqual(ops.count("attach-evidence"), 2)
        self.assertIsNone(integrity_break(led))


def integrity_break(led):
    """独立重算链，确认 --replace 之后链仍自洽。"""
    import hashlib
    chain = ""
    for e in led["integrity"]["log"]:
        expect = hashlib.sha256((chain + str(e["op"]) + str(e["facts_digest"])).encode()).hexdigest()
        if e["chain"] != expect:
            return "chain broken at seq %s" % e["seq"]
        chain = e["chain"]
    return None


class StopHookTestCase(RealRepoAttestationTestCase):
    """Stop hook 的自动化测试。

    独立审计连续多轮指出 hook 零自动化测试、证据退化成散文。这里把它的关键行为固化：
    识别靠账本**形状**（不靠文件名/目录名——两者各被打穿过一次），且不误伤业务文件。
    """

    HOOK = os.path.join(os.path.dirname(HERE), "..", "..", "hooks")

    def hook_repo(self):
        """把 gate 与 hook 装进当前 throwaway 仓，返回运行 hook 的函数。"""
        hooks_src = os.path.abspath(os.path.join(HERE, "..", "..", "..", "hooks"))
        dst = os.path.join(self.repo, "hooks")
        os.makedirs(dst, exist_ok=True)
        for name in ("stop-gate-check.sh", "gate_scan.py"):
            shutil.copy(os.path.join(hooks_src, name), os.path.join(dst, name))
        gate_dst = os.path.join(self.repo, "skills", "plan-test", "scripts")
        os.makedirs(gate_dst, exist_ok=True)
        shutil.copy(GATE, os.path.join(gate_dst, "plan_test_gate.py"))
        self.git("add", "-A")
        self.git("commit", "-qm", "install gate+hook")

        def run():
            return subprocess.run(["bash", "hooks/stop-gate-check.sh"], cwd=self.repo,
                                  capture_output=True, text=True,
                                  env=dict(os.environ, CLAUDE_PROJECT_DIR=self.repo))
        return run

    def test_hook_passes_when_no_ledger(self):
        run = self.hook_repo()
        self.assertEqual(run().returncode, 0)

    def test_hook_blocks_unclosed_ledger_anywhere(self):
        """run-dir 不在 verification/ 下也必须被发现（第八轮打穿点）。"""
        run = self.hook_repo()
        self.init_real_run()
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        r = run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stderr)

    def test_renaming_ledger_does_not_hide_it(self):
        """把账本改名同样藏不住（第九轮打穿点：按文件名识别仍是按名字识别）。"""
        run = self.hook_repo()
        self.init_real_run()
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        os.rename(os.path.join(self.run_dir, "plan-test-run.json"),
                  os.path.join(self.run_dir, "ledger.archived.json"))
        self.assertEqual(run().returncode, 2, "账本改名后 hook 看不见了")
        os.rename(os.path.join(self.run_dir, "ledger.archived.json"),
                  os.path.join(self.run_dir, "zzz-random-name.json"))
        self.assertEqual(run().returncode, 2)

    def test_hook_ignores_business_json_and_gitignored_files(self):
        """业务 JSON 与被 .gitignore 忽略的文件都不参与识别（误报方向）。"""
        run = self.hook_repo()
        self.write(".gitignore", ".venv/" + chr(10))
        os.makedirs(os.path.join(self.repo, ".venv", "pkg"), exist_ok=True)
        self.write(".venv/pkg/manifest.json",
                   '{"run_id":"x","scenarios":[{"scenario_id":"S-1"}],"applicability":{}}')
        self.write("tests/verification/cases/manifest.json",
                   '{"scenarios":["登录","下单"],"acceptance_file":"spec.md"}')
        self.write("docs/verification/q1/report.md", "# 来料检验报告\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "business files")
        self.assertEqual(run().returncode, 0, run().stderr)


class ClosingWorkflowTestCase(RealRepoAttestationTestCase):
    """按 phase-final-dod ⓪ 的收尾四步逐字执行，必须真的能走完。

    前两轮独立审计都在这里判 FAIL：文档写着一套顺序，照着做却永远 exit 1。
    grep 文档段落是否存在不算证据——只有整条路径跑通才算。
    """

    def gate(self, *args):
        return run_gate(list(args) + ["--run-dir", self.run_dir], cwd=self.repo)

    def full_green_run(self):
        self.init_real_run()
        with open(os.path.join(self.run_dir, "artifacts", "s1.log"), "w") as f:
            f.write("run log")
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                  "artifacts/s1.log", "--kind", "primary", "--scenario", "S-1"],
                 cwd=self.repo)
        for name, body in (("auditor-input.json", '{"frozen":true}'),
                           ("auditor-output.json", '{"verdict":"PASS"}')):
            with open(os.path.join(self.run_dir, name), "w") as f:
                f.write(body)
        self.audit()

    def audit(self):
        return run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                         "--engine", "audit-engine", "--input", "auditor-input.json",
                         "--output", "auditor-output.json"], cwd=self.repo)

    def finalize(self):
        return run_gate(["finalize", "--run-dir", self.run_dir], cwd=self.repo)

    def test_closing_four_steps_actually_work(self):
        self.full_green_run()
        self.assertEqual(self.finalize().returncode, 0, self.finalize().stdout)

        # step 1：收尾流程强制要求的文档回写 → 如实变红
        self.write("ARCHITECTURE.md", "# 架构\n")
        self.write("README.md", "# 说明\n")
        self.assertEqual(self.finalize().returncode, 1)

        # step 2：re-attest → doc-only
        r = run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "收尾文档回写"],
                     cwd=self.repo)
        self.assertIn("kind=doc-only", r.stdout)

        # step 3：重新 audit（re-attest 改了 fact，旧审计已 stale）
        self.assertEqual(self.audit().returncode, 0)

        # step 4：finalize 通过
        out = self.finalize()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("GATE RECEIPT:", out.stdout)

        # step 5：提交后仍通过（内容未变）
        self.git("add", "-A")
        self.git("commit", "-qm", "ship")
        self.assertEqual(self.finalize().returncode, 0, self.finalize().stdout)

    def test_code_change_at_closing_forces_retest(self):
        """收尾期改代码 → re-attest 判 behavioral → 必须重跑，不能靠 re-attest 洗白。"""
        self.full_green_run()
        self.assertEqual(self.finalize().returncode, 0)
        self.write("src.py", "print('v2')\n")
        run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "修 bug"],
                 cwd=self.repo)
        self.audit()
        out = self.finalize()
        self.assertEqual(out.returncode, 1)
        self.assertIn("RETEST_REQUIRED_AFTER_CHANGE", out.stdout)


class RetireTestCase(RealRepoAttestationTestCase):
    """退役必须有守卫，否则它就是下一个 `fixture_only`——加个字段就让门消失。

    独立审计实测过无守卫版本：`retire --reason "这个先不做了"` 即可让一个 required 场景 FAIL 的
    run 从 hook 前消失；手写 `"retired": true` 也一样，因为 hook 把该判断放在 check-only 之前。
    """

    def setUp(self):
        super(RetireTestCase, self).setUp()
        # 继任 run 目录须在 init 之前就存在（related_run_dirs 校验存在性）
        os.makedirs(os.path.join(self.repo, "plans", "p", "verification", "succ", "artifacts"))

    def successor(self, scenario_id="S-1"):
        """造一个真正通过的继任 run（非 fixture、SHIPPABLE、receipt 未失效）。"""
        d = os.path.join(self.repo, "plans", "p", "verification", "succ")
        manifest = {
            "run_id": "succ", "repo_root": self.repo, "source_request_text": "继任",
            "acceptance_file": os.path.join(self.repo, "acceptance.md"),
            "applicability": self.applicability_block(),
            "related_run_dirs": ["plans/p/verification/run-1"],
            "scenarios": [{"scenario_id": scenario_id, "required": True}],
        }
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False))
        run_gate(["init", "--run-dir", d, "--manifest", os.path.join(d, "manifest.json")], cwd=self.repo)
        with open(os.path.join(d, "artifacts", "s1.log"), "w") as f:
            f.write("ok")
        run_gate(["attach-evidence", "--run-dir", d, "--path", "artifacts/s1.log",
                  "--kind", "primary", "--scenario", scenario_id], cwd=self.repo)
        run_gate(["record-run", "--run-dir", d, "--scenario", scenario_id, "--kind", "root",
                  "--result", "pass"], cwd=self.repo)
        for name, body in (("auditor-input.json", '{"frozen":true}'),
                           ("auditor-output.json", '{"verdict":"PASS"}')):
            with open(os.path.join(d, name), "w") as f:
                f.write(body)
        run_gate(["audit", "--run-dir", d, "--verdict", "PASS", "--engine", "e",
                  "--input", "auditor-input.json", "--output", "auditor-output.json"], cwd=self.repo)
        r = run_gate(["finalize", "--run-dir", d], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return d

    def retire(self, superseded_by, reason="已被继任 run 取代"):
        return run_gate(["retire", "--run-dir", self.run_dir, "--reason", reason,
                         "--superseded-by", superseded_by], cwd=self.repo)

    def status(self):
        return run_gate(["retire-status", "--run-dir", self.run_dir], cwd=self.repo)

    def test_retire_requires_a_passing_successor(self):
        """没有通过的继任者 → 拒绝退役（这正是"这个先不做了"式绕过）。"""
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        r = self.retire("plans/p/verification/nonexistent")
        self.assertEqual(r.returncode, 2)
        self.assertIn("RETIRE 拒绝", r.stderr)
        self.assertEqual(self.status().returncode, 1)

    def test_retire_with_valid_successor_is_accepted(self):
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        succ = self.successor()
        r = self.retire(os.path.relpath(succ, self.repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        self.assertEqual(st.returncode, 0, st.stdout + st.stderr)
        self.assertIn("VALID", st.stdout)

    def test_handwritten_retired_flag_is_invalid(self):
        """手写 `"retired": true`（不经 CLI）不得生效——链对不上。"""
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        succ = self.successor()
        p = os.path.join(self.run_dir, "plan-test-run.json")
        with open(p, encoding="utf-8") as f:
            led = json.load(f)
        led["retired"] = True
        led["superseded_by"] = os.path.relpath(succ, self.repo)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
        st = self.status()
        self.assertEqual(st.returncode, 1)
        self.assertIn("INVALID", st.stdout)

    def test_retire_does_not_make_run_shippable(self):
        """退役不等于通过——账本仍如实是未闭环状态。"""
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        succ = self.successor()
        self.retire(os.path.relpath(succ, self.repo))
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stdout)

    def test_successor_must_cover_required_scenarios(self):
        """继任者必须真的承接工作：覆盖被退役 run 的 required 场景，且同一份 acceptance。

        独立审计实测：S-1 fail 的 run 被一个唯一场景是「Z-9 完全无关」的同仓 run 退役即通过——
        那不是转移举证责任，是拿一张无关的 receipt 背书。
        """
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        succ = self.successor(scenario_id="Z-9")     # 场景完全无关
        r = self.retire(os.path.relpath(succ, self.repo))
        self.assertEqual(r.returncode, 2)
        self.assertIn("未覆盖", r.stderr)

    def test_successor_must_be_in_same_repo(self):
        """继任者不能指向别的仓库——那等于"借"一张无关的 receipt 给本次失败背书。"""
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        outside = tempfile.mkdtemp(prefix="gate-other-repo-")
        try:
            r = self.retire(outside)
            self.assertEqual(r.returncode, 2)
            self.assertIn("不在本仓库内", r.stderr)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_fixture_run_cannot_retire_out(self):
        """fixture-only 账本不得靠退役退出阻断——retire 命令当场拒绝，不是事后判无效。"""
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        succ = self.successor()
        p = os.path.join(self.run_dir, "plan-test-run.json")
        with open(p, encoding="utf-8") as f:
            led = json.load(f)
        led["fixture_only"] = True
        with open(p, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
        r = self.retire(os.path.relpath(succ, self.repo))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.status().returncode, 1)


class AuditorVerdictSourceTestCase(GateHarness):
    """审计产物读不出结论时，不得静默采信命令行。"""

    def test_unparseable_output_rejected(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1")
        self.artifact("auditor-input.json", '{"frozen": true}')
        self.artifact("auditor-output.json", "我看了一遍，感觉没问题。")  # 无 verdict 字段/结论行
        r = run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                      "--engine", "opus-auditor", "--input", "auditor-input.json",
                      "--output", "auditor-output.json"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("读不到 verdict", r.stderr)


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
        # fixture-only 通过 = exit 3（合成数据不得冒充交付 exit 0）
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout + r.stderr)
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
