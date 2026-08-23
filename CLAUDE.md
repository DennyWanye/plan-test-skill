# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code **plugin** containing three skills that orchestrate a complete development workflow from requirements to delivery:

- **`/plan-bs`**: Brainstorm & co-create plan → challenge & iterate → user review (does NOT implement business code)
- **`/plan-task`**: Execute a finalized plan → 100% completion audit → testing → delivery
- **`/plan-test`**: End-to-end automated version of the above two (requirements → architecture → plan → execute → test → DoD)

The skills share phase documents, prompts, and configuration from `skills/plan-test/`.

## Repository Workflow

For this repository, develop directly on `main` and push to `origin/main`. Do not create feature branches or
worktrees unless the repository owner explicitly overrides this policy for a specific task.

## Core Architecture Principles

### Machine Gate as Single Authority

**Markdown is the human-readable view, NOT the state authority.** Test facts are recorded in `plan-test-run.json` (the unique ledger), and all status/state is recomputed by the deterministic validator. 

- Final delivery decisions ONLY accept the exit code from `python skills/plan-test/scripts/plan_test_gate.py finalize --run-dir <run-dir>`
- Exit codes: **0** = real delivery pass, **1** = gate fail, **2** = usage error, **3** = fixture-only pass (not shippable)
- Hand-written `SHIP`/`100% COMPLETE` without a valid `gate-receipt.json` is always treated as `DELIVERY_VERDICT_CONTRADICTS_LEDGER`

### State Machine

```
DRAFT → ACCEPTED → IMPLEMENTED → TESTED → VALIDATED → SHIPPABLE
```

States are computed by the validator, never hand-written.

### Integrity Chain

Every write to the ledger appends to the integrity chain: `chain_n = sha256(chain_{n-1} + op + facts_digest)`. Hand-editing a ledger line (like changing `runs[].result`) → `LEDGER_TAMPERED`. The chain detects casual editing but doesn't prevent determined forgery (it's a local file).

## Common Commands

### Testing the Gate System

```bash
# Run the full test suite (all discovered tests must pass)
python3 -m unittest discover -s skills/plan-test/scripts -p 'test*.py'
```

**Always run this after modifying any gate-related code.** The two static fixtures (`pass-minimal` and `fail-companion-conflict`) are frozen behavioral contracts.

### Gate CLI Usage

