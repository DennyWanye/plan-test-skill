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
HALF_SEEN=""
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
$(find . -path ./node_modules -prune -o -path ./.git -prune -o -path '*/fixtures/*' -prune -o \
       -name plan-test-run.json -print 2>/dev/null)
EOF

# 半截 init：有 gate manifest（或 gate 专属残留产物）却没有账本。
# **不按目录名枚举**——run 目录叫什么名字是调用者定的，把 `verification/` 当识别依据，
# 等于"改个目录名就绕过整个强制点"（独立审计实测：run-dir 放在 plans/run-x/ 下，
# finalize exit 1 四条诊断，hook 却 exit 0）。gate 记账物是内容可识别的，按内容找。
while IFS= read -r cand; do
  [ -z "$cand" ] && continue
  case "$cand" in */fixtures/*|*/.git/*|*/node_modules/*) continue ;; esac
  d="$(dirname "$cand")"
  [ -f "$d/plan-test-run.json" ] && continue
  case " $HALF_SEEN " in *" $d "*) continue ;; esac
  HALF_SEEN="$HALF_SEEN $d"
  # 只认真正的 gate manifest（scenarios 列表 + 一个 gate 专属键），或 gate 专属残留产物
  "$PY" -c "import json,os,sys
d=sys.argv[1]
if any(os.path.isfile(os.path.join(d,f)) for f in
       ('auditor-input.json','auditor-output.json','gate-receipt.json')): sys.exit(0)
m=os.path.join(d,'manifest.json')
if not os.path.isfile(m): sys.exit(1)
try: o=json.load(open(m,encoding='utf-8'))
except Exception: sys.exit(1)
sc=o.get('scenarios') if isinstance(o,dict) else None
# gate 的 scenarios 是「带 scenario_id 的对象数组」——BDD/测试清单通常是字符串数组，
# 用形状而非键名区分，减少对业务 manifest 的误报（独立审计实测过 tests/verification/cases/）。
shaped=isinstance(sc,list) and len(sc)>0 and all(
    isinstance(x,dict) and 'scenario_id' in x for x in sc)
sys.exit(0 if shaped and any(k in o for k in ('applicability','source_request_text',
                                              'source_request_file','run_id')) else 1)" "$d" 2>/dev/null || continue
  FOUND=1
  FAILED=1
  REPORT="$REPORT
── $d ──
该目录有 gate manifest / gate 产物却没有 plan-test-run.json：init 只开了一半（或账本被删）。
补跑 init 并把测试事实入账，或删掉这个目录。
"
done <<EOF
$(find . -path ./node_modules -prune -o -path ./.git -prune -o \
       \( -name manifest.json -o -name auditor-input.json -o -name auditor-output.json \
          -o -name gate-receipt.json \) -print 2>/dev/null)
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
