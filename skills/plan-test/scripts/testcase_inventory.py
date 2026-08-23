#!/usr/bin/env python3
"""Build and validate a reusable testcase inventory from Markdown frontmatter.

The module is intentionally stdlib-only.  It implements the small YAML subset
used by plan-test testcase metadata: top-level scalar keys and scalar lists.
Complex YAML is rejected instead of being interpreted differently across
environments.

Exit codes: 0 success, 1 invalid inventory/reuse report, 2 CLI/input error.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "1.0"
STATUSES = {"active", "needs-review", "retired", "superseded"}
DECISIONS = {"reuse-as-is", "reuse-with-extension", "supersede", "create-new"}
LIST_FIELDS = {"obligations", "tags", "preconditions", "results"}
REQUIRED_FIELDS = {"id", "purpose", "status", "surface", "type"}
SELECTABLE_STATUSES = {"active"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class InventoryError(ValueError):
    """Input is structurally invalid or violates testcase lifecycle rules."""


def _scalar(text, source, line_number):
    value = text.strip()
    if not value:
        return ""
    if value[0:1] in {"'", '"'}:
        if len(value) < 2 or value[-1] != value[0]:
            raise InventoryError("%s:%d: unterminated quoted scalar" % (source, line_number))
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if value.startswith("["):
        if not value.endswith("]"):
            raise InventoryError("%s:%d: unterminated inline list" % (source, line_number))
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_scalar(item, source, line_number) for item in inner.split(",")]
    return value


def parse_frontmatter(text, source="<memory>"):
    """Parse top-level scalar/list YAML frontmatter; return None if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise InventoryError("%s: frontmatter is missing closing ---" % source)

    result = {}
    list_key = None
    for offset, raw in enumerate(lines[1:end], start=2):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw[:1].isspace():
            if not stripped.startswith("-") or list_key is None:
                raise InventoryError(
                    "%s:%d: only top-level scalar lists are supported" % (source, offset)
                )
            result[list_key].append(_scalar(stripped[1:], source, offset))
            continue
        if ":" not in raw:
            raise InventoryError("%s:%d: expected key: value" % (source, offset))
        key, value = raw.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            raise InventoryError("%s:%d: invalid key %r" % (source, offset, key))
        if key in result:
            raise InventoryError("%s:%d: duplicate key %s" % (source, offset, key))
        if not value.strip():
            result[key] = []
            list_key = key
        else:
            result[key] = _scalar(value, source, offset)
            list_key = None
    return result


def _normalise_entry(metadata, relative_path):
    missing = sorted(field for field in REQUIRED_FIELDS if not metadata.get(field))
    if missing:
        raise InventoryError("%s: missing required fields: %s" % (
            relative_path, ", ".join(missing)))
    testcase_id = str(metadata["id"])
    if not ID_RE.fullmatch(testcase_id):
        raise InventoryError("%s: invalid testcase id %r" % (relative_path, testcase_id))
    status = str(metadata["status"])
    if status not in STATUSES:
        raise InventoryError("%s: invalid status %r" % (relative_path, status))

    entry = dict(metadata)
    entry["id"] = testcase_id
    entry["path"] = relative_path
    entry["status"] = status
    for field in LIST_FIELDS:
        value = entry.get(field, [])
        if value is None:
            value = []
        elif not isinstance(value, list):
            value = [value]
        entry[field] = [str(item) for item in value if item not in (None, "")]
    revision = entry.get("revision", 1)
    if not isinstance(revision, int) or revision < 1:
        raise InventoryError("%s: revision must be a positive integer" % relative_path)
    entry["revision"] = revision
    replacement = entry.get("replacement")
    entry["replacement"] = str(replacement) if replacement not in (None, "") else None
    return entry


def scan_testcases(testcase_dir):
    """Return a deterministic inventory by scanning Markdown frontmatter."""
    root = Path(testcase_dir).resolve()
    if not root.is_dir():
        raise InventoryError("testcase directory does not exist: %s" % root)
    entries = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        if path.name.lower() in {"index.md", "readme.md"} or "results" in relative.parts:
            continue
        metadata = parse_frontmatter(path.read_text(encoding="utf-8"), str(path))
        if metadata is None:
            relative_path = relative.as_posix()
            legacy_id = "LEGACY-" + hashlib.sha256(
                relative_path.encode("utf-8")).hexdigest()[:12].upper()
            entries.append({
                "id": legacy_id,
                "path": relative_path,
                "purpose": "Review legacy testcase metadata: %s" % relative_path,
                "status": "needs-review",
                "surface": "unknown",
                "type": "hybrid",
                "obligations": [],
                "tags": ["legacy", "needs-metadata"],
                "preconditions": [],
                "results": [],
                "entrypoint": "",
                "revision": 1,
                "replacement": None,
                "generated_legacy_metadata": True,
            })
        else:
            entries.append(_normalise_entry(metadata, relative.as_posix()))
    inventory = {"schema_version": SCHEMA_VERSION, "testcases": entries}
    errors = validate_inventory(inventory, root)
    if errors:
        raise InventoryError("\n".join(errors))
    return inventory


