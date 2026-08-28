import refusal_guard  # noqa: F401  测试隔离：把 refusal 写入引到 tmpdir（s1a AC-7，见该模块 docstring）
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest


MODULE_PATH = os.path.join(os.path.dirname(__file__), "gate_usage_report.py")
SPEC = importlib.util.spec_from_file_location("gate_usage_report", MODULE_PATH)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class GateUsageReportTestCase(unittest.TestCase):
    def test_parse_diagnostics_ignores_non_diagnostics(self):
        output = "\n".join([
            "DIAG REQUIRED_SCENARIO_NOT_RUN: missing",
            "ADVISORY EXECUTOR_ENGINE_UNDECLARED: unknown",
            "READY_FOR_AUDIT",
        ])
        self.assertEqual(REPORT.parse_diagnostics(output), [
            ("DIAG", "REQUIRED_SCENARIO_NOT_RUN"),
            ("ADVISORY", "EXECUTOR_ENGINE_UNDECLARED"),
        ])

    def test_find_ledgers_includes_tracked_and_ignored(self):
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "plans", "p", "verification", "tracked"))
            os.makedirs(os.path.join(repo, "plans", "p", "verification", "ignored"))
            os.makedirs(os.path.join(repo, "plans", "p", "verification", "ordinary"))
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            tracked = "plans/p/verification/tracked/plan-test-run.json"
            ignored = "plans/p/verification/ignored/plan-test-run.json"
            ordinary = "plans/p/verification/ordinary/plan-test-run.json"
            for path in (tracked, ignored, ordinary):
                with open(os.path.join(repo, path), "w", encoding="utf-8") as handle:
                    handle.write("{}")
            with open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8") as handle:
                handle.write("plans/p/verification/ignored/\n")
            subprocess.run(["git", "add", tracked], cwd=repo, check=True)
            self.assertEqual(REPORT.find_ledgers(repo), sorted([tracked, ignored, ordinary]))


class EncodingRobustnessTestCase(unittest.TestCase):
    """W1-2：报告在「解码环境 ≠ 子进程输出编码」时必须照常出报告，不许崩、更不许静默空。

    病根（Windows 实测）：subprocess text=True 未指定 encoding → 按 locale 解码
    （Windows=GBK）；gate 输出 UTF-8 中文 → 读线程 UnicodeDecodeError 崩掉，
    **报告输出三段空「（无）」而无任何错误**——规则退休的唯一数据源在 Windows 上
    永远失明，规则集因此只进不出。
    本用例在 Linux 上用 LC_ALL=C（ASCII 解码）+ PYTHONIOENCODING=utf-8
    （子 gate 照常 UTF-8 中文）复现同类崩溃。"""

    def test_report_survives_ascii_locale(self):
        with tempfile.TemporaryDirectory() as repo:
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            p = os.path.join(repo, "plans", "p", "verification", "r1")
            os.makedirs(p)
            with open(os.path.join(p, "plan-test-run.json"), "w",
                      encoding="utf-8") as f:
                f.write("{}")          # 坏账本：gate 会输出中文诊断
            env = dict(os.environ)
            env["LC_ALL"] = "C"
            env["LANG"] = "C"
            env["PYTHONIOENCODING"] = "utf-8"
            # 关掉 PEP 540/538 的自动救援——C locale 下 Python 会自动切 UTF-8 mode，
            # Linux 上复现不了 Windows GBK 的处境；显式关闭后 preferred encoding
            # 真正回到 ASCII，与 Windows 上「locale 编码 ≠ 子进程输出编码」同构
            env["PYTHONUTF8"] = "0"
            env["PYTHONCOERCECLOCALE"] = "0"
            r = subprocess.run(
                [sys.executable,
                 os.path.join(os.path.dirname(SPEC.origin), "gate_usage_report.py"),
                 "--repo-dir", repo],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, timeout=120)
            self.assertEqual(r.returncode, 0,
                             "ASCII locale 下报告不得崩溃：\n" + r.stderr[:800])
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("真实 run", r.stdout, "报告主体必须照常输出，不许静默变空")


if __name__ == "__main__":
    unittest.main()
