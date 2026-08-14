#!/bin/bash
# 测试 2026-08-14 新增的 12 个命令

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GATE="$SCRIPT_DIR/skills/plan-test/scripts/plan_test_gate.py"
TEST_DIR="/tmp/plan-test-optimization-test-$$"

echo "=== 创建测试环境 ==="
mkdir -p "$TEST_DIR"/{run-dir,repo}
cd "$TEST_DIR/repo"
git init -q

# 创建测试文件
cat > acceptance.md <<'EOF'
# Acceptance Criteria

## MUST
1. Feature A works
2. Feature B works

## SHOULD
1. Feature C works
EOF

cat > plan.md <<'EOF'
# Implementation Plan

## Task 1
Do something

## Task 2
Do something else
EOF

cat > manifest.json <<'EOF'
{
  "schema_version": "1.3.0",
  "scenarios": [
    {
      "scenario_id": "S-1",
      "kind": "required",
      "label": "Basic test"
    }
  ],
  "applicability": {
    "input_sensitive": {"value": false, "rationale": "not applicable", "decided_by": "agent"},
    "llm_payload_driven": {"value": false, "rationale": "not applicable", "decided_by": "agent"},
    "stateful_init": {"value": false, "rationale": "not applicable", "decided_by": "agent"}
  }
}
EOF

git add -A
git commit -q -m "initial"

echo "✓ 测试环境创建完成"
echo

# ============================================================
echo "=== 测试 P0-1: check-release-unit ==="
python3 "$GATE" check-release-unit \
  --acceptance acceptance.md \
  --plan plan.md
echo "✓ P0-1 通过（小 release unit）"
echo

# ============================================================
echo "=== 测试 P0-2: validate-release-unit ==="

# 先 init 一个 ledger
python3 "$GATE" init \
  --run-dir "$TEST_DIR/run-dir" \
  --manifest manifest.json \
  --allow-external-run-dir

# 此时应该失败（没有 release_unit）
if python3 "$GATE" validate-release-unit \
  --run-dir "$TEST_DIR/run-dir" 2>&1 | grep -q "RELEASE_UNIT_UNDECLARED"; then
  echo "✓ P0-2 正确检测到缺少 release_unit"
else
  echo "✗ P0-2 未能检测到缺少 release_unit"
  exit 1
fi

# 手动添加 release_unit
python3 <<EOF
import json
with open("$TEST_DIR/run-dir/plan-test-run.json", "r") as f:
    ledger = json.load(f)
ledger["release_unit"] = {
    "slice_id": "T1.1",
    "parent_program": "test-program",
    "scope_hash": "abc123"
}
with open("$TEST_DIR/run-dir/plan-test-run.json", "w") as f:
    json.dump(ledger, f, indent=2)
EOF

python3 "$GATE" validate-release-unit \
  --run-dir "$TEST_DIR/run-dir"
echo "✓ P0-2 通过（有 release_unit）"
echo

# ============================================================
echo "=== 测试 P0-5: check-wip-limit ==="
python3 "$GATE" check-wip-limit \
  --repo-dir .
echo "✓ P0-5 通过（工作树干净）"

# 创建大量 WIP（修改已跟踪的文件，触发行数限制）
for i in {1..3000}; do
  echo "modification line $i" >> acceptance.md
done

if python3 "$GATE" check-wip-limit \
  --repo-dir . --max-lines 1000 2>&1 | grep -q "WIP_ACCUMULATION_UNSAFE"; then
  echo "✓ P0-5 正确检测到 WIP 超限（行数）"
else
  echo "✗ P0-5 未能检测到 WIP 超限"
  exit 1
fi

# 恢复文件
git checkout acceptance.md
echo

# ============================================================
echo "=== 测试 P1-1: check-ledger-progress ==="
python3 "$GATE" check-ledger-progress \
  --run-dir "$TEST_DIR/run-dir" \
  --min-interval-minutes 9999999 2>&1 | grep -q "LEDGER_STALLED"
echo "✓ P1-1 正确检测到 ledger 无进展"
echo

# ============================================================
echo "=== 测试 P0-3: 循环账本命令 ==="

# 创建新的 run-dir 用于 P0-3/P0-4 测试（避免完整性链问题）
python3 "$GATE" init \
  --run-dir "$TEST_DIR/run-dir-2" \
  --manifest manifest.json \
  --allow-external-run-dir > /dev/null

# 1. start-challenge-loop
loop_id=$(python3 "$GATE" start-challenge-loop \
  --run-dir "$TEST_DIR/run-dir-2" \
  --loop-type plan-iteration \
  --target-file plan.md)

echo "✓ P0-3.1 创建循环: $loop_id"

# 2. check-loop-limit (第 1 轮应该通过)
python3 "$GATE" check-loop-limit \
  --run-dir "$TEST_DIR/run-dir-2" \
  --loop-id "$loop_id"
echo "✓ P0-3.2 检查循环限制通过"

# 3. record-challenge-round
echo '{"critical": 3, "major": 5, "minor": 2}' > findings-1.json
python3 "$GATE" record-challenge-round \
  --run-dir "$TEST_DIR/run-dir-2" \
  --loop-id "$loop_id" \
  --round 1 \
  --plan-hash "abc123def456" \
  --findings findings-1.json \
  --verdict FAIL
