#!/usr/bin/env python3
import importlib.util
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("testcase_inventory.py")
SPEC = importlib.util.spec_from_file_location("testcase_inventory", MODULE_PATH)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def markdown(testcase_id, **overrides):
    values = {
        "purpose": "prove memory recall",
        "status": "active",
        "surface": "api",
        "type": "scripted",
        "obligations": ["TO-MEM-03"],
        "tags": ["memory", "restart"],
        "entrypoint": "runtime gateway",
        "revision": 1,
    }
    values.update(overrides)
    lines = ["---", "id: %s" % testcase_id]
    for key, value in values.items():
        if isinstance(value, list):
            lines.append("%s:" % key)
            lines.extend("  - %s" % item for item in value)
        elif value is not None:
            lines.append("%s: %s" % (key, value))
    return "\n".join(lines + ["---", "", "# Steps", ""])


class TestFrontmatterAndBuild(unittest.TestCase):
    def test_parser_supports_required_scalar_and_list_subset(self):
        result = inventory.parse_frontmatter(markdown("TC-1"), "case.md")
        self.assertEqual("TC-1", result["id"])
        self.assertEqual(["TO-MEM-03"], result["obligations"])
        self.assertEqual(1, result["revision"])

    def test_parser_rejects_nested_yaml(self):
        text = "---\nid: TC-1\ncomplex:\n  child: value\n---\n"
        with self.assertRaisesRegex(inventory.InventoryError, "only top-level scalar lists"):
            inventory.parse_frontmatter(text, "case.md")

    def test_scan_builds_deterministic_indexes_and_skips_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "z.md").write_text(markdown("TC-Z"), encoding="utf-8")
            (root / "a.md").write_text(markdown("TC-A", tags=["memory"]), encoding="utf-8")
            (root / "legacy.md").write_text("# old testcase without frontmatter\n", encoding="utf-8")
            (root / "results").mkdir()
            (root / "results" / "run.md").write_text(markdown("TC-RESULT"), encoding="utf-8")

            data = inventory.scan_testcases(root)
            self.assertEqual(3, len(data["testcases"]))
            legacy = next(item for item in data["testcases"] if item["path"] == "legacy.md")
            self.assertEqual("needs-review", legacy["status"])
            self.assertTrue(legacy["generated_legacy_metadata"])
            self.assertEqual(["TC-A", "TC-Z"], sorted(
                item["id"] for item in data["testcases"] if item["status"] == "active"))
            json_path, md_path = inventory.write_indexes(data, root)
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data, loaded)
            rendered = md_path.read_text(encoding="utf-8")
            self.assertIn("| TC-A | a.md |", rendered)
            self.assertIn("| LEGACY-", rendered)
            self.assertIn("Do not record PASS/FAIL here", rendered)

    def test_scan_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.md").write_text(markdown("TC-DUP"), encoding="utf-8")
            (root / "two.md").write_text(markdown("TC-DUP"), encoding="utf-8")
            with self.assertRaisesRegex(inventory.InventoryError, "DUPLICATE_ID"):
                inventory.scan_testcases(root)


class TestInventoryValidation(unittest.TestCase):
    def entry(self, testcase_id, path, status="active", replacement=None,
              obligations=None, revision=1):
        return {
            "id": testcase_id, "path": path, "purpose": "p", "status": status,
            "surface": "api", "type": "scripted", "obligations": obligations or ["TO-1"],
            "tags": [], "preconditions": [], "results": [], "revision": revision,
            "replacement": replacement,
        }

    def test_missing_path_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"testcases": [self.entry("TC-1", "missing.md")]}
            errors = inventory.validate_inventory(data, tmp)
            self.assertIn("MISSING_PATH: TC-1: missing.md", errors)

    def test_path_escape_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"testcases": [self.entry("TC-1", "../outside.md")]}
            errors = inventory.validate_inventory(data, tmp)
            self.assertIn("PATH_ESCAPE: TC-1: ../outside.md", errors)

    def test_replacement_cycle_is_reported_once(self):
        data = {"testcases": [
            self.entry("TC-A", "a.md", "superseded", "TC-B"),
            self.entry("TC-B", "b.md", "superseded", "TC-A"),
        ]}
        errors = inventory.validate_inventory(data)
        self.assertEqual(["REPLACEMENT_CYCLE: TC-A -> TC-B -> TC-A"], errors)

    def test_missing_replacement_target_and_retired_without_replacement(self):
        data = {"testcases": [
            self.entry("TC-A", "a.md", "retired"),
            self.entry("TC-B", "b.md", "superseded", "TC-NOPE"),
        ]}
        errors = inventory.validate_inventory(data)
        self.assertIn("MISSING_REPLACEMENT: TC-A has status retired", errors)
        self.assertIn("MISSING_REPLACEMENT: TC-B -> TC-NOPE", errors)

    def test_query_matches_obligation_surface_tags_and_entrypoint(self):
        data = {"testcases": [
            self.entry("TC-A", "a.md"),
            self.entry("TC-B", "b.md", "needs-review"),
        ]}
        data["testcases"][0].update(tags=["memory", "restart"], entrypoint="Runtime Gateway")
        matches = inventory.query_inventory(
            data, obligations=["TO-1"], surface="api", tags=["memory"],
            entrypoint="gateway")
        self.assertEqual(["TC-A"], [item["id"] for item in matches])


