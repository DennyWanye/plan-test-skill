# Testcase inventory and reuse lifecycle

Read this reference when selecting, creating, or maintaining project testcases.
The testcase Markdown frontmatter is the source of truth; `index.json` and
`index.md` are deterministic generated views.

Legacy Markdown without frontmatter is not discarded. The builder indexes it
with a deterministic `LEGACY-*` ID and `needs-review` status, so it remains
discoverable but cannot be selected until a maintainer adds real metadata.

## Minimal frontmatter

```yaml
---
id: TC-MEM-RESTART-001
purpose: Verify semantic recall after a process restart
status: active
surface: api
type: scripted
obligations:
  - TO-MEM-03
tags:
  - memory
  - restart
entrypoint: runtime gateway
revision: 3
---
```

Supported statuses are `active`, `needs-review`, `retired`, and `superseded`.
Retired and superseded testcases remain in the repository and must name a valid
`replacement`; they cannot be selected for a new run.

## Workflow

1. Run `testcase_inventory.py build --testcase-dir <dir>` before designing new
   cases. This scans testcase Markdown and regenerates both indexes.
2. Query active candidates by obligation, surface, entrypoint, and tags. Read
   each candidate's full steps and expected results before deciding.
3. Record exactly one decision per required obligation:
   `reuse-as-is`, `reuse-with-extension`, `supersede`, or `create-new`.
4. For extension, supersede, and creation, record a concrete reason. A new case
   must already be indexed before the reuse report can pass validation.
5. Freeze the selected testcase revisions, execute them in the current run, and
   store actual results outside the oracle files. Historical PASS never replaces
   current execution.
6. After execution, update lifecycle metadata and regenerate the indexes.

Validate inventory paths, IDs, replacement chains, reuse decisions, required
obligation coverage, and the testcase lock with `testcase_inventory.py validate`.
The human-readable index is navigation metadata only; it is never PASS/FAIL
authority.