```bash
# Initialize a new run
python3 skills/plan-test/scripts/plan_test_gate.py init \
  --run-dir <plan>/verification/<run-id> --manifest manifest.json

# P0-1: Check release unit size before Phase 3 (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py check-release-unit \
  --acceptance <acceptance.md> \
  --plan <plan.md or implementation-tasks.md>

# P0-2: Validate release_unit declaration (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py validate-release-unit \
  --run-dir <run-dir>

# Record a test run (self-reported result)
python3 skills/plan-test/scripts/plan_test_gate.py record-run \
  --run-dir <D> --scenario S-1 --kind root --result pass

# Record a test run with real execution (preferred for scripted tests, 2026-08-19 new):
# gate runs the command itself, result comes from the exit code, and the output log
# is automatically attached as primary evidence
python3 skills/plan-test/scripts/plan_test_gate.py record-run \
  --run-dir <D> --scenario S-1 --kind root --exec -- python -m pytest tests/ -q

# Attach evidence
python3 skills/plan-test/scripts/plan_test_gate.py attach-evidence \
  --run-dir <D> --path artifacts/screenshot.png --kind primary --ui-action

# Record timing (measured via --exec or declared)
python3 skills/plan-test/scripts/plan_test_gate.py record-timing \
  --run-dir <D> --phase phase-4 --activity-class automated_test --exec -- <cmd>

# P0-5: Check WIP accumulation (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py check-wip-limit \
  --repo-dir <repo-path>

# P1-1: Check ledger progress (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py check-ledger-progress \
  --run-dir <run-dir>

# P0-3: Start a challenge loop (2026-08-14 new)
loop_id=$(python3 skills/plan-test/scripts/plan_test_gate.py start-challenge-loop \
  --run-dir <run-dir> --loop-type plan-iteration \
  --target-file <plan.md>)

# P0-3: Check loop limit before each round (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py check-loop-limit \
  --run-dir <run-dir> --loop-id $loop_id

# P0-3: Record challenge round results (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py record-challenge-round \
  --run-dir <run-dir> --loop-id $loop_id --round 1 \
  --plan-hash <sha256> --findings <findings.json> --verdict PASS

# P0-3: Detect loop reset evasion (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py detect-loop-reset \
  --run-dir <run-dir> --check-target-file <plan.md>

# P0-4: Record A2 plan defect (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py record-plan-defect \
  --run-dir <run-dir> --affected-tasks T4.1,T4.2 \
  --defect-type contract-conflict --description "..."

# P0-4: Check plan stability (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py check-plan-stability \
  --run-dir <run-dir>

# P0-4: Resolve a plan defect (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py resolve-plan-defect \
  --run-dir <run-dir> --event-id a2-001 --resolution "..."

# P0-4: Reset plan defects (requires user approval, 2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py reset-plan-defects \
  --run-dir <run-dir> --approval-hash <sha256> --reason "..."

# P1-2: Check plan growth (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py check-plan-growth \
  --baseline <baseline-plan.md> --current <current-plan.md>

# P2-1: Show loop history (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py show-loop-history \
  --run-dir <run-dir> --loop-id <loop-id>

# P2-2: Record phase transition (2026-08-14 new)
python3 skills/plan-test/scripts/plan_test_gate.py record-phase-transition \
  --run-dir <run-dir> --from-phase phase-2 --to-phase phase-3 \
  --evidence "..." --note "..."

# Checkpoint during work
python3 skills/plan-test/scripts/plan_test_gate.py checkpoint \
  --run-dir <D> --slice <name> --note "..."

# Check readiness (before audit)
python3 skills/plan-test/scripts/plan_test_gate.py finalize --run-dir <D> --check-only

# Record audit results
python3 skills/plan-test/scripts/plan_test_gate.py audit \
  --run-dir <D> --verdict PASS --engine <auditor-engine> \
  --input auditor-input.json --output auditor-output.json

# Final gate (produces receipt on exit 0)
python3 skills/plan-test/scripts/plan_test_gate.py finalize --run-dir <D>

# Render human-readable report
python3 skills/plan-test/scripts/plan_test_gate.py render --run-dir <D>
```

### Managing Historical Runs

```bash
# Retire a run (transfer responsibility to a successor run)
python3 skills/plan-test/scripts/plan_test_gate.py retire \
  --run-dir <old> --superseded-by <new> --reason "..."

# Acknowledge abandonment (user explicitly gives up on a run)
python3 skills/plan-test/scripts/plan_test_gate.py acknowledge \
  --run-dir <D> --reason "..." --approval-hash <sha256-of-user-message>

# Re-attest after changes during finalization
python3 skills/plan-test/scripts/plan_test_gate.py re-attest \
  --run-dir <D> --reason "documentation updates"
```

## Key Concepts

### Run Directory Structure

Every verification uses a fixed layout:

```
<plan-folder>/verification/<run-id>/
  plan-test-run.json       # Unique state ledger (facts only)
  artifacts/               # Screenshots, logs, primary evidence
  auditor-input.json       # Frozen audit input
  auditor-output.json      # Audit output
  gate-receipt.json        # Only exists after successful finalize
  report.md                # Human-readable view (generated by render)
```

### Diagnostic Codes

The gate has 25+ stable diagnostic codes in canonical order (see `gate/PROTOCOL.md` §4). Key codes:

- `SCHEMA_INVALID`: Ledger doesn't match schema
- `LEDGER_TAMPERED`: Integrity chain broken
- `REQUIRED_SCENARIO_NOT_RUN`: Required scenario not executed
- `STATUS_CONFLICT`: Declared status contradicts ledger
- `FROZEN_ORACLE_CHANGED`: Test case changed without approval
- `APPLICABILITY_GATE_UNSATISFIED`: Declared applicable but matrix not satisfied
- `AUDITOR_VERDICT_MISMATCH`: Audit output doesn't match command line
- `RECEIPT_STALE`: Receipt digest doesn't match current input