class TestReuseReport(unittest.TestCase):
    def setUp(self):
        self.data = {"testcases": [
            self.entry("TC-ASIS", "TO-A", revision=1),
            self.entry("TC-EXT", "TO-B", revision=2),
            self.entry("TC-OLD", "TO-C", status="superseded", replacement="TC-NEW"),
            self.entry("TC-NEW", "TO-C"),
            self.entry("TC-CREATE", "TO-D"),
            self.entry("TC-RETIRED", "TO-E", status="retired", replacement="TC-ASIS"),
        ]}

    @staticmethod
    def entry(testcase_id, obligation, status="active", replacement=None, revision=1):
        return {
            "id": testcase_id, "path": testcase_id + ".md", "purpose": "p",
            "status": status, "surface": "api", "type": "scripted",
            "obligations": [obligation], "tags": [], "preconditions": [], "results": [],
            "revision": revision, "replacement": replacement,
        }

    def test_all_four_decisions_are_valid(self):
        report = {"decisions": [
            {"obligation_id": "TO-A", "decision": "reuse-as-is",
             "candidates": ["TC-ASIS"], "selected_testcases": ["TC-ASIS@rev1"]},
            {"obligation_id": "TO-B", "decision": "reuse-with-extension",
             "candidates": ["TC-EXT"], "selected_testcases": ["TC-EXT@rev2"],
             "reason": "add a fault assertion"},
            {"obligation_id": "TO-C", "decision": "supersede",
             "candidates": ["TC-OLD"], "selected_testcases": ["TC-NEW"],
             "reason": "old entrypoint removed"},
            {"obligation_id": "TO-D", "decision": "create-new",
             "candidates": [], "selected_testcases": ["TC-CREATE"],
             "reason": "no existing testcase covers the new obligation"},
        ]}
        errors = inventory.validate_reuse_report(
            self.data, report, required_obligations=["TO-A", "TO-B", "TO-C", "TO-D"],
            locked_testcases=["TC-ASIS", "TC-EXT", "TC-NEW", "TC-CREATE"])
        self.assertEqual([], errors)

    def test_retired_selection_and_historical_pass_are_rejected(self):
        report = {"obligation_id": "TO-E", "decision": "reuse-as-is",
                  "candidates": ["TC-RETIRED"], "selected_testcases": ["TC-RETIRED"],
                  "historical_pass_inherited": True}
        errors = inventory.validate_reuse_report(self.data, report)
        self.assertIn("UNSELECTABLE_TESTCASE: TC-RETIRED has status retired", errors)
        self.assertTrue(any(error.startswith("HISTORICAL_PASS_INHERITED") for error in errors))

    def test_create_new_requires_reason_and_known_selected_testcase(self):
        report = {"obligation_id": "TO-X", "decision": "create-new",
                  "candidates": [], "selected_testcases": ["TC-MISSING"]}
        errors = inventory.validate_reuse_report(self.data, report)
        self.assertIn("UNKNOWN_TESTCASE: decisions[0]: TC-MISSING", errors)
        self.assertIn("INCOMPLETE_CREATE_NEW: decisions[0] requires selected testcase and reason", errors)

    def test_required_obligation_and_lock_are_checked(self):
        report = {"obligation_id": "TO-A", "decision": "reuse-as-is",
                  "candidates": ["TC-ASIS"], "selected_testcases": ["TC-ASIS"]}
        errors = inventory.validate_reuse_report(
            self.data, report, required_obligations=["TO-A", "TO-B"],
            locked_testcases=["TC-EXT"])
        self.assertIn("MISSING_REUSE_DECISION: TO-B", errors)
        self.assertTrue(any(error.startswith("TESTCASE_LOCK_MISMATCH") for error in errors))

    def test_selected_revision_must_match_inventory(self):
        report = {"obligation_id": "TO-B", "decision": "reuse-as-is",
                  "candidates": ["TC-EXT"], "selected_testcases": ["TC-EXT@rev1"]}
        errors = inventory.validate_reuse_report(self.data, report)
        self.assertIn(
            "TESTCASE_REVISION_MISMATCH: TC-EXT requested rev1, inventory has rev2", errors)


class TestCli(unittest.TestCase):
    def test_build_query_validate_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "case.md").write_text(markdown("TC-CLI"), encoding="utf-8")
            build = subprocess.run(
                [sys.executable, str(MODULE_PATH), "build", "--testcase-dir", str(root)],
                text=True, capture_output=True)
            self.assertEqual(0, build.returncode, build.stderr)

            validate = subprocess.run(
                [sys.executable, str(MODULE_PATH), "validate", "--testcase-dir", str(root)],
                text=True, capture_output=True)
            self.assertEqual(0, validate.returncode, validate.stderr)
            self.assertIn("OK: 1 testcase(s)", validate.stdout)

            query = subprocess.run(
                [sys.executable, str(MODULE_PATH), "query", "--index", str(root / "index.json"),
                 "--tag", "memory", "--obligation", "TO-MEM-03"],
                text=True, capture_output=True)
            self.assertEqual(0, query.returncode, query.stderr)
            self.assertEqual("TC-CLI", json.loads(query.stdout)[0]["id"])

    def test_validate_detects_unindexed_source_and_markdown_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.md").write_text(markdown("TC-ONE"), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, inventory.main(["build", "--testcase-dir", str(root)]))
            (root / "two.md").write_text(markdown("TC-TWO"), encoding="utf-8")
            (root / "index.md").write_text("stale\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "validate", "--testcase-dir", str(root)],
                text=True, capture_output=True)
            self.assertEqual(1, result.returncode)
            self.assertIn("UNINDEXED_TESTCASE: two.md", result.stderr)
            self.assertIn("MARKDOWN_INDEX_DRIFT", result.stderr)


if __name__ == "__main__":
    unittest.main()
