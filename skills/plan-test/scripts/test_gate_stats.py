#!/usr/bin/env python3
"""stats 子命令的测试（T4：规则退休的数据来源）。

运行：python skills/plan-test/scripts/test_gate_stats.py
账本全部经 canonical CLI 路径构造（init/record-run/…），不手写账本 JSON——
手写的四键 JSON 过不了 validate 的链校验，测出来的是解析失败路径而不是统计路径。
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


class LastActivityTimeSourceTestCase(unittest.TestCase):
    """W1-1：_stats_last_activity 必须读 integrity.log 的 at，而不是恒走 mtime 兜底。

    病根（第 5 轮审计实证）：函数读 integrity['chain']——那是一个 **str**（链值），
    时间戳在 integrity['log']（list of dict）。遍历字符串得单字符，isinstance dict
    恒 False → 永远落到 os.path.getmtime。mtime 被 clone/checkout 重置，
    换机与 CI 上时间轴系统性失真。"""

    def _gate(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("g_ts", GATE)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        return g

    def test_reads_integrity_log_not_mtime(self):
        g = self._gate()
        tmp = tempfile.mkdtemp(prefix="lastact-")
        try:
            rel = "verification/r1/plan-test-run.json"
            p = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(p))
            ledger = {"integrity": {
                "chain": "ab" * 32,          # str——真实账本就是这个形状
                "log": [{"at": "2026-08-27T11:49:15+0800", "chain": "x"},
                        {"at": "2026-08-27T11:53:10+0800", "chain": "y"}]}}
            with open(p, "w", encoding="utf-8") as f:
                json.dump(ledger, f)
            os.utime(p, (0, 0))              # mtime = 1970——若走 mtime 立刻穿帮
            got = g._stats_last_activity(tmp, rel, ledger)
            self.assertEqual(got, "2026-08-27T11:53:10+0800",
                             "必须取 integrity.log 的最大 at，而不是 1970 年的 mtime")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mtime_fallback_only_when_log_absent(self):
        g = self._gate()
        tmp = tempfile.mkdtemp(prefix="lastact-")
        try:
            rel = "verification/r1/plan-test-run.json"
            p = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(p))
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"integrity": {}}, f)
            got = g._stats_last_activity(tmp, rel, {"integrity": {}})
            self.assertTrue(got, "无 log 时仍应有 mtime 兜底，不返回空")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RefusalStatsTestCase(unittest.TestCase):
    """s1a AC-6：stats 的 refusal 计数段——按码、按命令、总数；坏行跳过；无文件出「（无）」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-stats-refusal-")
        subprocess.run(["git", "init", "-q", self.tmp], check=True,
                       capture_output=True)
        self._saved = os.environ["PLAN_TEST_REFUSAL_HOME"]
        self.home = tempfile.mkdtemp(prefix="refusal-stats-")
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self.home

    def tearDown(self):
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.home, ignore_errors=True)

    def _write_refusals(self, lines):
        with open(os.path.join(self.home, "refusals.jsonl"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def test_counts_by_code_and_cmd_with_bad_line(self):
        self._write_refusals([
            json.dumps({"at": "t1", "cwd": "/a", "cmd": "checkpoint",
                        "code": None, "run_dir": "/x", "detail": "d1"}),
            json.dumps({"at": "t2", "cwd": "/a", "cmd": "record-challenge-control",
                        "code": "CONTROL_NOT_REQUIRED", "run_dir": "/x", "detail": "d2"}),
            json.dumps({"at": "t3", "cwd": "/a", "cmd": "record-challenge-control",
                        "code": "CONTROL_NOT_REQUIRED", "run_dir": "/y", "detail": "d3"}),
            "{这不是 JSON",                       # 坏行：跳过，不崩溃
        ])
        r = run_gate(["stats", "--root", self.tmp])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("refusal 记录：3 条", r.stdout)
        self.assertIn("坏行跳过 1", r.stdout)
        self.assertIn("CONTROL_NOT_REQUIRED", r.stdout)
        self.assertIn("（无诊断码）", r.stdout)
        self.assertIn("record-challenge-control", r.stdout)
        # 按码排序：CONTROL_NOT_REQUIRED(2) 应排在（无诊断码）(1) 之前
        self.assertLess(r.stdout.index("CONTROL_NOT_REQUIRED"),
                        r.stdout.index("（无诊断码）"))

    def test_no_file_prints_none_and_no_crash(self):
        r = run_gate(["stats", "--root", self.tmp])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("refusal 记录：（无）", r.stdout)


class RefusalIntervalTestCase(unittest.TestCase):
    """W5-17（s1b）：「拒绝 → 下一个新 run」按码间隔分布——同目录配对 + 多对一去重。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-int-")
        subprocess.run(["git", "init", "-q", self.tmp], check=True,
                       capture_output=True)
        self._saved = os.environ["PLAN_TEST_REFUSAL_HOME"]
        self.home = tempfile.mkdtemp(prefix="refusal-int-")
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self.home

    def tearDown(self):
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.home, ignore_errors=True)

    def _ledger(self, rel_verification, run_name, created):
        rd = os.path.join(self.tmp, rel_verification, run_name)
        os.makedirs(rd, exist_ok=True)
        with open(os.path.join(rd, "plan-test-run.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"schema_version": "1.5.0", "run_id": run_name,
                       "created_at": created, "scenarios": [],
                       "integrity": {"chain": "x", "log": []}}, f)

    def _refuse(self, at, run_dir, code):
        with open(os.path.join(self.home, "refusals.jsonl"), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps({"at": at, "cwd": "/w", "cmd": "checkpoint",
                                "code": code, "run_dir": run_dir,
                                "detail": "d"}) + "\n")

    def test_same_dir_pairing_with_dedup(self):
        ver = "plans/p/verification"
        self._ledger(ver, "run-2", "2026-08-29T10:30:00+0800")
        # 两条 refusal 指向同目录 run-1：多对一去重应只留最近的（10:25）
        self._refuse("2026-08-29T10:00:00+0800",
                     os.path.join(self.tmp, ver, "run-1"), "CONTROL_NOT_REQUIRED")
        self._refuse("2026-08-29T10:25:00+0800",
                     os.path.join(self.tmp, ver, "run-1"), "CONTROL_NOT_REQUIRED")
        # 跨 slice 的 refusal：不同 verification 目录，不得配对
        self._refuse("2026-08-29T10:20:00+0800",
                     os.path.join(self.tmp, "plans/other/verification/run-9"),
                     "SCHEMA_INVALID")
        # run_dir 为空：只计数不配对
        self._refuse("2026-08-29T10:21:00+0800", None, "LEDGER_TAMPERED")
        r = run_gate(["stats", "--root", self.tmp])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("拒绝 → 下一个新 run", r.stdout)
        self.assertIn("CONTROL_NOT_REQUIRED", r.stdout)
        self.assertIn("n=1（样本<2 不出分布）", r.stdout,
                      "去重后应只剩 1 个样本（5 分钟那条），且样本<2 不出分布")
        self.assertNotRegex(r.stdout, r"SCHEMA_INVALID\s+n=",
                            "跨 verification 目录不得配对")

    def test_iso_gap_accepts_compact_and_colonized_offsets(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gate_iso_gap", GATE)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        self.assertEqual(
            gate._iso_gap_minutes(
                "2026-08-29T10:25:00+0800", "2026-08-29T10:30:00+0800"),
            5.0)
        self.assertEqual(
            gate._iso_gap_minutes(
                "2026-08-29T10:25:00+08:00", "2026-08-29T10:30:00+08:00"),
            5.0)


class ExportRefusalsTestCase(unittest.TestCase):
    """W5-18（s1c）：导出脱敏——POSIX / Windows 无空格 / Windows 含空格 三形态。"""

    def setUp(self):
        self._saved = os.environ["PLAN_TEST_REFUSAL_HOME"]
        self.home = tempfile.mkdtemp(prefix="refusal-exp-")
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self.home
        with open(os.path.join(self.home, "refusals.jsonl"), "w",
                  encoding="utf-8") as f:
            for detail in (
                    "LEDGER_LOCKED: /home/denny/proj/verification/r1/.gate.lock 被其他进程持有",
                    "run-dir 在仓库之外（C:\\proj\\verification\\run-1）",
                    "LEDGER_LOCKED: C:\\Users\\John Smith\\proj\\verification\\run-1\\.gate.lock 被其他进程持有"):
                f.write(json.dumps({"at": "t", "cwd": "/home/denny/proj",
                                    "cmd": "checkpoint", "code": None,
                                    "run_dir": "/home/denny/proj/verification/r1",
                                    "detail": detail}) + "\n")

    def tearDown(self):
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self._saved
        shutil.rmtree(self.home, ignore_errors=True)

    def test_export_redacts_all_three_path_forms(self):
        out = os.path.join(self.home, "export.jsonl")
        r = run_gate(["export-refusals", "--output", out])
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("/home/denny", text, "POSIX 路径未脱敏")
        self.assertNotIn("C:\\\\proj", text, "Windows 无空格路径未脱敏")
        self.assertNotIn("John", text,
                         "Windows 含空格路径按空白切分会残留姓氏——rev3 挑战抓出的缺口")
        self.assertNotIn("Smith", text)
        self.assertIn("<path>", text)
        self.assertIn("被其他进程持有", text, "非路径文本必须保留（不过度脱敏）")

    def test_output_is_mandatory(self):
        r = run_gate(["export-refusals"])
        self.assertEqual(r.returncode, 2, "--output 必填，不许写默认位置")


if __name__ == "__main__":
    unittest.main(verbosity=1)
