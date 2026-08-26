#!/usr/bin/env bash
# AC-5 E2E：pre-push 适配器在真实 git push 路径上——失败账本拦、fixture_only 直查拦、
# 干净仓库放行。自包含：账本用 gate CLI 在临时仓库里真 init 出来，不依赖任何外部
# 工作区状态；gate 经 PLAN_TEST_GATE 显式注入，脱离安装状态可复现。
# 退出码：0 = 三个用例全部符合预期。
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
GATE="$REPO/skills/plan-test/scripts/plan_test_gate.py"
export PLAN_TEST_GATE="$GATE"
PY="$(command -v python3 || command -v python)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BARE="$WORK/remote.git"
git init -q --bare "$BARE"

mk_repo() {  # $1 = path
  git init -q "$1"
  git -C "$1" remote add origin "$BARE"
  git -C "$1" config user.email t@t
  git -C "$1" config user.name t
  echo base > "$1/base.md"
  git -C "$1" add -A
  git -C "$1" commit -qm base
}

mk_failing_ledger() {  # $1 = repo path, $2 = "true"|"false" (fixture_only)
  mkdir -p "$1/plans/p/verification/r1"
  printf 'AC-1 必须：X\n' > "$1/acceptance.md"
  "$PY" - "$1" "$2" <<'PYEOF'
import json, sys
repo, fixture = sys.argv[1], sys.argv[2] == "true"
m = {
    "run_id": "e2e-pre-push-fixture" if fixture else "e2e-pre-push-real",
    "source_request_text": "pre-push E2E 测试夹具（required 场景故意不跑，制造失败账本）",
    "scenarios": [{"scenario_id": "S-1", "required": True}],
    "acceptance_file": "acceptance.md",
    "applicability": {
        "input_sensitive": {"value": False, "decided_by": "agent",
                            "rationale": "确定性 CLI 测试夹具，输出不随输入语义变化"},
        "llm_payload_driven": {"value": False, "decided_by": "agent",
                               "rationale": "无 LLM 载荷驱动端侧状态机的路径"},
        "stateful_init": {"value": False, "decided_by": "agent",
                          "rationale": "无异步注册服务或登录态依赖"},
    },
}
if fixture:
    m["fixture_only"] = True
    m["baseline"] = {"head": "deadbeef", "dirty_patch_sha256": "0" * 64}
json.dump(m, open(repo + "/manifest.json", "w", encoding="utf-8"), ensure_ascii=False)
PYEOF
  (cd "$1" && "$PY" "$GATE" init --run-dir plans/p/verification/r1 \
     --manifest manifest.json >/dev/null)
  git -C "$1" add -A
  git -C "$1" commit -qm run
}

# case 1：required 场景未跑的真实账本 → push 被拦
R1="$WORK/r1"; mk_repo "$R1"; mk_failing_ledger "$R1" false
bash "$REPO/hooks/adapters/git/install-pre-push.sh" "$R1" >/dev/null
rc=0; git -C "$R1" push -q origin HEAD:main 2>"$WORK/c1.log" || rc=$?
[ "$rc" -ne 0 ] || { echo "FAIL case1: 失败账本没被拦"; exit 1; }
grep -q "机器门（pre-push）" "$WORK/c1.log" || { echo "FAIL case1: 缺拦截诊断"; cat "$WORK/c1.log"; exit 1; }
echo "case1 failing ledger blocked: OK (rc=$rc)"

# case 2：fixture_only 账本 → 直查字段拦（check-only 对它返回 0，只看退出码会漏）
R2="$WORK/r2"; mk_repo "$R2"; mk_failing_ledger "$R2" true
bash "$REPO/hooks/adapters/git/install-pre-push.sh" "$R2" >/dev/null
rc=0; git -C "$R2" push -q origin HEAD:fixture 2>"$WORK/c2.log" || rc=$?
[ "$rc" -ne 0 ] || { echo "FAIL case2: fixture 账本没被拦"; exit 1; }
grep -q "fixture-only" "$WORK/c2.log" || { echo "FAIL case2: 缺 fixture 诊断"; cat "$WORK/c2.log"; exit 1; }
echo "case2 fixture-only blocked: OK (rc=$rc)"

# case 3：无记账物仓库 → 放行
R3="$WORK/r3"; mk_repo "$R3"
bash "$REPO/hooks/adapters/git/install-pre-push.sh" "$R3" >/dev/null
git -C "$R3" push -q origin HEAD:clean 2>"$WORK/c3.log"
echo "case3 clean repo allowed: OK"

echo "E2E-PRE-PUSH: PASS"
