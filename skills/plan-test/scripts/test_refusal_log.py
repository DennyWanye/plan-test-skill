"""s1a refusal log 用例（acceptance：plans/2026-08-28-gate-authority/slices/s1a-refusal-log/）。

红测纪律（plan §3 步骤 2）：AC-2 反向与 AC-4 断链两条**先于实现提交**，并在无实现的
代码上确认真的失败——rev1 的 AC-2 正是缺这一步才让「按构造无法失败」的 oracle 混过去。
计数一律用前后差值：守卫 tmpdir 由整个套件共享，其他用例的 die 也会追加记录。
"""
import refusal_guard  # noqa: F401  测试隔离：必须最先 import（见该模块 docstring）

import json
import os
import subprocess
import tempfile
import shutil
import unittest

from test_plan_test_gate import GateHarness, run_gate


def _refusal_path():
    return os.path.join(os.environ["PLAN_TEST_REFUSAL_HOME"], "refusals.jsonl")


def _lines(path=None):
    p = path or _refusal_path()
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [l for l in f.read().splitlines() if l.strip()]


class RefusalRecordTestCase(unittest.TestCase):
    """AC-1：die 落一条原始记录。"""

    def test_die_without_code_writes_raw_record(self):
        """无诊断码前缀的 die（『run-dir 缺少 plan-test-run.json』）也要记，code=null。"""
        before = len(_lines())
        empty = tempfile.mkdtemp(prefix="refusal-t-")
        try:
            r = run_gate(["checkpoint", "--run-dir", empty, "--note", "x"])
            self.assertEqual(r.returncode, 2, "前提：该调用必须 die")
            lines = _lines()
            self.assertEqual(len(lines), before + 1,
                             "die 之后 refusals.jsonl 应恰好多一条")
            rec = json.loads(lines[-1])
            self.assertEqual(rec["cmd"], "checkpoint")
            self.assertIsNone(rec["code"])
            self.assertEqual(rec["run_dir"], empty, "run_dir 记用户所给原文，不加工")
            self.assertIn("plan-test-run.json", rec["detail"])
            self.assertTrue(rec.get("cwd"), "cwd 必有且为原文")
            self.assertTrue(rec.get("at"))
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class RefusalFingerprintReverseTestCase(unittest.TestCase):
    """AC-2 反向：oracle 必须能判红——显式把落点指进仓库内，指纹必须真的变。"""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="refusal-repo-")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self._saved = os.environ["PLAN_TEST_REFUSAL_HOME"]
        # 显式 override（非默认路径）——按 AC-2，此时守卫不设防，责任归操作者
        os.environ["PLAN_TEST_REFUSAL_HOME"] = os.path.join(self.repo, "inside")

    def tearDown(self):
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self._saved
        shutil.rmtree(self.repo, ignore_errors=True)

    def _ls_files(self):
        r = subprocess.run(["git", "ls-files", "-c", "-o", "--exclude-standard"],
                           cwd=self.repo, capture_output=True, text=True, check=True)
        return [l for l in r.stdout.splitlines() if l.strip()]

    def test_in_repo_landing_does_perturb_fingerprint(self):
        before = self._ls_files()
        empty = tempfile.mkdtemp(prefix="refusal-t-")
        try:
            r = run_gate(["checkpoint", "--run-dir", empty, "--note", "x"])
            self.assertEqual(r.returncode, 2)
            after = self._ls_files()
            self.assertGreater(
                len(after), len(before),
                "落点在仓库内时 ls-files 必须增加——增加不了说明度量口径失效，"
                "AC-2 的正向断言从此测不出任何东西")
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class RefusalNoRecursionTestCase(GateHarness):
    """AC-4：LEDGER_TAMPERED（_append 写前验链自 die）场景不得递归。"""

    def test_chain_break_records_once_and_exits_cleanly(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        ledger_path = os.path.join(self.run_dir, "plan-test-run.json")
        with open(ledger_path, encoding="utf-8") as f:
            ledger = json.load(f)
        ledger["run_id"] = "tampered-by-hand"          # 绕过 CLI 手改 → 链必断
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False)

        before = len(_lines())
        r = run_gate(["checkpoint", "--run-dir", self.run_dir, "--note", "x"])
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(r.stderr.count("LEDGER_TAMPERED"), 1,
                         "stderr 只许出现一次 LEDGER_TAMPERED（递归会打多次）")
        self.assertNotIn("RecursionError", r.stderr)
        lines = _lines()
        self.assertEqual(len(lines), before + 1, "断链场景恰记一条")
        rec = json.loads(lines[-1])
        self.assertEqual(rec["code"], "LEDGER_TAMPERED")


class RefusalCodedNoRunDirTestCase(unittest.TestCase):
    """AC-1 第三形态：有 code、无 --run-dir（compile-manifest 这类前置命令）。
    它正是 rev1 结构上记不到的那 15%——本 slice 的上下文不绑 run_dir，记得到。"""

    def test_compile_manifest_failure_recorded_without_run_dir(self):
        before = len(_lines())
        spec = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        spec.write('{"foo": 1}')          # 合法 JSON、非法 spec → SCHEMA_INVALID
        spec.close()
        try:
            r = run_gate(["compile-manifest", "--spec", spec.name,
                          "--output", spec.name + ".out"])
            self.assertEqual(r.returncode, 2)
            lines = _lines()
            self.assertEqual(len(lines), before + 1)
            rec = json.loads(lines[-1])
            self.assertEqual(rec["cmd"], "compile-manifest")
            self.assertEqual(rec["code"], "SCHEMA_INVALID")
            self.assertIsNone(rec["run_dir"])
        finally:
            os.unlink(spec.name)


