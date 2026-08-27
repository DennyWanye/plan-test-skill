#!/usr/bin/env bash
# AC-6 E2E：Stop hook——失败账本 exit 2 并输出诊断，无记账物仓库 exit 0 放行。
# 自包含：账本用 gate CLI 在临时仓库真 init；gate 经 PLAN_TEST_GATE 显式注入。
# 退出码：0 = 两个用例全部符合预期。
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
GATE="$REPO/skills/plan-test/scripts/plan_test_gate.py"
export PLAN_TEST_GATE="$GATE"
PY="$(command -v python3 || command -v python)"
HOOK="$REPO/hooks/stop-gate-check.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# case 1：required 场景未跑的真实账本 → exit 2 + 诊断
R1="$WORK/r1"
git init -q "$R1"
git -C "$R1" config user.email t@t
git -C "$R1" config user.name t
echo base > "$R1/base.md"
git -C "$R1" add -A && git -C "$R1" commit -qm base
mkdir -p "$R1/plans/p/verification/r1"
printf 'AC-1 必须：X\n' > "$R1/acceptance.md"
"$PY" - "$R1" <<'PYEOF'
import json, sys
repo = sys.argv[1]
m = {
    "run_id": "e2e-stop-hook",
    "source_request_text": "Stop hook E2E 测试夹具（required 场景故意不跑）",
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
json.dump(m, open(repo + "/manifest.json", "w", encoding="utf-8"), ensure_ascii=False)
PYEOF
(cd "$R1" && "$PY" "$GATE" init --run-dir plans/p/verification/r1 \
   --manifest manifest.json >/dev/null)

rc=0
CLAUDE_PROJECT_DIR="$R1" bash "$HOOK" </dev/null >/dev/null 2>"$WORK/c1.log" || rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL case1: 期望 exit 2，得到 $rc"; cat "$WORK/c1.log"; exit 1; }
grep -q "机器门未通过" "$WORK/c1.log" || { echo "FAIL case1: 缺拦截诊断"; cat "$WORK/c1.log"; exit 1; }
echo "case1 failing ledger blocked: OK (rc=$rc)"

# case 2：无记账物仓库 → exit 0 放行
R2="$WORK/r2"
git init -q "$R2"
echo hi > "$R2/readme.md"
rc=0
CLAUDE_PROJECT_DIR="$R2" bash "$HOOK" </dev/null >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL case2: 期望 exit 0，得到 $rc"; exit 1; }
echo "case2 clean repo allowed: OK (rc=$rc)"

# case 3（F-002）：插件 cache 兜底解析——无 PLAN_TEST_GATE、HOME 指向只含插件 cache
# 布局的假家目录，复用 case 1 的失败账本仓库 → hook 仍须经 cache glob 找到 gate 并拦截。
FAKEHOME="$WORK/fakehome"
CACHE="$FAKEHOME/.claude/plugins/cache/e2e-market/plan-test/0.0.1"
mkdir -p "$CACHE/skills/plan-test/scripts" "$CACHE/hooks"
cp "$GATE" "$CACHE/skills/plan-test/scripts/plan_test_gate.py"
cp "$REPO/hooks/gate_scan.py" "$CACHE/hooks/gate_scan.py"
rc=0
env -u PLAN_TEST_GATE -u CLAUDE_PLUGIN_ROOT HOME="$FAKEHOME" CLAUDE_PROJECT_DIR="$R1" \
  bash "$HOOK" </dev/null >/dev/null 2>"$WORK/c3.log" || rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL case3: 期望 exit 2，得到 $rc（cache 兜底未解析到 gate？）"; cat "$WORK/c3.log"; exit 1; }
grep -q "机器门未通过" "$WORK/c3.log" || { echo "FAIL case3: 缺拦截诊断"; cat "$WORK/c3.log"; exit 1; }
echo "case3 plugin-cache fallback blocked: OK (rc=$rc)"

# case 4（Windows 静默桩回归）：WindowsApps 的 python3 是 rc=0、零输出、不执行代码的桩，
# 选中它会把门变成静默 no-op（2026-08-27 Windows 插件安装实测无声放行）。按 Windows 的
# 真实形态构造：PATH 首位是死的 python3 桩 + 活的 python 并存；hook 必须功能探测出
# 桩是坏的、退回 python，仍然拦截失败账本。
STUB="$WORK/stub"; mkdir -p "$STUB"
REAL_PY="$(command -v python3)"
printf '#!/bin/sh\nexit 0\n' > "$STUB/python3"
printf '#!/bin/sh\nexec "%s" "$@"\n' "$REAL_PY" > "$STUB/python"
chmod +x "$STUB/python3" "$STUB/python"
rc=0
PATH="$STUB:$PATH" CLAUDE_PROJECT_DIR="$R1" \
  bash "$HOOK" </dev/null >/dev/null 2>"$WORK/c4.log" || rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL case4: 期望 exit 2，得到 $rc（静默桩把门变成 no-op？）"; cat "$WORK/c4.log"; exit 1; }
grep -q "机器门未通过" "$WORK/c4.log" || { echo "FAIL case4: 缺拦截诊断"; cat "$WORK/c4.log"; exit 1; }
echo "case4 silent-python3-stub still blocked: OK (rc=$rc)"

echo "E2E-STOP-HOOK: PASS"