def load_inventory(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("testcases"), list):
        raise InventoryError("inventory must contain a testcases list")
    return data


def validate_inventory(inventory, testcase_dir=None):
    """Return stable, human-readable validation errors."""
    errors = []
    entries = inventory.get("testcases", []) if isinstance(inventory, dict) else []
    seen = {}
    seen_paths = {}
    by_id = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append("INVALID_ENTRY: testcases[%d] must be an object" % position)
            continue
        testcase_id = entry.get("id")
        if not testcase_id:
            errors.append("MISSING_ID: testcases[%d]" % position)
            continue
        if testcase_id in seen:
            errors.append("DUPLICATE_ID: %s (%s, %s)" % (
                testcase_id, seen[testcase_id], entry.get("path", "<missing>")))
        else:
            seen[testcase_id] = entry.get("path", "<missing>")
            by_id[testcase_id] = entry
        missing = sorted(field for field in REQUIRED_FIELDS if not entry.get(field))
        if missing:
            errors.append("MISSING_FIELDS: %s: %s" % (testcase_id, ", ".join(missing)))
        if entry.get("status") not in STATUSES:
            errors.append("INVALID_STATUS: %s: %r" % (testcase_id, entry.get("status")))
        revision = entry.get("revision", 1)
        if not isinstance(revision, int) or revision < 1:
            errors.append("INVALID_REVISION: %s: %r" % (testcase_id, revision))
        path = entry.get("path")
        if not path:
            errors.append("MISSING_PATH: %s" % testcase_id)
        else:
            if path in seen_paths and seen_paths[path] != testcase_id:
                errors.append("DUPLICATE_PATH: %s (%s, %s)" % (
                    path, seen_paths[path], testcase_id))
            else:
                seen_paths[path] = testcase_id
        if path and testcase_dir is not None:
            root = Path(testcase_dir).resolve()
            candidate = (root / path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append("PATH_ESCAPE: %s: %s" % (testcase_id, path))
            else:
                if not candidate.is_file():
                    errors.append("MISSING_PATH: %s: %s" % (testcase_id, path))

    for testcase_id, entry in by_id.items():
        replacement = entry.get("replacement")
        if replacement and replacement not in by_id:
            errors.append("MISSING_REPLACEMENT: %s -> %s" % (testcase_id, replacement))
        if entry.get("status") in {"retired", "superseded"} and not replacement:
            errors.append("MISSING_REPLACEMENT: %s has status %s" % (
                testcase_id, entry.get("status")))

    visiting = set()
    visited = set()

    def visit(testcase_id, trail):
        if testcase_id in visiting:
            start = trail.index(testcase_id)
            errors.append("REPLACEMENT_CYCLE: %s" % " -> ".join(trail[start:]))
            return
        if testcase_id in visited:
            return
        visiting.add(testcase_id)
        replacement = by_id.get(testcase_id, {}).get("replacement")
        if replacement in by_id:
            visit(replacement, trail + [replacement])
        visiting.remove(testcase_id)
        visited.add(testcase_id)

    for testcase_id in sorted(by_id):
        visit(testcase_id, [testcase_id])
    return sorted(set(errors))


def _display(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def render_markdown(inventory):
    columns = [
        ("ID", "id"), ("Path", "path"), ("Purpose", "purpose"),
        ("AC/Obligation", "obligations"), ("Surface", "surface"),
        ("Type", "type"), ("Preconditions", "preconditions"),
        ("Entry point", "entrypoint"), ("Reusable tags", "tags"),
        ("Last validated", "last_validated_run"), ("Status", "status"),
        ("Results", "results"), ("Replacement", "replacement"),
    ]

    def cell(value):
        return _display(value).replace("|", "\\|").replace("\n", " ") or "—"

    lines = [
        "# Testcase Index", "",
        "> Generated from testcase Markdown frontmatter. Do not record PASS/FAIL here.", "",
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for entry in sorted(inventory.get("testcases", []), key=lambda item: item["id"]):
        lines.append("| " + " | ".join(cell(entry.get(key)) for _, key in columns) + " |")
    return "\n".join(lines) + "\n"


def write_indexes(inventory, testcase_dir, json_name="index.json", markdown_name="index.md"):
    root = Path(testcase_dir)
    json_path = root / json_name
    markdown_path = root / markdown_name
    json_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(inventory), encoding="utf-8")
    return json_path, markdown_path


def validate_generated_views(inventory, testcase_dir, markdown_name="index.md"):
    """Check that generated views still match every frontmatter source."""
    root = Path(testcase_dir)
    errors = []
    try:
        scanned = scan_testcases(root)
    except InventoryError as exc:
        return ["INVALID_TESTCASE_SOURCE: %s" % exc]
    indexed_by_path = {entry.get("path"): entry for entry in inventory.get("testcases", [])}
    scanned_by_path = {entry.get("path"): entry for entry in scanned.get("testcases", [])}
    for path in sorted(set(scanned_by_path) - set(indexed_by_path)):
        errors.append("UNINDEXED_TESTCASE: %s" % path)
    for path in sorted(set(indexed_by_path) & set(scanned_by_path)):
        if indexed_by_path[path] != scanned_by_path[path]:
            errors.append("INDEX_METADATA_DRIFT: %s" % path)
    markdown_path = root / markdown_name
    if not markdown_path.is_file():
        errors.append("MISSING_MARKDOWN_INDEX: %s" % markdown_path)
    elif markdown_path.read_text(encoding="utf-8") != render_markdown(inventory):
        errors.append("MARKDOWN_INDEX_DRIFT: %s" % markdown_path)
    return errors


def query_inventory(inventory, obligations=None, surface=None, tags=None,
                    entrypoint=None, statuses=None):
    obligations = set(obligations or [])
    tags = set(tags or [])
    statuses = set(statuses or ["active"])
    matches = []
    for entry in inventory.get("testcases", []):
        if entry.get("status") not in statuses:
            continue
        if surface and entry.get("surface") != surface:
            continue
        if obligations and not obligations.intersection(entry.get("obligations", [])):
            continue
        if tags and not tags.issubset(set(entry.get("tags", []))):
            continue
        if entrypoint and entrypoint.casefold() not in str(entry.get("entrypoint", "")).casefold():
            continue
        matches.append(entry)
    return sorted(matches, key=lambda entry: entry["id"])


def _selected_id(reference):
    return str(reference).split("@rev", 1)[0]


def _selected_revision(reference):
    text = str(reference)
    if "@rev" not in text:
        return None
    suffix = text.rsplit("@rev", 1)[1]
    return int(suffix) if suffix.isdigit() else -1


def validate_reuse_report(inventory, report, required_obligations=None,
                          locked_testcases=None):
    """Validate lifecycle decisions and return errors without mutating inventory."""
    errors = []
    decisions = report.get("decisions") if isinstance(report, dict) else None
    if decisions is None and isinstance(report, dict) and report.get("decision"):
        decisions = [report]
    if not isinstance(decisions, list):
        return ["INVALID_REUSE_REPORT: decisions must be a list"]

    by_id = {entry.get("id"): entry for entry in inventory.get("testcases", [])}
    covered = set()
    selected_all = set()
    for position, item in enumerate(decisions):
        prefix = "decisions[%d]" % position
        if not isinstance(item, dict):
            errors.append("INVALID_REUSE_DECISION: %s must be an object" % prefix)
            continue
        obligation = item.get("obligation_id")
        decision = item.get("decision")
        reason = str(item.get("reason") or "").strip()
        candidates = item.get("candidates", [])
        selected = item.get("selected_testcases", [])
        if not obligation:
            errors.append("MISSING_OBLIGATION: %s" % prefix)
        else:
            if obligation in covered:
                errors.append("DUPLICATE_REUSE_DECISION: %s" % obligation)
            covered.add(obligation)
        if decision not in DECISIONS:
            errors.append("INVALID_REUSE_DECISION: %s: %r" % (prefix, decision))
            continue
        if not isinstance(candidates, list) or not isinstance(selected, list):
            errors.append("INVALID_REUSE_DECISION: %s candidates/selected_testcases must be lists" % prefix)
            continue
        candidate_ids = {_selected_id(value) for value in candidates}
        selected_ids = {_selected_id(value) for value in selected}
        selected_all.update(selected_ids)
        for testcase_id in candidate_ids | selected_ids:
            if testcase_id not in by_id:
                errors.append("UNKNOWN_TESTCASE: %s: %s" % (prefix, testcase_id))
        for testcase_id in selected_ids:
            status = by_id.get(testcase_id, {}).get("status")
            if status not in SELECTABLE_STATUSES:
                errors.append("UNSELECTABLE_TESTCASE: %s has status %s" % (testcase_id, status))
            if obligation and testcase_id in by_id:
                bound = set(by_id[testcase_id].get("obligations", []))
                if obligation not in bound:
                    errors.append("OBLIGATION_NOT_BOUND: %s is not bound to %s" % (
                        testcase_id, obligation))
        for reference in selected:
            testcase_id = _selected_id(reference)
            requested_revision = _selected_revision(reference)
            if requested_revision == -1:
                errors.append("INVALID_TESTCASE_REVISION: %s" % reference)
            elif requested_revision is not None and testcase_id in by_id:
                actual_revision = by_id[testcase_id].get("revision", 1)
                if requested_revision != actual_revision:
                    errors.append("TESTCASE_REVISION_MISMATCH: %s requested rev%d, inventory has rev%d" % (
                        testcase_id, requested_revision, actual_revision))
        if item.get("historical_pass_inherited") is True:
            errors.append("HISTORICAL_PASS_INHERITED: %s must execute in the current run" % prefix)

        if decision in {"reuse-as-is", "reuse-with-extension"}:
            if not candidate_ids or not selected_ids:
                errors.append("INCOMPLETE_REUSE: %s requires candidates and selected_testcases" % prefix)
            if not selected_ids.issubset(candidate_ids):
                errors.append("REUSE_NOT_FROM_CANDIDATES: %s" % prefix)
            if decision == "reuse-with-extension" and not reason:
                errors.append("MISSING_REASON: %s reuse-with-extension" % prefix)
        elif decision == "supersede":
            if not candidate_ids or not selected_ids or not reason:
                errors.append("INCOMPLETE_SUPERSEDE: %s requires old/new testcase and reason" % prefix)
            for old_id in candidate_ids:
                old = by_id.get(old_id, {})
                if old.get("status") != "superseded":
                    errors.append("NOT_SUPERSEDED: %s" % old_id)
                elif old.get("replacement") not in selected_ids:
                    errors.append("REPLACEMENT_MISMATCH: %s -> %s" % (
                        old_id, old.get("replacement")))
        elif decision == "create-new":
            if not selected_ids or not reason:
                errors.append("INCOMPLETE_CREATE_NEW: %s requires selected testcase and reason" % prefix)

    required = set(required_obligations or [])
    for obligation in sorted(required - covered):
        errors.append("MISSING_REUSE_DECISION: %s" % obligation)
    if locked_testcases is not None:
        locked = {_selected_id(value) for value in locked_testcases}
        if locked != selected_all:
            errors.append("TESTCASE_LOCK_MISMATCH: selected=%s locked=%s" % (
                ",".join(sorted(selected_all)), ",".join(sorted(locked))))
    return sorted(set(errors))


def _print_errors(errors):
    for error in errors:
        print("ERROR: " + error, file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="testcase_inventory.py")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="scan frontmatter and write index.json/index.md")
    build.add_argument("--testcase-dir", required=True)

    validate = sub.add_parser("validate", help="validate an index and optional reuse report")
    validate.add_argument("--testcase-dir", required=True)
    validate.add_argument("--index", default="index.json")
    validate.add_argument("--reuse-report")
    validate.add_argument("--required-obligation", action="append", default=[])
    validate.add_argument("--locked-testcase", action="append")

    query = sub.add_parser("query", help="query reusable active testcase candidates")
    query.add_argument("--index", required=True)
    query.add_argument("--obligation", action="append", default=[])
    query.add_argument("--surface")
    query.add_argument("--tag", action="append", default=[])
    query.add_argument("--entrypoint")
    query.add_argument("--status", action="append")

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            inventory = scan_testcases(args.testcase_dir)
            json_path, markdown_path = write_indexes(inventory, args.testcase_dir)
            print(json.dumps({"testcases": len(inventory["testcases"]),
                              "index_json": str(json_path),
                              "index_markdown": str(markdown_path)}, sort_keys=True))
            return 0
        if args.command == "query":
            inventory = load_inventory(args.index)
            errors = validate_inventory(inventory)
            if errors:
                _print_errors(errors)
                return 1
            matches = query_inventory(inventory, args.obligation, args.surface,
                                      args.tag, args.entrypoint, args.status)
            print(json.dumps(matches, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        inventory_path = Path(args.testcase_dir) / args.index
        inventory = load_inventory(inventory_path)
        errors = validate_inventory(inventory, args.testcase_dir)
        errors.extend(validate_generated_views(inventory, args.testcase_dir))
        if args.reuse_report:
            with open(args.reuse_report, "r", encoding="utf-8") as handle:
                report = json.load(handle)
            errors.extend(validate_reuse_report(
                inventory, report, args.required_obligation, args.locked_testcase))
        if errors:
            _print_errors(sorted(set(errors)))
            return 1
        print("OK: %d testcase(s)" % len(inventory["testcases"]))
        return 0
    except (InventoryError, OSError, json.JSONDecodeError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
