"""refusal trim 归档机制用例（v0.7.1 review 整改 F1–F7 的决定性测试）。

补课背景（2026-09-02）：v0.7.1/v0.7.2 重写了整个归档机制（155 行生产代码）却零新增
用例——同一个版本刚立下"每个 P0/P1 修复必配一条决定性测试并入回归套件"的规则。
本文件把当时的手工实测固化为可复跑断言，每个测试类对应一条 review finding：
丢弃→归档零丢失（原始整改）、utf-8 毒丸（F4）、归档失败不留残缺（F2）、
4 倍限额兜底（F5）、主文件重写失败回滚（F3）、读取层可达（F7）、停用状态可见（审计缺口 1）。
"""
import refusal_guard  # noqa: F401  测试隔离：必须最先 import（见该模块 docstring）

import gzip
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import plan_test_gate as gate
from test_plan_test_gate import run_gate


def _rec(i):
    return json.dumps({
        "at": "2026-09-01T00:00:00", "cwd": "/x", "cmd": "init",
        "code": "USAGE_ERROR", "run_dir": None, "detail": "d%04d" % i,
        "pad": "x" * 200}) + "\n"


def _make_oversized(path, n=3000):
    with open(path, "w", encoding="utf-8") as f:
        for i in range(n):
            f.write(_rec(i))
    assert os.path.getsize(path) > gate.REFUSAL_FILE_MAX_KB * 1024


def _archives(d):
    return sorted(a for a in os.listdir(d)
                  if a.startswith(gate.REFUSAL_ARCHIVE_PREFIX)
                  and a.endswith(gate.REFUSAL_ARCHIVE_SUFFIX))


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _leftover_tmp(d):
    """trim 的两类 mkstemp 临时文件都不许残留。"""
    return [a for a in os.listdir(d)
            if a.startswith(".refusal-archive-") or a.startswith(".refusals-")]


class TrimHarness(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="refusal-archive-test-")
        self.target = os.path.join(self.d, "refusals.jsonl")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)


class ArchiveInsteadOfDropTestCase(TrimHarness):
    def test_trim_archives_oldest_half_zero_loss(self):
        """超限 trim：最旧一半进 gz 归档、主文件留最新一半，总行数零丢失；
        归档名含 pid（并发唯一性契约，F1 的修法之一）。"""
        _make_oversized(self.target, 3000)
        gate._trim_refusals(self.target)
        archives = _archives(self.d)
        self.assertEqual(len(archives), 1)
        self.assertIn("-%d" % os.getpid(), archives[0])
        with gzip.open(os.path.join(self.d, archives[0]), "rt",
                       encoding="utf-8") as f:
            archived = f.read().splitlines()
        with open(self.target, encoding="utf-8") as f:
            kept = f.read().splitlines()
        self.assertEqual(len(archived), 1500)
        self.assertEqual(len(kept), 1500)
        # 顺序契约：归档是最旧一半，主文件是最新一半
        self.assertIn("d0000", archived[0])
        self.assertIn("d1500", kept[0])
        self.assertEqual(_leftover_tmp(self.d), [])

    def test_under_limit_untouched(self):
        with open(self.target, "w", encoding="utf-8") as f:
            f.write(_rec(0))
        before = _read_bytes(self.target)
        gate._trim_refusals(self.target)
        self.assertEqual(_read_bytes(self.target), before)
        self.assertEqual(_archives(self.d), [])


class PoisonByteTestCase(TrimHarness):
    def test_truncated_multibyte_does_not_disable_trim(self):
        """F4：文件尾部有截断的多字节序列时，trim 仍须成功（旧实现抛
        UnicodeDecodeError 后 refusal 记录永久静默失效）。"""
        _make_oversized(self.target, 3000)
        with open(self.target, "ab") as f:
            f.write("中文".encode("utf-8")[:4] + b"\n")
        gate._trim_refusals(self.target)  # 不许抛
        self.assertEqual(len(_archives(self.d)), 1)
        self.assertLess(os.path.getsize(self.target),
                        gate.REFUSAL_FILE_MAX_KB * 1024)

    def test_cli_still_records_refusal_on_poisoned_oversized_file(self):
        """端到端：毒丸 + 超限的账本上，一次 die() 仍会追加新记录（而非被
        trim 异常整体打断）。"""
        _make_oversized(self.target, 3000)
        with open(self.target, "ab") as f:
            f.write("中文".encode("utf-8")[:4] + b"\n")
        old = os.environ.get(gate.REFUSAL_HOME_ENV)
        os.environ[gate.REFUSAL_HOME_ENV] = self.d
        try:
            run_gate(["definitely-not-a-command"])
        finally:
            if old is None:
                os.environ.pop(gate.REFUSAL_HOME_ENV, None)
            else:
                os.environ[gate.REFUSAL_HOME_ENV] = old
        with open(self.target, encoding="utf-8", errors="replace") as f:
            tail = f.read().splitlines()[-1]
        self.assertIn("not-a-command", tail)