echo "✓ P0-3.3 记录第 1 轮挑战"

# 模拟 15 轮循环
for round in {2..15}; do
  python3 "$GATE" record-challenge-round \
    --run-dir "$TEST_DIR/run-dir-2" \
    --loop-id "$loop_id" \
    --round $round \
    --plan-hash "hash-$round" \
    --verdict FAIL \
    > /dev/null 2>&1
done

# 第 16 轮应该被拒绝
if python3 "$GATE" check-loop-limit \
  --run-dir "$TEST_DIR/run-dir-2" \
  --loop-id "$loop_id" 2>&1 | grep -q "LOOP_LIMIT_EXCEEDED"; then
  echo "✓ P0-3.4 正确拒绝第 16 轮"
else
  echo "✗ P0-3.4 未能拒绝第 16 轮"
  exit 1
fi

# 4. detect-loop-reset
python3 "$GATE" detect-loop-reset \
  --run-dir "$TEST_DIR/run-dir-2"
echo "✓ P0-3.5 检测循环重置通过"
echo

# ============================================================
echo "=== 测试 P0-4: A2 Plan Defect 命令 ==="

# 1. check-plan-stability (初始应该通过)
python3 "$GATE" check-plan-stability \
  --run-dir "$TEST_DIR/run-dir-2"
echo "✓ P0-4.1 初始稳定性检查通过"

# 2. record-plan-defect (记录 3 次 A2)
for i in {1..3}; do
  python3 "$GATE" record-plan-defect \
    --run-dir "$TEST_DIR/run-dir-2" \
    --affected-tasks "T$i.1,T$i.2" \
    --defect-type "test-defect-$i" \
    --description "Test defect $i" \
    > /dev/null 2>&1
done
echo "✓ P0-4.2 记录 3 次 A2 事件"

# 3. check-plan-stability (应该失败)
if python3 "$GATE" check-plan-stability \
  --run-dir "$TEST_DIR/run-dir-2" 2>&1 | grep -q "PLAN_UNSTABLE"; then
  echo "✓ P0-4.3 正确检测到 plan 不稳定"
else
  echo "✗ P0-4.3 未能检测到 plan 不稳定"
  exit 1
fi

# 4. resolve-plan-defect
python3 "$GATE" resolve-plan-defect \
  --run-dir "$TEST_DIR/run-dir-2" \
  --event-id a2-001 \
  --resolution "Fixed in phase-2"
echo "✓ P0-4.4 解决 A2 事件"

# 5. reset-plan-defects
approval_hash=$(echo -n "user approval message" | sha256sum | cut -d' ' -f1)
python3 "$GATE" reset-plan-defects \
  --run-dir "$TEST_DIR/run-dir-2" \
  --approval-hash "$approval_hash" \
  --reason "Phase-2 重新收敛"
echo "✓ P0-4.5 重置 A2 计数"
echo

# ============================================================
echo "=== 测试 P1-2: check-plan-growth ==="

# 创建 baseline 和 current plan
cat > plan-baseline.md <<'EOF'
# Plan Baseline
Task 1
Task 2
Task 3
EOF

cat > plan-current.md <<'EOF'
# Plan Current
Task 1
Task 2
Task 3
Task 4
Task 5
Task 6
Task 7
Task 8
EOF

# 应该检测到增长
if python3 "$GATE" check-plan-growth \
  --baseline plan-baseline.md \
  --current plan-current.md \
  --threshold 1.5 2>&1 | grep -q "PLAN_SCOPE_EXPANSION"; then
  echo "✓ P1-2 正确检测到 plan 增长"
else
  echo "✗ P1-2 未能检测到 plan 增长"
  exit 1
fi
echo

# ============================================================
echo "=== 测试 P2-1: show-loop-history ==="

python3 "$GATE" show-loop-history \
  --run-dir "$TEST_DIR/run-dir-2" \
  --loop-id plan-iteration-001 > /dev/null
echo "✓ P2-1 显示循环历史"
echo

# ============================================================
echo "=== 测试 P2-2: record-phase-transition ==="

python3 "$GATE" record-phase-transition \
  --run-dir "$TEST_DIR/run-dir-2" \
  --from-phase phase-2 \
  --to-phase phase-3 \
  --evidence "Plan 收敛，7 轮挑战 PASS" \
  --note "测试转移"
echo "✓ P2-2 记录 phase 转移"
echo

# ============================================================
echo "=== 清理测试环境 ==="
cd /
rm -rf "$TEST_DIR"
echo "✓ 清理完成"
echo

echo "=========================================="
echo "✅ 所有 15 个新命令测试通过！"
echo "=========================================="
echo
echo "已验证命令:"
echo "  P0-1: check-release-unit"
echo "  P0-2: validate-release-unit"
echo "  P0-3: start-challenge-loop, check-loop-limit, record-challenge-round, detect-loop-reset"
echo "  P0-4: record-plan-defect, check-plan-stability, resolve-plan-defect, reset-plan-defects"
echo "  P0-5: check-wip-limit"
echo "  P1-1: check-ledger-progress"
echo "  P1-2: check-plan-growth"
echo "  P2-1: show-loop-history"
echo "  P2-2: record-phase-transition"