**2026-08-14 New Diagnostic Codes:**

- `RELEASE_UNIT_TOO_LARGE`: MUST AC count, plan lines, or high-risk subsystems exceed limits
- `RELEASE_UNIT_UNDECLARED`: Ledger missing release_unit declaration (slice_id/parent_program/scope_hash)
- `WIP_ACCUMULATION_UNSAFE`: Uncommitted changes exceed safe threshold (>5000 lines or >20 files)
- `LOOP_LIMIT_EXCEEDED`: Challenge loop exceeded MAX_ROUNDS (15)
- `LOOP_REGRESSION`: Plan hash reverted to an earlier round
- `LOOP_NO_PROGRESS`: Challenge loop stuck (3+ rounds with no reduction in critical findings)
- `LOOP_RESET_EVASION`: Attempt to bypass loop limit by deleting ledger or changing target
- `PLAN_UNSTABLE`: Phase 3 A2 plan defects >= 3 (Phase 2 did not truly converge)
- `LEDGER_STALLED`: Ledger has no progress (runs/evidence/timing) for >90 minutes
- `PLAN_SCOPE_EXPANSION` (advisory): Plan size increased by >50% from baseline (exit 0, 仅警告)

**总计诊断码**: 46 个（原 32 + 2026-08-14 新增 9 + 2026-08-19 新增 5 个 advisory 曝光码：
`RUN_ATTESTATION_FANOUT` / `EVIDENCE_FREE_FINALIZE` / `EXECUTOR_ENGINE_UNDECLARED` /
`AUDITOR_ENGINE_MISMATCH` / `OPEN_DEFERRALS`，均不拦截、fixture 免检）

Diagnostic output is deterministic: same ledger state → same diagnostic sequence byte-for-byte.

### Frozen Oracle

Black-box testcases are frozen (per-file hash) before implementation via `init`. Any byte change → `FROZEN_ORACLE_CHANGED` unless bound to a `behavior_change_id` with user approval.

### Applicability Gates

Three dimensions must be explicitly declared in the manifest's `applicability` section with value, rationale (≥10 chars), and `decided_by`:

- `input_sensitive`: If true, requires ≥3 distinct input classes and at least one `positive-value` scenario
- `llm_payload_driven`: If true, requires ≥2 root runs for stochastic scenarios
- `stateful_init`: If true, requires a `cold_start: true` scenario

Declaring "not applicable" is legal but leaves a traceable record. Declaring "applicable" without satisfying the matrix → `APPLICABILITY_GATE_UNSATISFIED`.

### Tested Runtime Identity

Identity is determined by **tested content**, not commit identity (schema 1.2.0+). The `content_digest` is a hash of all tracked files + non-ignored untracked files. `git commit` doesn't change content → fingerprint stays same → gate doesn't block. Change one byte → `TESTED_RUNTIME_MISMATCH`.