class ArchiveFailureTestCase(TrimHarness):
    def test_failure_skips_trim_and_leaves_no_partial_gz(self):
        """F2：归档写失败 → 跳过本次 trim，最终名与临时名都不残留半截文件，
        主文件原样保留（数据保全优先）。"""
        _make_oversized(self.target, 3000)
        before = _read_bytes(self.target)
        with mock.patch("gzip.GzipFile", side_effect=OSError("disk full")):
            gate._trim_refusals(self.target)
        self.assertEqual(_read_bytes(self.target), before)
        self.assertEqual(_archives(self.d), [])
        self.assertEqual(_leftover_tmp(self.d), [])

    def test_persistent_failure_over_4x_falls_back_to_drop(self):
        """F5：归档持续失败且超 4 倍限额 → 退回丢弃式裁剪，保住体积上限
        invariant（否则每次 die() 全量重读无界增长的文件）。"""
        _make_oversized(self.target, 12000)  # ~2.9MB > 4*512KB
        with mock.patch("gzip.GzipFile", side_effect=OSError("disk full")):
            gate._trim_refusals(self.target)
        self.assertEqual(_archives(self.d), [])
        with open(self.target, encoding="utf-8") as f:
            kept = f.read().splitlines()
        self.assertEqual(len(kept), 6000)
        self.assertEqual(_leftover_tmp(self.d), [])


class MainRewriteFailureTestCase(TrimHarness):
    def test_rewrite_failure_rolls_back_archive(self):
        """F3：归档成功后主文件重写失败 → 回滚删除刚写的归档，防止下次 trim
        把同一批最旧行再归档一份（虚增退休评审计数）。"""
        _make_oversized(self.target, 3000)
        before = _read_bytes(self.target)
        with mock.patch.object(gate, "_rewrite_refusals",
                               side_effect=OSError("replace failed")):
            gate._trim_refusals(self.target)  # 不许抛
        self.assertEqual(_archives(self.d), [])
        self.assertEqual(_read_bytes(self.target), before)


class ReadLayerTestCase(TrimHarness):
    def _write_archive(self, name, lines):
        with gzip.open(os.path.join(self.d, name), "wt", encoding="utf-8") as f:
            f.writelines(lines)

    def test_iter_yields_archives_then_main_and_skips_corrupt(self):
        """F7：读取层按 归档→主文件 顺序全量可达；残缺归档跳过不炸。"""
        self._write_archive("refusals-20260901T000000-1.jsonl.gz",
                            [_rec(0), _rec(1)])
        with open(os.path.join(self.d, "refusals-20260901T000001-1.jsonl.gz"),
                  "wb") as f:
            f.write(b"\x1f\x8b broken")
        with open(self.target, "w", encoding="utf-8") as f:
            f.write(_rec(2))
        got = list(gate._iter_refusal_lines(self.target))
        self.assertEqual(len(got), 3)
        self.assertIn("d0000", got[0])
        self.assertIn("d0002", got[-1])

    def test_export_includes_archived_records(self):
        """F7 端到端：export-refusals（跨机器分析的指定出口）导出 归档+主文件
        全量记录——退休评审不再把已归档的拦截数成零。"""
        self._write_archive("refusals-20260901T000000-1.jsonl.gz",
                            [_rec(i) for i in range(5)])
        with open(self.target, "w", encoding="utf-8") as f:
            for i in range(5, 8):
                f.write(_rec(i))
        out = os.path.join(self.d, "export.jsonl")
        old = os.environ.get(gate.REFUSAL_HOME_ENV)
        os.environ[gate.REFUSAL_HOME_ENV] = self.d
        try:
            r = run_gate(["export-refusals", "--output", out])
        finally:
            if old is None:
                os.environ.pop(gate.REFUSAL_HOME_ENV, None)
            else:
                os.environ[gate.REFUSAL_HOME_ENV] = old
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            self.assertEqual(len(f.read().splitlines()), 8)


class DisabledStateVisibilityTestCase(unittest.TestCase):
    def test_stats_says_disabled_instead_of_none(self):
        """审计缺口 1：无声开关关闭时 stats 必须报"已停用 + 出口"，
        不得报"（无）"让读者把停用误读成零历史。"""
        buf = io.StringIO()
        with mock.patch.object(gate, "_refusal_target", return_value=None):
            with redirect_stdout(buf):
                gate._stats_print_refusals()
        self.assertIn("已停用", buf.getvalue())
        self.assertIn(gate.REFUSAL_HOME_ENV, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
