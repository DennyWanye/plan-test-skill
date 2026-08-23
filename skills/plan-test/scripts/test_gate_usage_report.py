import importlib.util
import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
