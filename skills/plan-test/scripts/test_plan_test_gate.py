#!/usr/bin/env python3
"""plan_test_gate.py 自测。

运行：python skills/plan-test/scripts/test_plan_test_gate.py
覆盖 handoff §8 要求的关键 fixture：状态矛盾、required NOT_RUN、证据缺失/篡改、
循环证据、frozen oracle 变异、audit 后 stale、receipt 幂等、Companion 历史三冲突
dogfood，以及一条完整 PASS 路径。全部经 canonical CLI 路径执行，不绕过 finalize。
"""

import refusal_guard  # noqa: F401  测试隔离：把 refusal 写入引到 tmpdir（s1a AC-7，见该模块 docstring）
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

FIXTURE_EXIT = 3  # fixture-only run 通过（合成数据，非交付通过）

# Installed Codex skills may be reached through a directory symlink. Resolve it so
# repository-level fixtures (hooks/) are found from the real skill source checkout.
HERE = os.path.dirname(os.path.realpath(__file__))
GATE = os.path.join(HERE, "plan_test_gate.py")


def expected_plugin_version():
    """与 plan_test_gate._plugin_version 同一发现算法：沿脚本路径向上找
    .claude-plugin/plugin.json；找不到（如手工复制安装）时为空串。
    动态读取而非硬编码——否则每次 release 升版本都会打红这两条测试。"""
    d = HERE
    while True:
        candidate = os.path.join(d, ".claude-plugin", "plugin.json")
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as f:
                    return str(json.load(f).get("version") or "")
            except (OSError, ValueError):
                return ""
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_utf8(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


_GATE_MODULE = None


def gate_module():
    """按路径加载被测 gate 本体——用于直接调用内部不变量函数（不经 CLI）。"""
    global _GATE_MODULE
    if _GATE_MODULE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("plan_test_gate_under_test", GATE)
        _GATE_MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_GATE_MODULE)
    return _GATE_MODULE


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

    def test_in_place_amend_fail_then_pass_finalizes(self):
        """2026-08-31 DGX 复盘出口成本 AC：原地修账必须比作废重开便宜。

        端到端锚定 W4-15（fail 非粘性）在 finalize 全链上真的走得通：
        真实失败 → 修复 → **同一 run-dir** 补 root pass → audit → finalize
        必须发 receipt；失败史保留在账本里（留痕与出账不再二选一——
        优化前 run log 实证 56% 测试执行因换 run-dir 作废）。"""
        self.init([{"scenario_id": "S-1", "required": True, "ui": True,
                    "gate_type": "positive-value", "expected_run_created": True}])
        self.record("S-1", result="fail")  # 第一次真实失败入账
        self.artifact("artifacts/s1-click.png", "screenshot-bytes")
        self.attach("artifacts/s1-click.png", scenario="S-1", ui_action=True)
        self.record("S-1", business_terminal="completed+valid",
                    run_id_under_test="run-uuid-1", session_id="sess-new")
        self.audit_pass()
        r = self.finalize()
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout + r.stderr)
        self.assertIn("GATE RECEIPT:", r.stdout)
        with open(os.path.join(self.run_dir, "plan-test-run.json"),
                  encoding="utf-8") as f:
            ledger = json.load(f)
        fails = [x for x in ledger.get("runs", [])
                 if x.get("scenario_id") == "S-1" and x.get("result") == "fail"]
        self.assertEqual(len(fails), 1, "失败史必须保留在账本，不得因出账被抹")

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

    def test_release_unit_counts_only_formal_ac_table_rows(self):
        rows = ["| AC-%d | MUST | behavior %d |" % (n, n) for n in range(1, 9)]
        acceptance = self.write(
            "release-acceptance.md",
            "| ID | Level | Rule |\n|---|---|---|\n" + "\n".join(rows)
            + "\n| Summary | 覆盖 8 条 MUST | not another AC |\n",
        )
        plan = self.write("small-plan.md", "# plan\n")
        r = run_gate(["check-release-unit", "--acceptance", acceptance,
                      "--plan", plan, "--max-must-ac", "8"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("MUST AC: 8 / 8", r.stdout)

    def test_required_lane_closure(self):
        """fresh lane PASS、history lane 未执行 → FAIL。"""
        self.init([{"scenario_id": "S-1", "required": True,
                    "required_lanes": ["fresh", "history-upgrade"]}])
        self.record("S-1", lane="fresh")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RISK_CLOSURE_MISSING", r.stdout)

    def test_stochastic_sampling(self):
        """高风险非确定性场景 1/3 成功 → 采样不足，不得 SHIP。

        W4-15 后 fail 非粘性，场景不再因历史 fail 判 FAIL——但 FLAKY 序列被
        **稳定性门**独立接住（1/3 通过 + 未解释失败 → STABILITY_SAMPLES_INSUFFICIENT，
        照样 rc=1）。这正是「解除 fail 的 pass 面对的硬门一条不少」的实证：
        非粘性没有为抖动测试打开任何口子。"""
        self.init([{"scenario_id": "S-1", "required": True, "min_root_runs": 2}])
        self.record("S-1", result="fail")
        self.record("S-1", result="fail")
        self.record("S-1", result="pass")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("STABILITY_SAMPLES_INSUFFICIENT", r.stdout)
        self.assertIn("FLAKY", r.stdout)

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

    def test_fixture_run_skips_clock_gates_but_renders_breakdown(self):
        """fixture 回放的时钟天然双峰（历史申报时间 vs 回放时刻）——时钟类硬门只对真实 run
        生效；fixture 仍要能记 timing 并在报告里给出耗时分解。"""
        self.full_pass_run()
        for s, e in (("2026-07-27T09:00:00Z", "2026-07-27T09:05:00Z"),
                     ("2026-07-27T13:00:00Z", "2026-07-27T13:05:00Z")):  # 中隔 >120min
            run_gate(["record-timing", "--run-dir", self.run_dir,
                      "--phase", "phase-4", "--activity-class", "manual_e2e",
                      "--declared-start", s, "--declared-end", e])
        self.audit_pass()  # timing 追加改变了 facts，须重审
        r = self.finalize()
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout + r.stderr)
        self.assertNotIn("TIMING_GAP", r.stdout)      # fixture 免检时钟门
        self.assertNotIn("TIMING_MISSING", r.stdout)
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

    def test_baseline_is_summary_and_runtime_holds_content_entries(self):
        self.init_real_run()
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            ledger = json.load(f)
        self.assertNotIn("content_entries", ledger["baseline"])
        self.assertIn("content_entries", ledger["runtime_attestation"])
        self.assertEqual(ledger["baseline"].get("content_digest"),
                         ledger["runtime_attestation"].get("content_digest"))

    def test_deletion_digest_is_index_independent(self):
        """删文件后，"未 git add"与"已提交"必须算出同一个指纹。

        记成 "absent" 条目时指纹会依赖索引状态：删了未 add → 索引里还有它（记 absent），
        commit 之后 → 条目消失，同一份工作树内容算出两个指纹，于是"提交"这个不改内容的动作
        会误触发 TESTED_RUNTIME_MISMATCH（提交本仓时实测到）。
        """
        self.write("doomed.py", "print('bye')\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "add doomed")
        self.init_real_run()
        os.remove(os.path.join(self.repo, "doomed.py"))
        run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "删文件"], cwd=self.repo)
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "pass"], cwd=self.repo)
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        self.git("add", "-A")                      # 把删除登记进索引
        self.git("commit", "-qm", "remove doomed")
        out = self.check()
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("TESTED_RUNTIME_MISMATCH", out.stdout)

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


