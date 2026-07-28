#!/usr/bin/env bash
# plan-test Stop hook：会话准备收尾时，强制核对每个 run 账本的机器门状态。
#
# 设计取舍（故意保守，避免误伤正常会话）：
#   - 仓库里没有 run 账本 → 直接放行（S 档交付、纯问答、探索会话不受影响）
#   - 有账本 → 每个都跑 finalize --check-only；任一 FAIL 就以退出码 2 阻止收尾
#   - 只看账本事实，不解析代理说了什么；措辞违规由账本侧的
#     DELIVERY_VERDICT_CONTRADICTS_LEDGER 兜
#
# 安装见 hooks/README.md。退出码：0 放行 / 2 阻止并把 stderr 回灌给代理。

set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || exit 0

GATE=""
for cand in \
  "skills/plan-test/scripts/plan_test_gate.py" \
  ".claude/plugins/plan-test/skills/plan-test/scripts/plan_test_gate.py" \
  "${PLAN_TEST_GATE:-}"
do
  [ -n "$cand" ] && [ -f "$cand" ] && GATE="$cand" && break
done
[ -z "$GATE" ] && exit 0   # 本项目没装 gate 脚本：不是本 hook 的管辖范围

PY="$(command -v python3 || command -v python)"
[ -z "$PY" ] && exit 0

# 只找工作区内的 run 账本，排除 fixtures（合成数据）与依赖目录。
# 用 while-read 而非 mapfile：macOS 自带 bash 3.2 没有 mapfile。
FAILED=0
FOUND=0
REPORT=""
while IFS= read -r led; do
  [ -z "$led" ] && continue
  FOUND=1
  dir="$(dirname "$led")"
  out="$("$PY" "$GATE" finalize --run-dir "$dir" --check-only 2>&1)"
  rc=$?
  # fixture-only 账本不能出现在交付路径上：check-only 对它同样返回 0，
  # 只靠退出码会被"给 manifest 加一个 fixture_only 字段"整个绕过（独立审计实测）。
  if "$PY" -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1],encoding='utf-8')).get('fixture_only') else 1)" "$led" 2>/dev/null; then
    FAILED=1
    REPORT="$REPORT
── $dir ──
该账本是 fixture-only（合成数据，跳过全部 git 校验），不能作为交付证据。
真实交付请用 fixture_only=false 重新 init；确属 fixture 演练请移出 verification/ 目录。
"
  elif [ "$rc" -ne 0 ]; then
    # 未闭环的 run：只有**经 CLI 正当退役**（链自洽 + 有 retire 操作 + 继任 run 已 SHIPPABLE
    # 且 receipt 未失效）才放行。判定交给 gate 自己（retire-status），hook 不解读账本字段——
    # 独立审计实测过：hook 自己读 `retired` 且放在 check-only 之前时，手写两个词就能让
    # 一个 required FAIL 的 run 从门前消失，且 LEDGER_TAMPERED 永远不会被打印。
    if "$PY" "$GATE" retire-status --run-dir "$dir" >/dev/null 2>&1; then
      continue
    fi
    FAILED=1
    REPORT="$REPORT
── $dir ──
$out
"
  fi
done <<EOF
$(find . -path ./node_modules -prune -o -path '*/fixtures/*' -prune -o \
       -name plan-test-run.json -path '*/verification/*' -print 2>/dev/null)
EOF

# 半截 init：有 verification/<run>/ 目录（artifacts/manifest 已就位）却没有账本 —— 
# 这是"开了个头就去收尾"的典型形态，此前 hook 完全无感（独立审计实测）。
while IFS= read -r d; do
  [ -z "$d" ] && continue
  case "$d" in */fixtures/*) continue ;; esac
  [ -f "$d/plan-test-run.json" ] && continue
  # 必须存在 gate manifest 才算"开了一半的 run"——只按目录名判定会把业务目录
  # （如 src/verification/rules/）误报成半截 init，实测过（独立审计 AC-7 打穿点）。
  # 判据放宽到"确实是 gate manifest"：必须有 scenarios 列表，且至少还有一个 gate 专属键。
  # 只看 run_id 会误伤业务文件（`{"run_id":"batch-2026","limit":100}` 也会中招，独立审计实测）。
  # 另一条便宜的逃逸是"删掉账本但留下 auditor-*.json / gate-receipt.json"——一并识别。
  "$PY" -c "import json,os,sys
d=sys.argv[1]
# 只认 gate 专属文件名。report.md 是通用名（业务的"来料检验报告"就叫这个），
# 把它当信号会误伤 docs/verification/**、tests/verification/** 等目录——独立审计实测过。
leftovers=[f for f in ('auditor-input.json','auditor-output.json','gate-receipt.json')
           if os.path.isfile(os.path.join(d,f))]
if leftovers: sys.exit(0)          # 有 gate 产物却没账本：账本被删了
m=os.path.join(d,'manifest.json')
if not os.path.isfile(m): sys.exit(1)
try: o=json.load(open(m,encoding='utf-8'))
except Exception: sys.exit(1)
ok=isinstance(o,dict) and isinstance(o.get('scenarios'),list) and any(
    k in o for k in ('applicability','acceptance_file','acceptance_text','source_request_text','source_request_file'))
sys.exit(0 if ok else 1)" "$d" 2>/dev/null || continue
  FOUND=1
  FAILED=1
  REPORT="$REPORT
── $d ──
该 run 目录没有 plan-test-run.json：init 只开了一半（或被清掉）。
补跑 init 并把测试事实入账，或删掉这个空目录。
"
done <<EOF
$(for vdir in $(find . -path ./node_modules -prune -o -type d -name verification -print 2>/dev/null); do
    for sub in "$vdir"/*/; do
      [ -d "$sub" ] && echo "${sub%/}"
    done
  done)
EOF

[ "$FOUND" -eq 0 ] && exit 0

if [ "$FAILED" -eq 1 ]; then
  {
    echo "plan-test 机器门未通过：存在 run 账本但预检 FAIL，不能收尾。"
    echo "请按诊断补测/补证据后重跑 finalize --check-only；确实做不到的项标 BLOCKED 升级给用户。"
    echo "$REPORT"
  } >&2
  exit 2
fi
exit 0