class RefusalFailureSafetyTestCase(unittest.TestCase):
    """AC-3：写入失败（refusals.jsonl 被建成目录）不得改变原 stderr 与退出码。
    注入手段跨平台：open(dir, 'a') 在 POSIX/Windows 均抛异常；不用 chmod
    （Windows 与 root 下无效，会在未注入任何失败时静默判绿——rev2 挑战 P2）。"""

    def setUp(self):
        self._saved = os.environ["PLAN_TEST_REFUSAL_HOME"]
        self.home = tempfile.mkdtemp(prefix="refusal-ro-")
        os.makedirs(os.path.join(self.home, "refusals.jsonl"))   # 占位为目录
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self.home

    def tearDown(self):
        os.environ["PLAN_TEST_REFUSAL_HOME"] = self._saved
        shutil.rmtree(self.home, ignore_errors=True)

    def test_write_failure_leaves_stderr_and_exit_code_intact(self):
        empty = tempfile.mkdtemp(prefix="refusal-t-")
        try:
            r = run_gate(["checkpoint", "--run-dir", empty, "--note", "x"])
            self.assertEqual(r.returncode, 2, "退出码不得因写入失败而变")
            self.assertEqual(
                r.stderr.strip(),
                "ERROR: run-dir 缺少 plan-test-run.json，先执行 init",
                "stderr 必须与无 refusal 机制时逐字节一致")
            self.assertTrue(os.path.isdir(
                os.path.join(self.home, "refusals.jsonl")), "占位目录原样保留")
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class BareTracebackEntriesTestCase(unittest.TestCase):
    """坏输入必须走 die（rc=2、单行 ERROR、留 refusal），不许崩裸 traceback（rc=1）。

    冒烟实测（2026-08-28）：不存在的 run-dir 在 LedgerLock 崩 FileNotFoundError；
    init 的 --manifest 指向不存在文件同样裸崩。这类失败连 refusal 都记不到——
    因为它根本没走 die()。PROTOCOL §6c 覆盖面第 4 类的修复。"""

    def test_nonexistent_run_dir_dies_cleanly(self):
        before = len(_lines())
        r = run_gate(["checkpoint", "--run-dir", "/tmp/refusal-no-such-dir-x",
                      "--note", "x"])
        self.assertEqual(r.returncode, 2, "坏输入应 die(rc=2) 而非崩溃(rc=1)")
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(r.stderr.startswith("ERROR: "), r.stderr[:120])
        lines = _lines()
        self.assertEqual(len(lines), before + 1, "die 路径必须留 refusal")
        self.assertIn("run-dir", json.loads(lines[-1])["detail"])

    def test_init_with_missing_manifest_dies_cleanly(self):
        before = len(_lines())
        rd = tempfile.mkdtemp(prefix="refusal-init-")
        try:
            r = run_gate(["init", "--run-dir", rd,
                          "--manifest", "/tmp/refusal-no-such-manifest.json"])
            self.assertEqual(r.returncode, 2)
            self.assertNotIn("Traceback", r.stderr)
            self.assertTrue(r.stderr.startswith("ERROR: "), r.stderr[:120])
            self.assertEqual(len(_lines()), before + 1)
        finally:
            shutil.rmtree(rd, ignore_errors=True)


class StatusCommandTestCase(GateHarness):
    """W4-16：status——只读、回答「我在哪、能做什么」；敲错命令给近似建议。"""

    def test_status_reports_state_and_next_steps(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        before = os.path.getmtime(os.path.join(self.run_dir, "plan-test-run.json"))
        r = run_gate(["status", "--run-dir", self.run_dir])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("STATE:", r.stdout)
        self.assertIn("REQUIRED_SCENARIO_NOT_RUN", r.stdout)
        self.assertIn("下一步总则", r.stdout)
        after = os.path.getmtime(os.path.join(self.run_dir, "plan-test-run.json"))
        self.assertEqual(before, after, "status 必须只读，不得触碰账本")

    def test_typo_gets_suggestion(self):
        r = run_gate(["staus", "--run-dir", "/tmp/x"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("status", r.stderr, "敲错命令应给出近似建议")
        self.assertIn("是不是想敲", r.stderr)


class ChainLengthCoversAllFactArraysTestCase(unittest.TestCase):
    """W1-4：phase_transitions / plan_defects（含 history 归档）必须计入链长下界。

    此前不计入 → 手删一条不会被长度检查发现（链值检查仍覆盖，保护弱一档）。"""

    def test_counts_include_previous_blind_spots(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "g_cl", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "plan_test_gate.py"))
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        base = {"runs": [], "evidence": []}
        n0 = g.expected_chain_length(dict(base))
        n1 = g.expected_chain_length(dict(base, phase_transitions=[{}, {}]))
        n2 = g.expected_chain_length(dict(base, plan_defects=[{}]))
        n3 = g.expected_chain_length(dict(
            base, plan_defects_history=[{"defects": [{}, {}, {}]}]))
        self.assertEqual(n1 - n0, 2, "phase_transitions 未计入下界")
        self.assertEqual(n2 - n0, 1, "plan_defects 未计入下界")
        self.assertEqual(n3 - n0, 3, "归档进 history 的 defects 未计入下界")


if __name__ == "__main__":
    unittest.main()