class PortableRepoRootTestCase(RealRepoAttestationTestCase):
    """v0.6.1 路径可移植（2026-09-01 实测复盘）：账本此前存开账机器的绝对
    repo_root 与 testcase abs_path，换机器/挪目录后 TESTED_RUNTIME_MISMATCH /
    FROZEN_ORACLE_CHANGED / ACTIVE_RUN_MISMATCH 全成假阳性（Windows 开账的
    C:\\... 账本在 Mac 上实锤）。resolver：存储值可达用存储值，否则从 run-dir
    向上找 .git。"""

    def test_ledger_survives_repo_relocation(self):
        self.write("testcase/tc-1.md", "# oracle\n断言：脚本输出 v1\n")
        self.init_real_run(testcase_files=["testcase/tc-1.md"])
        with open(os.path.join(self.run_dir, "plan-test-run.json"),
                  encoding="utf-8") as f:
            led = json.load(f)
        # 写入端：path 必须是仓库相对 POSIX 形式，不再是调用者原文/绝对路径
        self.assertEqual(led["testcase_lock"]["files"][0]["path"], "testcase/tc-1.md")
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        # 整仓搬家：存储的绝对 repo_root 与 abs_path 全部失效
        moved = os.path.join(self.tmp, "repo-moved")
        os.rename(self.repo, moved)
        run_dir2 = os.path.join(moved, "plans", "p", "verification", "run-1")
        r = run_gate(["finalize", "--run-dir", run_dir2, "--check-only"], cwd=moved)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("TESTED_RUNTIME_MISMATCH", r.stdout)
        self.assertNotIn("FROZEN_ORACLE_CHANGED", r.stdout)

    def test_die_messages_carry_codes(self):
        """v0.6.1：出口成本要有度量——高频摩擦有专码，其余 die 自动冠 USAGE_ERROR，
        refusal log/stats 从此能区分"门抓到违规"与"代理在门前摔跤"。"""
        self.init_real_run()
        r = run_gate(["record-timing", "--run-dir", self.run_dir, "--phase", "phase-3",
                      "--activity-class", "testing",
                      "--declared-start", "2026-09-01T00:00:00Z",
                      "--declared-end", "2026-09-01T00:10:00Z"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("TIMING_CLASS_INVALID", r.stderr)
        self.assertIn("automated_test", r.stderr)  # 直觉词对照要给出合法出口
        r2 = run_gate(["record-timing", "--run-dir", self.run_dir, "--phase", "phase-3",
                       "--activity-class", "implementation", "--wait-reason", "user_review",
                       "--declared-start", "2026-09-01T00:00:00Z",
                       "--declared-end", "2026-09-01T00:10:00Z"], cwd=self.repo)
        self.assertEqual(r2.returncode, 2)
        self.assertIn("USAGE_ERROR", r2.stderr)  # 无专码的拒绝由兜底码接住
        r3 = run_gate(["attach-evidence", "--run-dir", self.run_dir,
                       "--path", '{"inline": "json"}', "--kind", "primary"], cwd=self.repo)
        self.assertEqual(r3.returncode, 2)
        self.assertIn("EVIDENCE_PATH_NOT_FOUND", r3.stderr)


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

    def test_check_only_after_ship_clarifies_historical_receipt(self):
        """2026-08-31 复盘：历史 receipt 复验 NOT_READY 曾被误读为"历史交付失败"
        （08-28 收集实测 18/18 命中 TESTED_RUNTIME_MISMATCH）。check-only 在
        receipt 存在时必须声明：漂移诊断不推翻签发时刻的判定。"""
        self.full_green_run()
        self.assertEqual(self.finalize().returncode, 0)
        self.write("src.py", "print('v2 after ship')\n")
        r = self.gate("finalize", "--check-only")
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)
        self.assertIn("HISTORICAL RECEIPT PRESENT", r.stdout)
        self.assertIn("不推翻", r.stdout)

    def test_check_only_after_ship_distinguishes_unreachable_repo(self):
        """v0.6.1 修正归因：仓库不可达 ≠ 内容漂移。把不可达说成漂移是安抚性的
        错误解释（exec-004 实测：Windows 账本在 Mac 上被解释成"漂移"）。"""
        self.full_green_run()
        self.assertEqual(self.finalize().returncode, 0)
        orphan = os.path.join(self.tmp, "orphan-run")
        shutil.copytree(self.run_dir, orphan)
        os.rename(self.repo, os.path.join(self.tmp, "repo-gone-elsewhere"))
        r = run_gate(["finalize", "--check-only", "--run-dir", orphan], cwd=self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("TESTED_RUNTIME_MISMATCH", r.stdout)
        self.assertIn("读不到被测仓库", r.stdout)
        self.assertNotIn("反映的是仓库在签发后的内容漂移", r.stdout)

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

    def successor(self, scenario_id="S-1", finalize=True):
        """造一个全绿的继任 run（非 fixture、state=SHIPPABLE）。

        `finalize=True` 会额外盖章拿 receipt。**注意顺序**（2026-08-28 起）：当被退役的
        run-1 就在同一个 `verification/` 下、且测同一批场景时，继任者在 run-1 了结之前
        拿不到 receipt（SIBLING_RUN_UNRESOLVED）。合法顺序是"继任者全绿 → retire run-1
        → 继任者 finalize"，所以这类用例要传 `finalize=False`。
        """
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
        if finalize:
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
        succ = self.successor(finalize=False)
        r = self.retire(os.path.relpath(succ, self.repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        # 继任者还没盖章 → 退役成立但未落地，退役不能在这一步就让 hook 放行，
        # 否则"造个全绿继任者、退役、永不 finalize"就是一条静默出口。
        st = self.status()
        self.assertEqual(st.returncode, 1, st.stdout + st.stderr)
        self.assertIn("PENDING", st.stdout)
        # 死锁已解：run-1 一了结，继任者立刻能盖章（这正是 allow_pending 存在的理由）。
        fin = run_gate(["finalize", "--run-dir", succ], cwd=self.repo)
        self.assertEqual(fin.returncode, 0, fin.stdout + fin.stderr)
        st = self.status()
        self.assertEqual(st.returncode, 0, st.stdout + st.stderr)
        self.assertIn("VALID", st.stdout)

    def test_handwritten_retired_flag_is_invalid(self):
        """手写 `"retired": true`（不经 CLI）不得生效——链对不上。"""
        self.init_real_run(related_run_dirs=["plans/p/verification/succ"])
        succ = self.successor(finalize=False)
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
        succ = self.successor(finalize=False)
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
        succ = self.successor(finalize=False)
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


class TimingHardGateTestCase(RealRepoAttestationTestCase):
    """时间记账硬门（schema 1.3.0）：DeskPet 复盘实锤 12h24m 真实执行 timing 全 0、
    账本在 finalize 前 2.5 分钟整体补写，validator 零提示。现在这些都是 error。"""

    def _iso(self, offset_minutes):
        import datetime
        t = datetime.datetime.now(datetime.timezone.utc) + \
            datetime.timedelta(minutes=offset_minutes)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    def declared(self, start_off, end_off, activity="manual_e2e", wait=None):
        args = ["record-timing", "--run-dir", self.run_dir, "--phase", "phase-4",
                "--activity-class", activity,
                "--declared-start", self._iso(start_off),
                "--declared-end", self._iso(end_off)]
        if wait:
            args += ["--wait-reason", wait]
        r = run_gate(args, cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_long_span_without_timing_blocks(self):
        """活动跨度超 30 分钟而 timing 覆盖不足 → TIMING_MISSING（error）。
        跨度由导入的历史证据文件时间撑开——正是 DeskPet 的形态。"""
        self.init_real_run()
        p = os.path.join(self.run_dir, "artifacts", "old-shot.png")
        with open(p, "w", encoding="utf-8") as f:
            f.write("screenshot")
        old = __import__("time").time() - 40 * 60
        os.utime(p, (old, old))
        r = run_gate(["import-evidence", "--run-dir", self.run_dir,
                      "--path", "artifacts/old-shot.png", "--kind", "primary",
                      "--from-run", "e2e 会话 22:31 采集"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("TIMING_MISSING", out.stdout)
        self.assertNotIn("EVIDENCE_PREDATES_LEDGER", out.stdout)  # import 是合法通道
        # 用申报 timing 把历史测试时段补记入账 → 覆盖达标 → 放行
        self.declared(-40, -2)
        out = self.check()
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_gap_between_anchors_blocks_until_covered(self):
        """锚点之间超过 120 分钟的空洞 → TIMING_GAP（error）；申报补覆盖后放行。"""
        self.init_real_run()
        self.declared(0, 30, activity="implementation")
        self.declared(180, 205, activity="automated_test")   # 与上一段中隔 150min
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("TIMING_GAP", out.stdout)
        self.declared(30, 180, activity="user_wait", wait="user_review")
        out = self.check()
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_predated_evidence_via_plain_attach_blocks(self):
        """普通 attach 一份开账前生成的证据 → EVIDENCE_PREDATES_LEDGER（先测后补账）。"""
        self.init_real_run()
        p = os.path.join(self.run_dir, "artifacts", "backfill.png")
        with open(p, "w", encoding="utf-8") as f:
            f.write("old screenshot")
        old = __import__("time").time() - 3600
        os.utime(p, (old, old))
        r = run_gate(["attach-evidence", "--run-dir", self.run_dir,
                      "--path", "artifacts/backfill.png", "--kind", "primary"],
                     cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("EVIDENCE_PREDATES_LEDGER", out.stdout)
        self.assertIn("import-evidence", out.stdout)  # 诊断要指出合法通道


class PhasePairingTestCase(GateHarness):
    """phase-start/phase-end 配对：阶段没收尾就 finalize → PHASE_UNPAIRED。"""

    def test_unpaired_phase_blocks_full_finalize_only(self):
        self.full_pass_run()
        r = run_gate(["phase-start", "--run-dir", self.run_dir, "--phase", "phase-4"])
        self.assertEqual(r.returncode, 0, r.stderr)
        # check-only 不查配对（阶段可能尚未收尾）
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.audit_pass()  # phase 事件改变 facts，重审
        r = self.finalize()
        self.assertEqual(r.returncode, 1)
        self.assertIn("PHASE_UNPAIRED", r.stdout)
        r = run_gate(["phase-end", "--run-dir", self.run_dir, "--phase", "phase-4"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.audit_pass()
        r = self.finalize()
        self.assertEqual(r.returncode, FIXTURE_EXIT, r.stdout + r.stderr)

    def test_end_without_start_blocks(self):
        self.full_pass_run()
        run_gate(["phase-end", "--run-dir", self.run_dir, "--phase", "phase-9"])
        self.audit_pass()
        r = self.finalize()
        self.assertEqual(r.returncode, 1)
        self.assertIn("PHASE_UNPAIRED", r.stdout)


class DriverApprovalTestCase(GateHarness):
    """全 AI 驾驶批准门（phase-4 ①b 机器化）：输入语义敏感 + required UI 场景全 AI 驾驶
    且无用户批准 → DRIVER_APPROVAL_MISSING。DeskPet 复盘：12 条 run 全 driver=ai、
    叙述却写"真人 E2E"，规则只在文档里。"""

    def sensitive_ui_run(self):
        scen = [{"scenario_id": "S-1", "required": True, "ui": True,
                 "gate_type": "positive-value", "input_class": "自然提问",
                 "min_root_runs": 2, "cold_start": True},
                {"scenario_id": "S-2", "required": True, "input_class": "专业术语"},
                {"scenario_id": "S-3", "required": True, "gate_type": "negative-safety",
                 "input_class": "对抗输入"}]
        self.init(scen, applicability={
            "input_sensitive": {"value": True, "decided_by": "user",
                                "rationale": "LLM 调研 agent，输出质量随输入语义变化"},
            "llm_payload_driven": {"value": False, "decided_by": "agent",
                                   "rationale": "LLM 只做文本展示，不驱动端侧状态机"},
            "stateful_init": {"value": True, "decided_by": "agent",
                              "rationale": "依赖登录态与异步注册的检索服务"}})
        self.artifact("artifacts/s1-ui.png", "shot")
        self.attach("artifacts/s1-ui.png", scenario="S-1", ui_action=True)
        self.record("S-1", business_terminal="completed+valid")
        self.record("S-1", business_terminal="completed+valid")
        self.record("S-2")
        self.record("S-3")

    def test_all_ai_driving_without_approval_blocks(self):
        self.sensitive_ui_run()
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DRIVER_APPROVAL_MISSING", r.stdout)

    def test_recorded_approval_unblocks(self):
        self.sensitive_ui_run()
        msg_hash = hashlib.sha256("同意本次全部场景由 AI 驾驶".encode()).hexdigest()
        r = run_gate(["record-approval", "--run-dir", self.run_dir,
                      "--kind", "all-ai-driving", "--message-hash", msg_hash,
                      "--note", "用户 chat 批准"])
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        # 批准要在人读报告里可见
        self.audit_pass()
        self.finalize()
        run_gate(["render", "--run-dir", self.run_dir])
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            self.assertIn("用户批准记录", f.read())

    def test_human_driven_run_needs_no_approval(self):
        self.sensitive_ui_run()
        self.record("S-1", business_terminal="completed+valid", driver="human")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_bogus_message_hash_rejected(self):
        self.sensitive_ui_run()
        r = run_gate(["record-approval", "--run-dir", self.run_dir,
                      "--kind", "all-ai-driving", "--message-hash", "用户同意了"])
        self.assertEqual(r.returncode, 2)


class AuditorEngineIdentityTestCase(GateHarness):
    """audit --engine 必须是引擎身份，不是方法名（DeskPet 实测填了 fault_seam_analysis）。"""

    def test_method_name_as_engine_rejected(self):
        self.full_pass_run()
        r = run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                      "--engine", "fault_seam_analysis",
                      "--input", "auditor-input.json",
                      "--output", "auditor-output.json"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("引擎", r.stderr)

    def test_real_engine_id_accepted(self):
        self.full_pass_run()  # full_pass_run 里的 audit 用 opus-auditor，已经证明通过


class ImpactScopedRetestTestCase(RealRepoAttestationTestCase):
    """按影响范围复测：scenario.impact_paths 映射，fail-closed。
    DeskPet 复盘 P1：改任何文件 → 全场景 stale，是墙钟浪费最大的单点。"""

    def init_mapped_run(self):
        manifest = {
            "run_id": "impact-1",
            "repo_root": self.repo,
            "source_request_text": "影响范围复测验证",
            "acceptance_file": self.write("acceptance.md", "AC-A 后端；AC-B 前端\n"),
            "applicability": self.applicability_block(),
            "scenarios": [
                {"scenario_id": "S-A", "required": True,
                 "impact_paths": ["backend/**"]},
                {"scenario_id": "S-B", "required": True,
                 "impact_paths": ["frontend/**"]},
            ],
        }
        mpath = self.write("manifest.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mpath],
                     cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        for sid in ("S-A", "S-B"):
            r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", sid,
                          "--kind", "root", "--result", "pass"], cwd=self.repo)
            self.assertEqual(r.returncode, 0, r.stderr)

    def re_attest(self, reason="改动"):
        return run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", reason],
                        cwd=self.repo)

    def test_scoped_change_spares_unrelated_scenario(self):
        """只改 backend → 只有 S-A 需要重测，S-B 沿用既有结论并能解释原因。"""
        self.init_mapped_run()
        self.write("backend/api.py", "print('v2')\n")
        r = self.re_attest("改后端")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("S-A", r.stdout)          # 输出要指明受影响范围
        out = self.check()
        self.assertEqual(out.returncode, 1)
        retests = [l for l in out.stdout.splitlines()
                   if "RETEST_REQUIRED_AFTER_CHANGE" in l]
        self.assertEqual(len(retests), 1, out.stdout)
        self.assertIn("S-A", retests[0])
        # 只补测受影响场景即可放行
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-A",
                  "--kind", "root", "--result", "pass"], cwd=self.repo)
        out = self.check()
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_uncovered_change_fails_closed(self):
        """改一个未被任何映射覆盖的文件 → 全量复测（映射是被测者自写的，证明不了无关就全测）。"""
        self.init_mapped_run()
        self.write("misc/helper.py", "print('x')\n")
        self.re_attest("改杂项")
        out = self.check()
        self.assertEqual(out.returncode, 1)
        retests = [l for l in out.stdout.splitlines()
                   if "RETEST_REQUIRED_AFTER_CHANGE" in l]
        self.assertEqual(len(retests), 2, out.stdout)
        self.assertIn("fail-closed", out.stdout)

    def test_no_mapping_keeps_full_retest(self):
        """没有任何场景声明 impact_paths → 维持 1.2.0 全量复测行为（已有用例锁住，这里锁语义）。"""
        self.init_real_run()
        self.write("src.py", "print('v2')\n")
        run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "改代码"],
                 cwd=self.repo)
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("RETEST_REQUIRED_AFTER_CHANGE", out.stdout)


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


class BlockedNonStickyTestCase(GateHarness):
    """blocked 是「此刻做不到」，不是「这一轮报废」。

    背景（simple_harness r9 实跑）：旧实现里 blocked 排在 fail 之前、扫的还是全部 run，
    于是记一条 blocked = 该场景永久钉死；而 Stop hook 当时的文案恰恰是"做不到的项标
    BLOCKED"——文案 + 实现的组合等于诱导代理毁掉自己正在跑的轮次。
    """

    def test_blocked_then_pass_clears_the_scenario(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="blocked")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("状态=BLOCKED", r.stdout)
        # 后来真的跑通了：同一轮里补一条 root pass 就该解除，而不是整轮报废
        self.record("S-1", result="pass")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("READY_FOR_AUDIT", r.stdout)

    def test_blocked_after_pass_still_blocks(self):
        """顺序有意义：pass 之后又出现 blocked（回归/环境掉了）仍然是 BLOCKED。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="pass")
        self.record("S-1", result="blocked", kind="retry")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("状态=BLOCKED", r.stdout)

    def test_fail_cleared_by_later_compliant_pass(self):
        """W4-15（业主决策 B，2026-08-29）：fail 非粘性——与 blocked 同一解除线。

        blocked 的先例注释逐字适用：解除的唯一方式是**真的记一条 root pass**，
        该 pass 面对的硬门与从未 fail 过的场景完全相同。旧行为下同强度的证据
        「留痕重测」与「换目录洗账」二选一，设计在奖励洗账——56% 作废率的直接来源
        （s1-relay-foundation 一个 slice 连开 6 个 run、前 5 全废）。
        失败史不洗：fail 记录仍在账本与链里，render/审计随时可见。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="fail")
        self.record("S-1", result="pass")
        r = self.finalize(check_only=True)
        self.assertNotIn("状态=FAIL", r.stdout,
                         "其后合规 root pass 应解除更早的 fail")

    def test_fail_after_pass_is_still_fail(self):
        """解除线是单向的：pass 之后又 fail → 当前状态就是 FAIL。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        self.record("S-1", result="pass")
        self.record("S-1", result="fail")
        r = self.finalize(check_only=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("状态=FAIL", r.stdout)


class FlowTierAndTelemetryTestCase(RealRepoAttestationTestCase):
    """W6-22/23：判档入账与遥测必记（advisory 起步；LEAN×input_sensitive 矛盾为 error）。"""

    def _check(self, **extra):
        self.init_real_run(**extra)
        r = run_gate(["finalize", "--run-dir", self.run_dir, "--check-only"])
        return r.stdout

    def test_undeclared_flow_tier_is_advisory(self):
        out = self._check()
        self.assertIn("ADVISORY FLOW_TIER_UNDECLARED", out,
                      "未判档应曝光（advisory 起步，存量 manifest 全未声明不许一夜打红）")

    def test_missing_phase_telemetry_surfaces_at_render(self):
        # 遥测检查按设计只在 full/render 模式跑——check-only 时阶段可能尚未收尾
        self.init_real_run()
        r = run_gate(["render", "--run-dir", self.run_dir])
        self.assertIn("PHASE_TELEMETRY_MISSING", r.stdout,
                      "无任何 phase 事件应在 render/finalize 曝光")
        run_gate(["phase-start", "--run-dir", self.run_dir, "--phase", "p4"])
        run_gate(["phase-end", "--run-dir", self.run_dir, "--phase", "p4",
                  "--status", "ok"])
        r2 = run_gate(["render", "--run-dir", self.run_dir])
        self.assertNotIn("PHASE_TELEMETRY_MISSING", r2.stdout)

    def test_declared_flow_tier_passes(self):
        out = self._check(flow_tier={"value": "FULL", "decided_by": "agent",
                                     "rationale": "改动触及共享基础设施，按 config 判 FULL"})
        self.assertNotIn("FLOW_TIER_UNDECLARED", out)

    def test_lean_with_input_sensitive_is_error(self):
        out = self._check(
            flow_tier={"value": "LEAN", "decided_by": "agent",
                       "rationale": "单切面可自动回归，判 LEAN"},
            applicability={
                "input_sensitive": {"value": True, "decided_by": "agent",
                                    "rationale": "被测对象含 LLM 生成，输出随输入语义变化"},
                "llm_payload_driven": {"value": False, "decided_by": "agent",
                                       "rationale": "无 LLM 载荷驱动端侧状态机"},
                "stateful_init": {"value": False, "decided_by": "agent",
                                  "rationale": "无异步注册服务或登录态依赖"},
            },
            scenarios=[{"scenario_id": "S-%d" % i, "required": True,
                        "input_class": "c%d" % i,
                        "gate_type": "positive-value" if i == 1 else "negative-safety"}
                       for i in (1, 2, 3)])
        self.assertIn("DIAG FLOW_TIER_BASIS_FALSE", out,
                      "判 LEAN 与 input_sensitive=true 是实锤矛盾，必须拦")

    def test_render_generates_coverage_table(self):
        self.init_real_run()
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "pass"])
        run_gate(["render", "--run-dir", self.run_dir])
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            report = f.read()
        self.assertIn("真人覆盖账本（自动生成", report,
                      "W6-20：①c 的手写表必须由 render 生成")
        self.assertIn("| S-1 |", report)


class AcknowledgeTestCase(RealRepoAttestationTestCase):
    """acknowledge：用户显式放弃一轮验证——retire 之外的第二条出口。

    死锁背景：retire 要求继任 run 已 SHIPPABLE，而"继任轮正在跑"恰是最需要安静的阶段，
    历史轮每回合刷一遍诊断，出口却要等新轮跑完——历史轮越多，跑完新轮越贵。
    """

    HASH = "a" * 64

    def ack(self, reason="用户决定放弃这一轮", approval=None):
        return run_gate(["acknowledge", "--run-dir", self.run_dir, "--reason", reason,
                         "--approval-hash", approval or self.HASH], cwd=self.repo)

    def ack_status(self):
        return run_gate(["ack-status", "--run-dir", self.run_dir], cwd=self.repo)

    def test_acknowledge_requires_user_approval_hash(self):
        self.init_real_run()
        r = self.ack(approval="不是hash")
        self.assertEqual(r.returncode, 2)
        self.assertIn("SHA-256", r.stderr)
        self.assertEqual(self.ack_status().returncode, 1)

    def test_acknowledged_run_stops_blocking_but_never_ships(self):
        self.init_real_run()
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        r = self.ack()
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.ack_status()
        self.assertEqual(st.returncode, 0, st.stdout + st.stderr)
        # 放弃 ≠ 通过：账本从此报 RUN_ABANDONED，finalize 永远出不来 receipt
        out = self.check()
        self.assertEqual(out.returncode, 1)
        self.assertIn("RUN_ABANDONED", out.stdout)
        fin = run_gate(["finalize", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(fin.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "gate-receipt.json")))

    def test_handwritten_acknowledged_flag_is_invalid(self):
        """手写 `"acknowledged": true`（不经 CLI）不得生效——链对不上。"""
        self.init_real_run()
        p = os.path.join(self.run_dir, "plan-test-run.json")
        with open(p, encoding="utf-8") as f:
            led = json.load(f)
        led["acknowledged"] = True
        led["acknowledged_reason"] = "自己批准自己"
        led["acknowledged_approval"] = self.HASH
        with open(p, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
        st = self.ack_status()
        self.assertEqual(st.returncode, 1)
        self.assertIn("INVALID", st.stdout)

    def test_acknowledged_run_cannot_be_a_successor(self):
        """放弃的 run 不能反过来给别人背书——它永远没有 receipt。"""
        self.init_real_run()
        self.ack()
        other = os.path.join(self.repo, "plans", "p", "verification", "run-2")
        os.makedirs(os.path.join(other, "artifacts"))
        r = run_gate(["retire", "--run-dir", other, "--reason", "x",
                      "--superseded-by", os.path.relpath(self.run_dir, self.repo)],
                     cwd=self.repo)
        self.assertNotEqual(r.returncode, 0)


class HookOutputBudgetTestCase(StopHookTestCase):
    """输出预算：只详报活动轮，其余压成一行；结论不变时不重复正文；连续无变化会断路放行。

    背景（simple_harness r9 实跑）：旧版单次 Stop 输出 300+ 行 / ~10k token，一个会话触发
    12+ 次，且内容与本回合做了什么无关。
    """

    def second_run(self, run_id="real-2", result="fail"):
        """再造一个未闭环的 run-dir（模拟历史轮）。"""
        d = os.path.join(self.repo, "plans", "p", "verification", "run-2")
        os.makedirs(os.path.join(d, "artifacts"), exist_ok=True)
        manifest = {
            "run_id": run_id, "repo_root": self.repo, "source_request_text": "历史轮",
            "acceptance_file": os.path.join(self.repo, "acceptance.md"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-1", "required": True}],
        }
        mp = os.path.join(d, "m.json")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False))
        run_gate(["init", "--run-dir", d, "--manifest", mp], cwd=self.repo)
        run_gate(["record-run", "--run-dir", d, "--scenario", "S-1", "--kind", "root",
                  "--result", result], cwd=self.repo)
        return d

    def test_only_active_run_gets_full_diagnostics(self):
        run = self.hook_repo()
        self.second_run()             # 历史轮（先开，账本 mtime 更旧）
        self.init_real_run()          # 活动轮：本会话最后写入的账本
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        r = run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("run-2", r.stderr)                 # 历史轮仍被点名
        self.assertIn("活动轮", r.stderr)
        # 历史轮只出一行摘要，不出 DIAG 正文
        hist = [l for l in r.stderr.splitlines() if "run-2" in l]
        self.assertEqual(len(hist), 1, r.stderr)
        self.assertLess(len(r.stderr.splitlines()), 60, "单次输出不该再是几百行")

    def test_identical_report_is_not_repeated(self):
        run = self.hook_repo()
        self.init_real_run()
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        first = run()
        self.assertEqual(first.returncode, 2)
        self.assertIn("DIAG", first.stderr)
        second = run()
        self.assertEqual(second.returncode, 2)
        self.assertIn("与上次检查结论完全一致", second.stderr)
        self.assertNotIn("DIAG", second.stderr)
        self.assertLess(len(second.stderr), len(first.stderr))

    def test_circuit_breaker_releases_after_repeats(self):
        """连续 N 次结论一字未变 → 放行一次，但大声说明账本仍然是红的。"""
        run = self.hook_repo()
        self.init_real_run()
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        seen_release = False
        for _ in range(5):
            r = run()
            if r.returncode == 0:
                seen_release = True
                self.assertIn("交付判定没有改变", r.stderr)
                self.assertIn("acknowledge", r.stderr)
                break
        self.assertTrue(seen_release, "断路器没生效——会无限循环")

    def test_acknowledged_run_no_longer_blocks_the_hook(self):
        run = self.hook_repo()
        self.init_real_run()
        run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                  "--kind", "root", "--result", "fail"], cwd=self.repo)
        self.assertEqual(run().returncode, 2)
        r = run_gate(["acknowledge", "--run-dir", self.run_dir, "--reason", "用户放弃这一轮",
                      "--approval-hash", "b" * 64], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run().returncode, 0, run().stderr)


class LoopHarness(GateHarness):
    """挑战循环的 setUp/helpers，不含 test_*——供多个测试类继承而不重复执行用例
    （与 GateHarness 同一惯例；W2 拆出）。"""

    COVERAGE = {
        "acceptance_coverage": True,
        "entry_and_trust_chain": True,
        "data_flow_and_persistence": True,
        "identity_permissions_concurrency_cleanup": True,
        "failure_and_recovery": True,
        "tests_and_evidence": True,
        "release_and_rollback": True,
        "trusted_boundary_stop": True,
    }

    def setUp(self):
        super().setUp()
        self.init([{"scenario_id": "S-1", "required": True}])
        self.plan = self.write("plan.md", "# plan\n\ninitial\n")
        self.contract = self.write("assurance-contract.json", json.dumps({
            "profile": "standard",
            "acceptance_ids": ["AC-01"],
            "protected_assets": [{"id": "ASSET-DEVICE", "description": "target device"}],
            "trusted_assumptions": [{"id": "TRUST-DEV-ACCOUNT", "description": "developer account"}],
            "in_scope_failures": [{"id": "FAIL-WRONG-HOST", "description": "wrong target"}],
            "in_scope_adversaries": [],
            "out_of_scope_conditions": [{"id": "OOS-HOST-OWNER", "description": "host owner compromised"}],
            "maximum_acceptable_impact": "read-only plan review; no target mutation"
        }, ensure_ascii=False))
        r = run_gate(["start-challenge-loop", "--run-dir", self.run_dir,
                      "--loop-type", "plan-iteration", "--target-file", self.plan,
                      "--assurance-contract", self.contract])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.loop_id = r.stdout.strip().splitlines()[-1]
        self.last_hash = sha256_file(self.plan)

    def finding(self, fid, severity="P0", scope="in-scope", origin="pre-existing",
                status="open", evidence="source pointer", ac=None, assurance=None, **extra):
        item = {
            "id": fid,
            "severity": severity,
            "scope_relation": scope,
            "origin": origin,
            "violated_acceptance_ids": ["AC-01"] if ac is None else ac,
            "assurance_contract_ids": ["FAIL-WRONG-HOST"] if assurance is None else assurance,
            "evidence": evidence,
            "status": status,
            "root_cause": extra.pop("root_cause", "missing invariant"),
        }
        item.update(extra)
        return item

    def record(self, round_no, findings, review_mode=None, coverage=None,
               reviewer_verdict=None, based_on=None):
        review_mode = review_mode or ("breadth" if round_no == 1 else "diff")
        payload = {"review_mode": review_mode, "findings": findings}
        if round_no == 1:
            payload["coverage"] = self.COVERAGE if coverage is None else coverage
        fp = self.write("findings-%d.json" % round_no,
                        json.dumps(payload, ensure_ascii=False))
        current_hash = sha256_file(self.plan)
        args = ["record-challenge-round", "--run-dir", self.run_dir,
                "--loop-id", self.loop_id, "--round", str(round_no),
                "--plan-hash", current_hash, "--findings", fp]
        if round_no > 1:
            args += ["--based-on-plan-hash", based_on or self.last_hash]
        if reviewer_verdict:
            args += ["--verdict", reviewer_verdict]
        r = run_gate(args)
        if r.returncode in (0, 1):
            self.last_hash = current_hash
        return r

    def revise_plan(self, marker):
        with open(self.plan, "a", encoding="utf-8") as f:
            f.write(marker + "\n")

    def control(self, action, outcome=None, approval_hash=None, acceptance=None,
                assurance_contract=None):
        args = ["record-challenge-control", "--run-dir", self.run_dir,
                "--loop-id", self.loop_id, "--action", action,
                "--evidence", "reviewed control action"]
        if outcome:
            args += ["--outcome", outcome]
        if approval_hash:
            args += ["--approval-hash", approval_hash]
        if acceptance:
            args += ["--acceptance", acceptance]
        if assurance_contract:
            args += ["--assurance-contract", assurance_contract]
        return run_gate(args)


class ChallengeLoopAssuranceTestCase(LoopHarness):
    """Review-loop 1.4：范围冻结、真实 finding ID 与机器推导收敛状态。"""

    def test_same_finding_id_reworded_is_not_new(self):
        r1 = self.record(1, [self.finding("wrong-host")])
        self.assertIn("NEW_CRITICAL_FINDINGS: 1", r1.stdout)
        self.revise_plan("fix attempt")
        repeated = self.finding("wrong-host", evidence="same issue, different wording")
        r2 = self.record(2, [repeated])
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("NEW_CRITICAL_FINDINGS: 0", r2.stdout)

    def test_same_count_different_ids_is_new(self):
        self.record(1, [self.finding("wrong-host")])
        self.revise_plan("first fix")
        r2 = self.record(2, [self.finding("secret-persistence", origin="new-external-fact",
                                                assurance=["ASSET-DEVICE"])])
        self.assertIn("NEW_CRITICAL_FINDINGS: 1", r2.stdout)

    def test_out_of_scope_hostile_host_is_advisory(self):
        hostile = self.finding(
            "python-sitecustomize", scope="out-of-scope", status="advisory",
            ac=[], assurance=["OOS-HOST-OWNER"])
        r = self.record(1, [hostile], reviewer_verdict="FAIL")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LOOP_STATE: CONVERGED", r.stdout)
        self.assertIn("REVIEWER_VERDICT_IGNORED", r.stdout)

    def test_in_scope_p0_without_acceptance_binding_fails_closed(self):
        bad = self.finding("unbound", ac=[])
        r = self.record(1, [bad])
        self.assertEqual(r.returncode, 2)
        self.assertIn("SCHEMA_INVALID", r.stderr)

    def test_round_three_new_critical_requires_scope_audit(self):
        self.record(1, [self.finding("f-1")])
        self.revise_plan("r2")
        self.record(2, [self.finding("f-2", origin="new-external-fact")])
        self.revise_plan("r3")
        r3 = self.record(3, [self.finding("f-3", origin="new-external-fact")])
        self.assertEqual(r3.returncode, 1)
        self.assertIn("LOOP_STATE: SCOPE_AUDIT_REQUIRED", r3.stdout)
        check = run_gate(["check-loop-limit", "--run-dir", self.run_dir,
                          "--loop-id", self.loop_id])
        self.assertEqual(check.returncode, 1)
        self.assertIn("SCOPE_AUDIT_REQUIRED", check.stdout)
        self.assertEqual(self.control("scope-audit", outcome="continue").returncode, 0)
        self.assertEqual(run_gate(["check-loop-limit", "--run-dir", self.run_dir,
                                  "--loop-id", self.loop_id]).returncode, 0)

    def test_two_consecutive_patch_induced_p0_require_architecture_reset(self):
        self.record(1, [self.finding("base", status="resolved")])
        self.revise_plan("patch one")
        self.record(2, [self.finding("patch-1", origin="patch-induced")])
        self.revise_plan("patch two")
        r3 = self.record(3, [self.finding("patch-2", origin="patch-induced")])
        self.assertEqual(r3.returncode, 1)
        self.assertIn("ARCHITECTURE_RESET_REQUIRED", r3.stdout)

    def test_breadth_coverage_is_required_in_round_one(self):
        r = self.record(1, [], coverage={"acceptance_coverage": True})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BREADTH_REVIEW_INCOMPLETE", r.stderr)

    def test_contract_hash_change_requires_user_approval(self):
        with open(self.contract, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["profile"] = "hostile-host"
        with open(self.contract, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        r = self.record(1, [])
        self.assertEqual(r.returncode, 2)
        self.assertIn("ASSURANCE_CONTRACT_CHANGED", r.stderr)

    def test_acceptance_hash_change_requires_user_approval(self):
        with open(os.path.join(self.tmp, "acceptance.md"), "a", encoding="utf-8") as f:
            f.write("AC-02 MUST: silently expanded scope\n")
        r = self.record(1, [])
        self.assertEqual(r.returncode, 2)
        self.assertIn("ACCEPTANCE_CHANGED", r.stderr)

    def test_approved_scope_change_can_replace_acceptance_snapshot(self):
        proposal = self.finding("add-approved-scope", scope="scope-change-proposal",
                                assurance=["FAIL-WRONG-HOST"])
        self.assertIn("USER_SCOPE_APPROVAL_REQUIRED", self.record(1, [proposal]).stdout)
        acceptance = os.path.join(self.tmp, "acceptance.md")
        with open(acceptance, "a", encoding="utf-8") as f:
            f.write("AC-02 MUST: user-approved scope extension\n")
        approved = self.control("scope-change-approved", outcome="continue",
                                approval_hash="b" * 64, acceptance=acceptance)
        self.assertEqual(approved.returncode, 0, approved.stdout + approved.stderr)
        self.revise_plan("approved scope reflected")
        resolved = self.finding("add-approved-scope", scope="scope-change-proposal",
                                status="resolved", assurance=["FAIL-WRONG-HOST"])
        r2 = self.record(2, [resolved])
        self.assertEqual(r2.returncode, 2)
        self.assertIn("CONSOLIDATED_REVIEW_REQUIRED", r2.stderr)

    def test_reviewer_pass_cannot_override_open_blocker(self):
        r = self.record(1, [self.finding("still-open")], reviewer_verdict="PASS")
        self.assertEqual(r.returncode, 0)
        self.assertIn("LOOP_STATE: CONTINUE", r.stdout)
        self.assertIn("REVIEWER_VERDICT_IGNORED", r.stdout)

    def test_round_sequence_and_base_hash_are_fail_closed(self):
        self.record(1, [])
        self.revise_plan("r2")
        r = self.record(3, [], based_on="0" * 64)
        self.assertEqual(r.returncode, 2)
        self.assertIn("ROUND_SEQUENCE_INVALID", r.stderr)

    def test_preexisting_finding_after_round_one_explains_late_discovery(self):
        self.record(1, [])
        self.revise_plan("r2")
        r = self.record(2, [self.finding("late-preexisting")])
        self.assertEqual(r.returncode, 2)
        self.assertIn("LATE_FINDING_UNEXPLAINED", r.stderr)
        explained = self.finding("late-preexisting",
                                 why_not_found_in_round_one="new source file was supplied")
        r = self.record(2, [explained])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_standard_profile_keeps_aiphone_host_owner_risks_advisory(self):
        findings = [
            self.finding("wrong-phone"),
            self.finding("secret-on-disk", assurance=["ASSET-DEVICE"]),
            self.finding("sitecustomize-prehook", scope="out-of-scope", status="advisory",
                         ac=[], assurance=["OOS-HOST-OWNER"]),
            self.finding("shell-prehook", scope="out-of-scope", status="advisory",
                         ac=[], assurance=["OOS-HOST-OWNER"]),
        ]
        r = self.record(1, findings)
        self.assertIn("NEW_CRITICAL_FINDINGS: 2", r.stdout)
        self.assertIn("ADVISORY_FINDINGS: 2", r.stdout)

    def test_hard_limit_blocks_without_resetting_history(self):
        # Test-specific policy proves hard-stop semantics without spending eight rounds.
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            ledger = json.load(f)
        self.assertEqual(ledger["challenge_loops"][0]["limits"]["hard"], 8)
        for n in range(1, 9):
            if n > 1:
                self.revise_plan("round-%d" % n)
            finding = self.finding("f-%d" % n, origin="new-external-fact" if n > 1 else "pre-existing")
            r = self.record(n, [finding])
            if n == 3:
                self.assertIn("SCOPE_AUDIT_REQUIRED", r.stdout)
                self.control("scope-audit", outcome="continue")
            if n == 5:
                self.assertIn("USER_REVIEW_REQUIRED", r.stdout)
                self.control("user-review", outcome="continue")
        self.assertEqual(r.returncode, 1)
        self.assertIn("LOOP_STATE: BLOCKED", r.stdout)

    def test_scope_change_can_only_resume_with_user_approval(self):
        proposal = self.finding("need-hostile-host", scope="scope-change-proposal",
                                assurance=["OOS-HOST-OWNER"])
        r = self.record(1, [proposal])
        self.assertEqual(r.returncode, 1)
        self.assertIn("USER_SCOPE_APPROVAL_REQUIRED", r.stdout)
        bad = self.control("scope-change-approved", outcome="continue")
        self.assertEqual(bad.returncode, 2)
        good = self.control("scope-change-approved", outcome="continue",
                            approval_hash="a" * 64)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)

    def test_malformed_findings_fail_closed_stably(self):
        for index, payload in enumerate((None, [], "bad", {"review_mode": "breadth", "findings": None})):
            with self.subTest(payload=payload):
                fp = self.write("malformed-%d.json" % index, json.dumps(payload))
                r = run_gate(["record-challenge-round", "--run-dir", self.run_dir,
                              "--loop-id", self.loop_id, "--round", "1",
                              "--plan-hash", sha256_file(self.plan), "--findings", fp])
                self.assertEqual(r.returncode, 2)
                self.assertIn("SCHEMA_INVALID", r.stderr)
        r = run_gate(["record-challenge-round", "--run-dir", self.run_dir,
                      "--loop-id", self.loop_id, "--round", "-1",
                      "--plan-hash", sha256_file(self.plan), "--findings", fp])
        self.assertEqual(r.returncode, 2)
        self.assertIn("ROUND_SEQUENCE_INVALID", r.stderr)
        bad_id = self.finding("valid-id")
        bad_id["id"] = []
        r = self.record(1, [bad_id])
        self.assertEqual(r.returncode, 2)
        self.assertIn("SCHEMA_INVALID", r.stderr)

    def test_control_events_cannot_be_pre_authorized(self):
        """W3 语义更新：预授权防线从「记不进去」改为「记进去但不满足门的要求」。

        入口无条件化后，user-initiated 事件必须绑 hash 才能记录，且**永不**清除
        门此前/此后的 pending 要求——否则先记一条再触发要求即可让升级永不出现
        （第 5 轮审计 §5.3 的预授权漏洞）。"""
        # (a) 门未要求 + 无 hash → 拒绝（新码 CONTROL_APPROVAL_REQUIRED）
        r = self.control("scope-audit", outcome="continue")
        self.assertEqual(r.returncode, 2)
        self.assertIn("CONTROL_APPROVAL_REQUIRED", r.stderr)
        # (b) 门未要求 + 带 hash → 如实记录为 user-initiated
        r = self.control("scope-audit", outcome="continue", approval_hash="c" * 64)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # (c) 预记录不满足门的要求：攒满 3 轮新增关键 finding，
        #     SCOPE_AUDIT_REQUIRED 必须照常出现（user-initiated 不算数）
        for n in range(1, 4):
            if n > 1:
                self.revise_plan("round-%d" % n)
            r = self.record(n, [self.finding(
                "pa-%d" % n,
                origin="new-external-fact" if n > 1 else "pre-existing")])
        self.assertIn("SCOPE_AUDIT_REQUIRED", r.stdout,
                      "预先记录的 user-initiated scope-audit 不得关闭该升级")
        # (d) 门要求之下的 gate-requested 回应才算满足
        ok = self.control("scope-audit", outcome="continue")
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_architecture_reset_requires_changed_plan_and_consolidated_review(self):
        self.record(1, [self.finding("base", status="resolved")])
        self.revise_plan("patch one")
        self.record(2, [self.finding("patch-1", origin="patch-induced")])
        self.revise_plan("patch two")
        self.record(3, [self.finding("patch-2", origin="patch-induced")])
        unchanged = self.control("architecture-reset")
        self.assertEqual(unchanged.returncode, 2)
        self.assertIn("ARCHITECTURE_RESET_INCOMPLETE", unchanged.stderr)
        self.revise_plan("architecture rewritten")
        reset = self.control("architecture-reset")
        self.assertEqual(reset.returncode, 0, reset.stdout + reset.stderr)
        bad = self.record(4, [], review_mode="diff")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("CONSOLIDATED_REVIEW_REQUIRED", bad.stderr)
        payload = {"review_mode": "consolidated", "coverage": self.COVERAGE,
                   "findings": [self.finding("patch-1", origin="patch-induced", status="resolved"),
                                self.finding("patch-2", origin="patch-induced", status="resolved")]}
        fp = self.write("findings-4-consolidated.json", json.dumps(payload, ensure_ascii=False))
        r = run_gate(["record-challenge-round", "--run-dir", self.run_dir,
                      "--loop-id", self.loop_id, "--round", "4",
                      "--plan-hash", sha256_file(self.plan),
                      "--based-on-plan-hash", self.last_hash, "--findings", fp])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LOOP_STATE: CONVERGED", r.stdout)

    def test_schema_13_legacy_loop_remains_readable(self):
        spec = importlib.util.spec_from_file_location("plan_test_gate_compat", GATE)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        legacy = {
            "schema_version": "1.3.0", "run_id": "legacy", "source_request": {},
            "scenarios": [], "runs": [], "evidence": [],
            "challenge_loops": [{
                "loop_id": "plan-iteration-001", "loop_type": "plan-iteration",
                "target_file": "plan.md", "baseline_hash": "a" * 64,
                "rounds": [{"round": 1, "plan_hash": "a" * 64,
                            "findings": {"critical": 1, "major": 0, "minor": 0}}],
                "status": "active"
            }]
        }
        errors = gate.structural_check(legacy)
        self.assertFalse([e for e in errors if "challenge_loops" in e], errors)


class ExecRecordRunTestCase(RealRepoAttestationTestCase):
    """record-run --exec（2026-08-19）：gate 亲眼执行，exit code 决定 result，
    输出日志自动成为 primary 证据——堵"一次执行扇出成 N 条自报 pass"。"""

    def init_two_scenarios(self):
        self.init_real_run(scenarios=[{"scenario_id": "S-1", "required": True},
                                      {"scenario_id": "S-2", "required": True}])

    def test_exec_pass_records_result_and_primary_evidence(self):
        self.init_two_scenarios()
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-2",
                      "--kind", "root", "--exec", "--",
                      sys.executable, "-c", "print('hello-gate')"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("EXEC log=", r.stdout)
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            led = json.load(f)
        mine = [x for x in led["runs"] if x.get("scenario_id") == "S-2"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["result"], "pass")
        self.assertEqual(mine[0]["exec_exit_code"], 0)
        evs = [e for e in led["evidence"] if e.get("scenario_id") == "S-2"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["kind"], "primary")
        log_path = os.path.join(self.run_dir, evs[0]["path"])
        self.assertIn("hello-gate", read_utf8(log_path))

        # A run and its automatic primary log are one atomic ledger write.
        # The next legitimate CLI write must not be rejected as a truncated
        # integrity chain merely because that write produced two fact rows.
        again = run_gate(
            ["checkpoint", "--run-dir", self.run_dir, "--note", "after exec"],
            cwd=self.repo,
        )
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_exec_fail_records_fail_and_transparent_exit(self):
        self.init_two_scenarios()
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-2",
                      "--kind", "root", "--exec", "--",
                      sys.executable, "-c", "import sys; sys.exit(3)"], cwd=self.repo)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)  # 如实透传
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            led = json.load(f)
        mine = [x for x in led["runs"] if x.get("scenario_id") == "S-2"]
        self.assertEqual(mine[0]["result"], "fail")

    def test_exec_rejects_self_reported_result(self):
        self.init_two_scenarios()
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-2",
                      "--kind", "root", "--result", "pass", "--exec", "--",
                      sys.executable, "-c", "pass"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("不许自报", r.stderr)

    def test_no_result_no_exec_is_usage_error(self):
        self.init_two_scenarios()
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-2",
                      "--kind", "root"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("须给 --result", r.stderr)

    def test_exec_unknown_scenario_rejected_before_running(self):
        self.init_two_scenarios()
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-9",
                      "--kind", "root", "--exec", "--",
                      sys.executable, "-c", "pass"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("不在 init 冻结的场景清单", r.stderr)


class ExposureAdvisoryTestCase(RealRepoAttestationTestCase):
    """自报暴露规则；fanout 缺独立证据为 error，其余启发式保持 advisory。"""

    def audit_real(self, engine="opus-4.8", output_json=None):
        with open(os.path.join(self.run_dir, "auditor-input.json"), "w",
                  encoding="utf-8") as f:
            f.write('{"frozen": true}')
        with open(os.path.join(self.run_dir, "auditor-output.json"), "w",
                  encoding="utf-8") as f:
            f.write(output_json if output_json is not None else '{"verdict": "PASS"}')
        r = run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS",
                      "--engine", engine,
                      "--input", "auditor-input.json",
                      "--output", "auditor-output.json"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def finalize_full(self):
        return run_gate(["finalize", "--run-dir", self.run_dir], cwd=self.repo)

    def test_evidence_free_finalize_exposed_but_not_blocking(self):
        """required 全 PASS 但零 primary 证据 → advisory 曝光，不拦截交付。"""
        self.init_real_run(executor_engine="claude")
        self.audit_real()
        r = self.finalize_full()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("EVIDENCE_FREE_FINALIZE", r.stdout)

    def test_primary_evidence_silences_evidence_free(self):
        self.init_real_run(executor_engine="claude")
        self.write("plans/p/verification/run-1/artifacts/out.log", "pytest ok\n")
        r = run_gate(["attach-evidence", "--run-dir", self.run_dir,
                      "--path", "artifacts/out.log", "--kind", "primary",
                      "--scenario", "S-1"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.audit_real()
        r = self.finalize_full()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("EVIDENCE_FREE_FINALIZE", r.stdout)

    def test_executor_engine_undeclared_exposed(self):
        self.init_real_run()  # 未声明 executor_engine
        self.audit_real()
        r = self.finalize_full()
        self.assertIn("EXECUTOR_ENGINE_UNDECLARED", r.stdout)

    def test_auditor_engine_mismatch_exposed(self):
        self.init_real_run(executor_engine="claude", auditor_engine="opus-4.8")
        self.audit_real(engine="gpt-5")
        r = self.finalize_full()
        self.assertIn("AUDITOR_ENGINE_MISMATCH", r.stdout)
        self.assertIn("opus-4.8", r.stdout)

    def test_open_deferrals_exposed(self):
        self.init_real_run(executor_engine="claude")
        self.audit_real(output_json=json.dumps({
            "verdict": "PASS",
            "findings": [{"id": "E-1", "severity": "info", "status": "deferred",
                          "text": "真实 LLM 对话 E2E 留待 slice 5"}]}))
        r = self.finalize_full()
        self.assertIn("OPEN_DEFERRALS", r.stdout)
        self.assertIn("E-1", r.stdout)

    def test_fanout_requires_independent_primary_evidence(self):
        """required 场景扇出缺独立证据时拦截；每场景有证据时放行。"""
        spec = importlib.util.spec_from_file_location("plan_test_gate_fanout", GATE)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        base = {
            "schema_version": gate.SCHEMA_VERSION, "run_id": "t", "source_request": {},
            "scenarios": [{"scenario_id": "S-1", "required": True},
                          {"scenario_id": "S-2", "required": True}],
            "evidence": [], "applicability": {},
        }
        fanout_runs = [
            {"scenario_id": "S-1", "kind": "root", "result": "pass",
             "command": "pytest -q", "recorded_at": "2026-08-18T18:56:24+0800"},
            {"scenario_id": "S-2", "kind": "root", "result": "pass",
             "command": "pytest -q", "recorded_at": "2026-08-18T18:56:24+0800"},
        ]
        diags, _ = gate.validate(self.run_dir, dict(base, runs=fanout_runs),
                                 mode="full", fixture=False)
        fanout_diags = [d for d in diags if d.code == "RUN_ATTESTATION_FANOUT"]
        self.assertEqual(len(fanout_diags), 1)
        self.assertEqual(fanout_diags[0].severity, "error")
        # 每个 required 场景都有独立 primary evidence → 不报 fanout
        evidenced = dict(base, runs=fanout_runs, evidence=[
            {"evidence_id": "E-1", "scenario_id": "S-1", "kind": "primary",
             "path": "artifacts/s1.log"},
            {"evidence_id": "E-2", "scenario_id": "S-2", "kind": "primary",
             "path": "artifacts/s2.log"},
        ])
        diags, _ = gate.validate(self.run_dir, evidenced, mode="full", fixture=False)
        self.assertNotIn("RUN_ATTESTATION_FANOUT", {d.code for d in diags})
        # 不同时间戳 → 不曝光
        staggered = [dict(r, recorded_at="2026-08-18T18:56:2%d+0800" % i)
                     for i, r in enumerate(fanout_runs)]
        diags, _ = gate.validate(self.run_dir, dict(base, runs=staggered),
                                 mode="full", fixture=False)
        self.assertNotIn("RUN_ATTESTATION_FANOUT", {d.code for d in diags})
        # fixture 免检
        diags, _ = gate.validate(self.run_dir, dict(base, runs=fanout_runs),
                                 mode="full", fixture=True)
        self.assertNotIn("RUN_ATTESTATION_FANOUT", {d.code for d in diags})


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ToolchainRecordingTestCase(GateHarness):
    """开账即记工具链与环境（2026-08-28）。

    动机是一次跨机器的 run log 合并分析：账本此前只有 `schema_version`，而它在插件
    v0.4.0→v0.4.1、8/11→8/28 全程都是 `1.5.0`，于是"这一轮是哪版 gate、哪台机器跑的"
    事后完全查不到——一批诚实工作中触发的 LEDGER_TAMPERED 因此无法定性。
    """

    def _init_run(self):
        mf = self.manifest([{"scenario_id": "S-1", "required": True,
                             "title": "冷启动", "cold_start": True}])
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mf])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.run_dir, "plan-test-run.json"),
                  encoding="utf-8") as f:
            return json.load(f)

    def test_init_records_toolchain(self):
        tc = self._init_run().get("toolchain") or {}
        for key in ("gate_version", "gate_sha256", "gate_path", "plugin_version",
                    "python_version", "platform", "host", "recorded_at"):
            self.assertIn(key, tc)
        self.assertEqual(tc["gate_version"], "1.5.0")
        # gate_sha256 是这里最硬的一条：版本号可以忘了升，文件哈希不会。
        self.assertRegex(tc["gate_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(tc["gate_path"].endswith("plan_test_gate.py"))
        self.assertEqual(tc["plugin_version"], expected_plugin_version())

    def test_toolchain_is_frozen_by_the_integrity_chain(self):
        """工具链写在链首 init 之前，事后改它 → LEDGER_TAMPERED。

        这一条保证记账不是装饰：伪造"我是用旧版跑的"要连链一起重写。
        """
        self._init_run()
        p = os.path.join(self.run_dir, "plan-test-run.json")
        with open(p, encoding="utf-8") as f:
            led = json.load(f)
        led["toolchain"]["gate_version"] = "0.0.1-伪造"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
        r = run_gate(["finalize", "--run-dir", self.run_dir, "--check-only"])
        self.assertIn("LEDGER_TAMPERED", r.stdout + r.stderr)

    def _render_report(self):
        run_gate(["render", "--run-dir", self.run_dir])   # render 把正文写进 report.md
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            return f.read()

    def test_render_surfaces_toolchain(self):
        self._init_run()
        report = self._render_report()
        self.assertIn("TOOLCHAIN", report)
        self.assertIn("gate_sha256", report)
        ver = expected_plugin_version()
        self.assertIn(ver if ver else "plugin ?", report)

    def test_ledger_without_toolchain_still_renders(self):
        """加字段不能让上一版 validator 建的账本集体作废（迁移断裂是本仓明令禁止的）。"""
        self._init_run()
        p = os.path.join(self.run_dir, "plan-test-run.json")
        with open(p, encoding="utf-8") as f:
            led = json.load(f)
        led.pop("toolchain")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
        self.assertIn("无版本/环境信息", self._render_report())


class SiblingRunUnresolvedTestCase(RealRepoAttestationTestCase):
    """换目录洗账本：红轮丢在原地、新开一轮全绿拿 receipt（2026-08-28）。

    真实数据（18 本账本 + 8 处轮换现场）：`fail` 粘性 ⇒ 唯一出路是新建 run-00N+1；而配套的
    `retire --superseded-by` 没有任何东西检查它做没做 ⇒ 5 次轮换里 4 次没挂账，retire/
    acknowledge 全局使用次数为 0，被丢弃的账本里躺着 75 条测试事实、16 条 root fail。
    """

    def sibling(self, name, scenario_ids, result="fail", fixture=False):
        """在同一个 verification/ 下造一个有测试事实的兄弟 run。"""
        d = os.path.join(self.repo, "plans", "p", "verification", name)
        os.makedirs(os.path.join(d, "artifacts"), exist_ok=True)
        if not os.path.exists(os.path.join(self.repo, "acceptance.md")):
            self.write("acceptance.md", "AC-1 必须：脚本可运行\n")
        manifest = {
            "run_id": name, "repo_root": self.repo, "source_request_text": "兄弟轮",
            "acceptance_file": os.path.join(self.repo, "acceptance.md"),
            "applicability": self.applicability_block(),
            "fixture_only": fixture,
            "scenarios": [{"scenario_id": s, "required": True} for s in scenario_ids],
        }
        mp = os.path.join(d, "manifest.json")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", d, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_gate(["record-run", "--run-dir", d, "--scenario", scenario_ids[0],
                      "--kind", "root", "--result", result], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return d

    def test_unresolved_red_sibling_blocks_receipt(self):
        self.sibling("run-0", ["S-1"])
        self.init_real_run()
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("SIBLING_RUN_UNRESOLVED", r.stdout)
        self.assertIn("root fail 1 条", r.stdout)

    def test_disjoint_scenarios_are_not_my_history(self):
        """真实反例：`2026-08-18-memory-sdk-integration/verification/` 下 run-1..run-4
        分别测 AC-1..4 / AC-5..8 / AC-9..11 / AC-12..14，用四份不同 manifest——那是四个
        不同 slice 各测各的。只按目录判会把它们全判成互相欠账，谁都发不出 receipt。
        """
        self.sibling("run-slice2", ["AC-5", "AC-6"])
        self.init_real_run()
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("SIBLING_RUN_UNRESOLVED", r.stdout)

    def test_init_only_sibling_is_not_blocking(self):
        """纯 init、没跑过的空账本不藏失败史，拦它只是噪音。"""
        d = os.path.join(self.repo, "plans", "p", "verification", "run-0")
        os.makedirs(os.path.join(d, "artifacts"), exist_ok=True)
        self.write("acceptance.md", "AC-1 必须：脚本可运行\n")
        manifest = {
            "run_id": "run-0", "repo_root": self.repo, "source_request_text": "空轮",
            "acceptance_file": os.path.join(self.repo, "acceptance.md"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-1", "required": True}],
        }
        mp = os.path.join(d, "manifest.json")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False))
        run_gate(["init", "--run-dir", d, "--manifest", mp], cwd=self.repo)
        self.init_real_run()
        self.assertNotIn("SIBLING_RUN_UNRESOLVED", self.check().stdout)

    def test_fixture_sibling_is_ignored(self):
        self.sibling("run-fix", ["S-1"], fixture=True)
        self.init_real_run()
        self.assertNotIn("SIBLING_RUN_UNRESOLVED", self.check().stdout)

    def test_handwritten_retired_sibling_still_blocks(self):
        """给红账本手加一行 `"retired": true` 是绕过本门最省事的路径——必须不认。

        兄弟轮的 integrity 链不由本 run 的 validate 核对，所以这里单独查"链里有没有
        retire 这一笔操作"，与 retire-status 同口径。
        """
        d = self.sibling("run-0", ["S-1"])
        p = os.path.join(d, "plan-test-run.json")
        with open(p, encoding="utf-8") as f:
            led = json.load(f)
        led["retired"] = True
        led["superseded_by"] = "plans/p/verification/run-1"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
        self.init_real_run()
        self.assertIn("SIBLING_RUN_UNRESOLVED", self.check().stdout)

    def test_retire_then_finalize_is_the_legal_way_out(self):
        """完整的正当出口，也是死锁已解的端到端证明。

        顺序：兄弟轮红 → 本轮全绿（此时被兄弟轮挡住，拿不到 receipt）→ retire 兄弟轮
        （继任者尚未盖章也接受）→ 本轮 finalize 通过。
        """
        sib = self.sibling("run-0", ["S-1"])
        # 兄弟 run-dir 必须在 init 显式声明才不算交付内容（PROTOCOL 的防绕过决定：
        # 按 `.../verification/<x>/` 路径形态自动排除，等于给"藏后门"开了个口子）。
        # 不声明的话，下面 retire 写兄弟账本会把本轮打成 TESTED_RUNTIME_MISMATCH。
        self.init_real_run(related_run_dirs=["plans/p/verification/run-0"])
        # 本轮补齐证据与审计，做到"全绿但尚未盖章"
        with open(os.path.join(self.run_dir, "artifacts", "s1.log"), "w") as f:
            f.write("ok")
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                  "artifacts/s1.log", "--kind", "primary", "--scenario", "S-1"],
                 cwd=self.repo)
        for name, body in (("auditor-input.json", '{"frozen":true}'),
                           ("auditor-output.json", '{"verdict":"PASS"}')):
            with open(os.path.join(self.run_dir, name), "w") as f:
                f.write(body)
        run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS", "--engine",
                  "e", "--input", "auditor-input.json", "--output",
                  "auditor-output.json"], cwd=self.repo)
        # 全绿也拿不到 receipt——兄弟轮那段历史还没交代
        blocked = run_gate(["finalize", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("SIBLING_RUN_UNRESOLVED", blocked.stdout)
        # 正当出口：把红轮退役给本轮（本轮尚无 receipt 也接受，否则两边死锁）
        r = run_gate(["retire", "--run-dir", sib, "--reason", "被 run-1 取代",
                      "--superseded-by", "plans/p/verification/run-1"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_gate(["finalize", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("SIBLING_RUN_UNRESOLVED", r.stdout)
        # 退役至此才落地
        st = run_gate(["retire-status", "--run-dir", sib], cwd=self.repo)
        self.assertEqual(st.returncode, 0, st.stdout + st.stderr)

    def test_acknowledged_sibling_stops_blocking(self):
        sib = self.sibling("run-0", ["S-1"])
        approval = hashlib.sha256("我确认放弃这一轮".encode("utf-8")).hexdigest()
        r = run_gate(["acknowledge", "--run-dir", sib, "--reason", "用户放弃",
                      "--approval-hash", approval], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.init_real_run()
        self.assertNotIn("SIBLING_RUN_UNRESOLVED", self.check().stdout)


class ChainLengthInvariantTestCase(RealRepoAttestationTestCase):
    """链长下界必须对**每一条**写入命令成立：Δ(expected_chain_length) ≤ Δ(len(chain.log))。

    为什么值得单独一个用例（2026-08-28，从 5 次真实误报回溯出来的）：
      `record-run --exec` 在一次 CLI 写入里同时追加 run 与它抓到的执行日志（2 条事实、
      1 条链），而 `expected_chain_length` 是**手工维护的枚举**。该特性 2026-08-19 上线，
      给它补的折扣 2026-08-24 才上线——中间 5 天，每跑一次 `--exec` 就让**下一条**命令
      报 `LEDGER_TAMPERED`。真实日志里 5 次触发全部由此解释，其中一次连跑 17 次 `--exec`、
      缺口正好 16。

    症状为什么严重：`LEDGER_TAMPERED` 是阻塞级、没有任何修复命令，账本一旦被误判就是死的，
    代理只能换 run-dir 重开——而那正是 `SIBLING_RUN_UNRESOLVED` 要堵的行为。一个门的误报
    直接喂给另一个门。

    所以修的不是那一条折扣，是**让下一条犯同样错误的命令在这里失败，而不是在用户账本里失败**。
    新增写入命令时请在下面补一行。
    """

    def _state(self):
        with open(os.path.join(self.run_dir, "plan-test-run.json"), encoding="utf-8") as f:
            led = json.load(f)
        chain = len((led.get("integrity") or {}).get("log") or [])
        return chain, gate_module().expected_chain_length(led)

    def test_every_write_command_keeps_the_chain_length_bound(self):
        self.init_real_run()          # init + 一条 record-run
        prev = self._state()
        self.assertGreaterEqual(prev[0], prev[1],
                                "init 之后链长下界就已经不成立")

        approval = hashlib.sha256("同意".encode("utf-8")).hexdigest()
        self.write("target.md", "plan v1\n")
        contract = self.write("assurance.json", json.dumps(
            {"obligations": [], "version": 1}, ensure_ascii=False))
        with open(os.path.join(self.run_dir, "artifacts", "a.log"), "w") as f:
            f.write("ok")

        steps = [
            ("checkpoint", ["checkpoint", "--run-dir", self.run_dir,
                            "--slice", "s", "--note", "n"]),
            ("phase-start", ["phase-start", "--run-dir", self.run_dir,
                             "--phase", "phase-3"]),
            ("phase-end", ["phase-end", "--run-dir", self.run_dir,
                           "--phase", "phase-3"]),
            ("attach-evidence", ["attach-evidence", "--run-dir", self.run_dir,
                                 "--path", "artifacts/a.log", "--kind", "primary",
                                 "--scenario", "S-1"]),
            # 这一条就是当年的肇事者：一次写入 = run + 执行日志两条事实
            ("record-run --exec", ["record-run", "--run-dir", self.run_dir,
                                   "--scenario", "S-1", "--kind", "retry", "--exec",
                                   "--", sys.executable, "-c", "print(1)"]),
            ("record-timing --exec", ["record-timing", "--run-dir", self.run_dir,
                                      "--phase", "phase-4", "--activity-class",
                                      "automated_test", "--exec", "--",
                                      sys.executable, "-c", "print(2)"]),
            ("record-timing 声明", ["record-timing", "--run-dir", self.run_dir,
                                    "--phase", "phase-4", "--activity-class",
                                    "automated_test",
                                    "--declared-start", "2026-08-28T10:00:00+0800",
                                    "--declared-end", "2026-08-28T10:05:00+0800"]),
            ("declare-status", ["declare-status", "--run-dir", self.run_dir,
                                "--source", "acceptance.md", "--scenario", "S-1",
                                "--status", "PASS"]),
            ("record-approval", ["record-approval", "--run-dir", self.run_dir,
                                 "--kind", "all-ai-driving",
                                 "--message-hash", approval, "--note", "n"]),
            ("record-phase-transition", ["record-phase-transition", "--run-dir", self.run_dir,
                                         "--from-phase", "phase-3", "--to-phase", "phase-4",
                                         "--evidence", "e", "--note", "n"]),
            ("record-plan-defect", ["record-plan-defect", "--run-dir", self.run_dir,
                                    "--affected-tasks", "T1", "--defect-type",
                                    "contract-conflict", "--description", "d"]),
            ("start-challenge-loop", ["start-challenge-loop", "--run-dir", self.run_dir,
                                      "--loop-type", "plan-iteration",
                                      "--target-file", "target.md",
                                      "--assurance-contract", contract]),
            ("re-attest", ["re-attest", "--run-dir", self.run_dir, "--reason", "文档回写"]),
        ]
        for label, args in steps:
            r = run_gate(args, cwd=self.repo)
            if r.returncode != 0:      # 该命令本身被别的门拒绝，不是本用例要测的
                continue
            chain, need = self._state()
            self.assertGreaterEqual(
                chain, need,
                "%s 之后链长下界被打破（链 %d 条 < 事实 %d 条）——下一条 CLI 命令会误报 "
                "LEDGER_TAMPERED，账本就此报废。请在 expected_chain_length 里为它补上折扣。"
                % (label, chain, need))
            prev = (chain, need)

        # 收尾复核：整条链仍自洽（不只是长度，值也对得上）
        with open(os.path.join(self.run_dir, "plan-test-run.json"),
                  encoding="utf-8") as f:
            self.assertIsNone(gate_module().integrity_check(json.load(f)))

class DecisionPrimitiveTestCase(GateHarness):
    """W3-10：decision 原语——随时可记 / hash 必填 / 豁免降级且强制公示 / 完整性码不可豁免。"""

    def setUp(self):
        super().setUp()
        self.init([{"scenario_id": "S-1", "required": True}])

    def _decide(self, effect, subject="*", hash_="d" * 64,
                rationale="业主批准：该场景本批不做，见批准原话", initiator="user-initiated"):
        return run_gate(["record-decision", "--run-dir", self.run_dir,
                         "--effect", effect, "--subject", subject,
                         "--initiator", initiator, "--approval-hash", hash_,
                         "--rationale", rationale])

    def _check(self):
        r = run_gate(["finalize", "--run-dir", self.run_dir, "--check-only"])
        return r.stdout

    def test_input_validation_fails_closed(self):
        self.assertEqual(self._decide("waive:NOT_A_CODE").returncode, 2)
        self.assertEqual(self._decide("REQUIRED_SCENARIO_NOT_RUN").returncode, 2)
        self.assertEqual(
            self._decide("waive:REQUIRED_SCENARIO_NOT_RUN", hash_="xyz").returncode, 2)
        self.assertEqual(
            self._decide("waive:REQUIRED_SCENARIO_NOT_RUN", rationale="短").returncode, 2)

    def test_integrity_codes_are_not_waivable(self):
        for code in ("SCHEMA_INVALID", "LEDGER_TAMPERED"):
            r = self._decide("waive:%s" % code)
            self.assertEqual(r.returncode, 2, code)
            self.assertIn("不可豁免", r.stderr)

    def test_waiver_demotes_error_and_publishes(self):
        self.assertIn("DIAG REQUIRED_SCENARIO_NOT_RUN", self._check())
        r = self._decide("waive:REQUIRED_SCENARIO_NOT_RUN", subject="S-1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self._check()
        self.assertNotIn("DIAG REQUIRED_SCENARIO_NOT_RUN", out,
                         "命中的 error 应降为 advisory")
        self.assertIn("ADVISORY REQUIRED_SCENARIO_NOT_RUN", out)
        self.assertIn("已豁免", out)
        run_gate(["render", "--run-dir", self.run_dir])
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            report = f.read()
        self.assertIn("生效中的豁免", report, "render 报告必须公示豁免——豁免不隐身")
        self.assertIn("dddddddddddd", report, "豁免的 hash 前缀必须可见")

    def test_subject_scoping(self):
        r = self._decide("waive:REQUIRED_SCENARIO_NOT_RUN", subject="S-OTHER")
        self.assertEqual(r.returncode, 0)
        self.assertIn("DIAG REQUIRED_SCENARIO_NOT_RUN", self._check(),
                      "subject 不匹配的 decision 不得豁免别的场景")


class ScopeApproveConsolidatedTestCase(LoopHarness):
    """W3-12：consolidated 只在结构真变时强制——只批准处置不换约，下轮 diff 即可。"""

    def test_approve_without_snapshot_does_not_force_consolidated(self):
        proposal = self.finding("prop-only", scope="scope-change-proposal",
                                assurance=["FAIL-WRONG-HOST"])
        r = self.record(1, [proposal])
        self.assertIn("USER_SCOPE_APPROVAL_REQUIRED", r.stdout)
        ok = self.control("scope-change-approved", outcome="continue",
                          approval_hash="a" * 64)     # 不带 --acceptance：不换约
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.revise_plan("processed proposal")
        resolved = self.finding("prop-only", scope="scope-change-proposal",
                                status="resolved", assurance=["FAIL-WRONG-HOST"])
        r2 = self.record(2, [resolved], review_mode="diff")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)


class PlanChallengeUnresolvedTestCase(LoopHarness):
    """W2-6：挑战循环必须进 finalize 判定——未收敛的 loop 不得拿 receipt。

    依据（第 5 轮审计 §4.2/§4.3）：4 张历史 receipt 全部发在**没有**挑战循环的账本上，
    跑过循环的 7 本一张都没有；validate()（当时 1335-1905）零引用 challenge_loops，
    三个 LOOP_* 诊断码无产生点——「计划被严格挑战过」从未进过任何成绩单。"""

    def _check_codes(self):
        r = run_gate(["finalize", "--run-dir", self.run_dir, "--check-only"])
        return {l.split()[1].rstrip(":") for l in r.stdout.splitlines()
                if l.startswith("DIAG ")}

    def test_open_loop_blocks(self):
        # setUp 刚 start-challenge-loop、零轮次——循环存在且远未收敛
        self.assertIn("PLAN_CHALLENGE_UNRESOLVED", self._check_codes(),
                      "存在未收敛的挑战循环时 finalize 必须拦")

    def test_converged_loop_passes(self):
        r = self.record(1, [])          # 第一轮零 finding → 机器推导 CONVERGED
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CONVERGED", r.stdout)
        self.assertNotIn("PLAN_CHALLENGE_UNRESOLVED", self._check_codes(),
                         "已收敛的循环不得再拦")

    def test_loop_with_open_p0_blocks(self):
        r = self.record(1, [self.finding("real-bug")])   # open P0 → CONTINUE，非 CONVERGED
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LOOP_STATE: CONTINUE", r.stdout)
        self.assertIn("PLAN_CHALLENGE_UNRESOLVED", self._check_codes())


class FindingSchemaHelpTestCase(GateHarness):
    """§4 挑战层报错手感：枚举错误必须自带合法取值，且有可复制模板。

    run log 实证（HANDOFF-2026-08-28-runlog.md §4）：SCHEMA_INVALID 真实触发 20 次，
    其中 13 次是纯格式问题——id 不合正则 5、缺必填字段 4、未知字段 2、元素非 object 2。
    典型错法 scope_relation='in_scope'（要连字符）、origin='upstream_contract'（非法枚举），
    而当时报错只回一个正则或一句"非法"。这些错误不拦任何实质风险，只烧轮次。

    本用例锁住：报错必须列出合法取值/必填字段清单，print-schema 的模板必须自洽。
    新增 finding 字段或枚举值时，这里会跟着变红——那是提醒你同步模板与文档。
    """

    LOOP = {"contract_snapshots": [
        {"acceptance_ids": ["AC-1"], "assurance_ids": ["ASR-1"]}]}

    def _template(self):
        proc = run_gate(["print-schema", "--format", "template"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_template_is_self_consistent(self):
        """模板本身必须过校验——否则它教出来的就是错的。"""
        g = gate_module()
        tpl = self._template()
        self.assertEqual(set(tpl["coverage"]), g.BREADTH_COVERAGE_KEYS,
                         "模板 coverage 键与 BREADTH_COVERAGE_KEYS 不一致")
        _, errors = g._validate_finding_payload(tpl, 1, self.LOOP)
        self.assertEqual(errors, [], "print-schema 的模板自己过不了校验")

    def test_enum_errors_list_legal_values(self):
        """两个实测错法：报错必须给出合法取值，而不是只说'非法'。"""
        g = gate_module()
        tpl = self._template()
        tpl["findings"][0]["scope_relation"] = "in_scope"
        tpl["findings"][0]["origin"] = "upstream_contract"
        _, errors = g._validate_finding_payload(tpl, 1, self.LOOP)
        blob = " ; ".join(errors)
        self.assertIn("in-scope | out-of-scope | scope-change-proposal", blob,
                      "scope_relation 报错未列合法值——代理只能猜")
        self.assertIn("new-external-fact | patch-induced | pre-existing", blob,
                      "origin 报错未列合法值——代理只能猜")
        self.assertIn("'in_scope'", blob, "报错未回显出错的值")

    def test_missing_and_unknown_fields_list_the_roster(self):
        g = gate_module()
        tpl = self._template()
        tpl["findings"][0]["trusted_boundary_stop"] = True   # 实测：把 coverage 键写进 finding
        del tpl["findings"][0]["root_cause"]
        _, errors = g._validate_finding_payload(tpl, 1, self.LOOP)
        blob = " ; ".join(errors)
        self.assertIn("合法字段", blob, "未知字段报错未给合法字段清单")
        self.assertIn("必填", blob, "缺字段报错未给必填清单")

    def test_cluster_path_errors_also_carry_values(self):
        """specialist/synthesis 走的是另一个校验函数，同样不能只说'非法'。"""
        g = gate_module()
        tpl = self._template()
        item = dict(tpl["findings"][0])
        item["scope_relation"] = "in_scope"
        item["severity"] = "SEV1"
        blob = " ; ".join(g._validate_cluster_finding_items([item], self.LOOP))
        self.assertIn("in-scope | out-of-scope | scope-change-proposal", blob)
        self.assertIn("P0 | P1 | P2", blob)

    def test_id_error_explains_the_pattern(self):
        g = gate_module()
        tpl = self._template()
        tpl["findings"][0]["id"] = "Auth_Token_Leak"        # 实测错法：大写 + 下划线
        _, errors = g._validate_finding_payload(tpl, 1, self.LOOP)
        blob = " ; ".join(errors)
        self.assertIn("auth-token-leak", blob, "id 报错未给示例")
        self.assertIn("'Auth_Token_Leak'", blob, "id 报错未回显出错的值")

    def test_human_output_covers_every_enum(self):
        """人读版必须列全枚举——漏一个就等于把代理推回猜的状态。"""
        g = gate_module()
        proc = run_gate(["print-schema"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        for values in (g.FINDING_SEVERITIES, g.FINDING_SCOPE_RELATIONS,
                       g.FINDING_ORIGINS, g.FINDING_STATUSES,
                       g.CHALLENGE_REVIEW_MODES, g.BREADTH_COVERAGE_KEYS):
            for v in values:
                self.assertIn(v, out, "print-schema 漏了取值 %s" % v)
        for field in g.FINDING_ITEM_REQUIRED:
            self.assertIn(field, out, "print-schema 漏了必填字段 %s" % field)
