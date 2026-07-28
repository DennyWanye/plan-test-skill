#!/usr/bin/env bash
# plan-test Stop hook：会话准备收尾时，强制核对每个 run 账本的机器门状态。
#
# 设计取舍（故意保守，避免误伤正常会话）：
#   - 工作区里没有 gate 记账物 → 直接放行（S 档交付、纯问答、探索会话不受影响）
#   - 有账本 → 每个都跑 finalize --check-only；任一 FAIL 就以退出码 2 阻止收尾
#   - 只看账本事实，不解析代理说了什么；措辞违规由账本侧的
#     DELIVERY_VERDICT_CONTRADICTS_LEDGER 兜
#   - 识别账本靠**内容形状**（见 gate_scan.py），不靠文件名或目录名——两者都被独立审计
#     各打穿过一次（改目录名 / 改文件名即可让失败 run 从门前消失）
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

SCANNER=""
for cand in "$(dirname "$0")/gate_scan.py" "hooks/gate_scan.py" ".claude/hooks/gate_scan.py"
do
  [ -f "$cand" ] && SCANNER="$cand" && break
done
[ -z "$SCANNER" ] && exit 0

FAILED=0
FOUND=0
REPORT=""

SCAN="$("$PY" "$SCANNER" 2>/dev/null)"
LEDGERS="$(printf '%s\n' "$SCAN" | sed -n '/^LEDGERS$/,/^HALVES$/p' | sed '1d;$d')"
HALVES="$(printf '%s\n' "$SCAN" | sed -n '/^HALVES$/,$p' | sed '1d')"

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
真实交付请用 fixture_only=false 重新 init；确属 fixture 演练请移出工作区。
"
  elif [ "$rc" -ne 0 ]; then
    # 未闭环的 run：只有**经 CLI 正当退役**（链自洽 + 有 retire 操作 + 继任 run 已 SHIPPABLE
    # 且覆盖本 run 的 required 场景）才放行。判定交给 gate 自己，hook 不解读账本字段——
    # 独立审计实测过：hook 自己读 retired 且放在 check-only 之前时，手写两个词就能绕过。
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
$LEDGERS
EOF

while IFS= read -r mf; do
  [ -z "$mf" ] && continue
  d="$(dirname "$mf")"
  FOUND=1
  FAILED=1
  REPORT="$REPORT
── $d ──
该目录有 gate manifest 却没有账本：init 只开了一半，或账本被删/改名。
补跑 init 并把测试事实入账，或删掉这个目录。
"
done <<EOF
$HALVES
EOF

[ "$FOUND" -eq 0 ] && exit 0

if [ "$FAILED" -eq 1 ]; then
  {
    echo "plan-test 机器门未通过：存在 gate 记账物但预检 FAIL，不能收尾。"
    echo "请按诊断补测/补证据后重跑 finalize --check-only；确实做不到的项标 BLOCKED 升级给用户。"
    echo "$REPORT"
  } >&2
  exit 2
fi
exit 0