The exclusion scope (current run-dir + manifest's `related_run_dirs`) is frozen at init time and appears in the receipt digest.

### Re-attestation

After behavioral changes during finalization, use `re-attest`:
- **doc-only** changes (matching the doc whitelist) → existing test conclusions remain valid
- **behavioral** changes → affected required scenarios need a new root PASS after the attestation (controlled by `impact_paths` mapping in manifest)

## Configuration

Default configuration: `skills/plan-test/config.md`
Project overrides: `.claude/plan-test.config.md` (only write keys you want to change)

Key configuration variables:
- `EXECUTOR_ENGINE`: current (inherit the user's current session model; no fixed model binding)
- `CHALLENGER_ENGINE`: claude
- `AUDITOR_ENGINE`: opus-4.8
- `FLOW_TIER`: auto (DIRECT/LEAN/FULL based on risk and reversibility)
- `ARCH_DIR`: ./ARCHITECTURE
- `PLANS_DIR`: ./plans
- `TESTCASE_DIR`: ./testcase
- `ACCEPTANCE_FILE`: ./acceptance.md

## Phases

The full workflow (L tier) has 8 phases:

| Phase | Document | Key Output |
|-------|----------|------------|
| A | `phase-A-acceptance.md` | acceptance.md (single source of truth) |
| 0 | `phase-0-architecture.md` | ARCHITECTURE.md + index |
| 1 | `phase-1-plan.md` | Executable plan.md |
| 2 | `phase-2-iterate-plan.md` | Finalized plan + green baseline |
| 3 | `phase-3-execute.md` | Code + completion audit |
| 4 | `phase-4-stage-gate.md` | Test facts in ledger + READY_FOR_AUDIT |
| 5 | `phase-5-testcase.md` | Testcases + full-audit results |
| final | `phase-final-dod.md` | exit 0 + gate receipt + DoD checklist |

Phases have dependencies but allow parallelism where possible (see `SKILL.md` for dependency graph).

## Important Files to Read

**Before starting any work on the gate system:**
1. `skills/plan-test/gate/PROTOCOL.md` - Normative contract, diagnostics, and limitations
2. `skills/plan-test/gate/ROADMAP.md` - Completed and remaining work
3. `skills/plan-test/schemas/plan-test-run.schema.json` - Current ledger schema
4. `HANDOFF.md` - Detailed context on the three implementation rounds

**For understanding the workflow:**
1. `skills/plan-test/SKILL.md` - Entry point with frontmatter
2. `skills/plan-test/config.md` - All configurable variables
3. The phase documents (`phase-A-acceptance.md` through `phase-final-dod.md`)

## What the Gate CANNOT Prevent

From `gate/PROTOCOL.md` §6b - be honest about limitations:

- **Evidence can be forged**: The gate only validates file existence and hash, not content authenticity
- **Results are self-reported**: `record-run --result pass` is free text
- **Oracle is defined by the testee**: Scenarios come from the agent's manifest - missing a risk scenario means the gate doesn't know it should exist
- **The gate only exists if called**: Running the script is voluntary unless enforced via Stop hook or CI (see `hooks/README.md`)

The gate validates **consistency between recorded facts**, not whether the facts actually occurred. It's a true gate for internal consistency, but a high-cost reminder for fact authenticity.

## Hard Rules

1. Account only facts; states are computed by validator
2. Retry/replay/continuation are NOT root runs - only root runs count toward scenario status
3. `blocked` is non-sticky (resolved by a subsequent root pass); `fail` is sticky
4. Evidence hierarchy: screenshots/logs/receipts are primary; reports are derived
5. Engine terminal state ≠ business success
6. Frozen oracle: byte changes fail unless bound to user-approved `behavior_change_id`
7. Audit freezes `facts_digest`: any change after audit → `AUDITOR_INPUT_STALE`
8. Runtime identity by content, not commit hash
9. Fixture-only runs always marked FIXTURE-ONLY, never valid delivery evidence
10. Timing is first-class evidence (schema 1.3.0+): real runs >30min need ≥20% coverage
11. Ledger can only be written via CLI (integrity chain enforced)
12. Auditor output > command line for verdict

## Never Do This

- Don't add prompt-only rules claiming they solve problems - known violations must go into the validator
- Don't allow hand-written PASS/status fields
- Don't bypass `finalize` exit code with another delivery decision mechanism
- Don't modify historical evidence or fixture expectations to make history green
- Don't mix declared timing into measured aggregates without the `measured:false` flag
- Don't push to remote without explicit user request

## Verification After Changes

After modifying gate code:

```bash
python3 -m unittest discover -s skills/plan-test/scripts -p 'test*.py'
```

All discovered tests must pass. Any change that alters the two static fixture outputs (`pass-minimal` must reach SHIPPABLE + receipt; `fail-companion-conflict` must match its frozen diagnostics) requires reviewing the new output and explaining the reason in the commit message.
