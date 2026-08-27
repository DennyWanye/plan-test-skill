#!/usr/bin/env bash
# plan-test Stop hook：会话准备收尾时，强制核对每个 run 账本的机器门状态。
#
# 设计取舍（故意保守，避免误伤正常会话）：
#   - 工作区里没有 gate 记账物 → 直接放行（DIRECT、纯问答、探索会话不受影响）
#   - 有账本 → 每个都跑机器判定；任一 FAIL 就以退出码 2 阻止收尾
#   - 只看账本事实，不解析代理说了什么；措辞违规由账本侧的
#     DELIVERY_VERDICT_CONTRADICTS_LEDGER 兜
#   - 识别账本靠**内容形状**（见 gate_scan.py），不靠文件名或目录名——两者都被独立审计
#     各打穿过一次（改目录名 / 改文件名即可让失败 run 从门前消失）
#
# 输出预算（2026-08-09 重写，simple_harness r9 实跑反馈）：
#   旧版对**每一个** run-dir 打印完整诊断。7 个历史 run-dir = 单次 Stop 300+ 行 / ~10k token，
#   一个会话触发 12+ 次，而且这些内容**与本回合做了什么无关**——只改了一个证据文件、甚至
#   没碰账本，照样把 r3…r8 全刷一遍。代理真正能据以行动的只有两条：被拦了 + 哪个还没闭环。
#   现在：
#     1) 只有**活动轮**详报（且截断到 MAX_LINES 行），其余每个一行摘要；
#     2) 报告指纹与上次完全相同 → 只出摘要，不重复正文；
#     3) 连续 MAX_REPEATS 次内容完全没变 → 放行一次并大声说明（见下方"死循环断路器"）。
#
# 可调（环境变量）：
#   PLAN_TEST_GATE_MAX_LINES=24    活动轮详报的最大行数
#   PLAN_TEST_GATE_MAX_REPEATS=3   连续几次"完全无变化"后放行；设 0 = 永不放行（旧行为）
#
# 安装见 hooks/README.md。退出码：0 放行 / 2 阻止并把 stderr 回灌给代理。

set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || exit 0

MAX_LINES="${PLAN_TEST_GATE_MAX_LINES:-24}"
MAX_REPEATS="${PLAN_TEST_GATE_MAX_REPEATS:-3}"
# 环境变量写错不该让门整个崩掉——非数字一律退回默认值
case "$MAX_LINES" in ''|*[!0-9]*) MAX_LINES=24 ;; esac
case "$MAX_REPEATS" in ''|*[!0-9]*) MAX_REPEATS=3 ;; esac

# 找 gate 脚本：项目内优先，其次全局安装位置。
# **全局安装必须能找到它**——否则把 hook 挂到 ~/.claude/settings.json 之后，在任何"项目里没有
# 这套 skill"的仓库里都会静默 exit 0，等于装了个不工作的门（安装到全局时实测发现）。
# 插件 cache 安装位置带版本号（…/cache/<marketplace>/plan-test/<version>/…），取最新一份。
# 场景：pre-push / 手工调用时 CLAUDE_PLUGIN_ROOT 没人注入，而 skill 又只以插件形式安装。
PLUGIN_CACHE_GATE="$(ls -1d "$HOME"/.claude/plugins/cache/*/plan-test/*/skills/plan-test/scripts/plan_test_gate.py 2>/dev/null | sort -V | tail -1)"
GATE=""
for cand in \
  "${CLAUDE_PLUGIN_ROOT:-}/skills/plan-test/scripts/plan_test_gate.py" \
  "skills/plan-test/scripts/plan_test_gate.py" \
  ".claude/plugins/plan-test/skills/plan-test/scripts/plan_test_gate.py" \
  "${PLAN_TEST_GATE:-}" \
  "$HOME/.claude/skills/plan-test/scripts/plan_test_gate.py" \
  "$HOME/.claude/plugins/plan-test/skills/plan-test/scripts/plan_test_gate.py" \
  "${PLUGIN_CACHE_GATE:-}"
do
  [ -n "$cand" ] && [ -f "$cand" ] && GATE="$cand" && break
done
[ -z "$GATE" ] && exit 0   # 哪里都没装 gate 脚本：不是本 hook 的管辖范围

# python 解释器：不能只看 command -v——Windows 的 WindowsApps python3 是**静默桩**
# （rc=0、零输出、不执行任何代码），选中它等于把门变成静默 no-op（2026-08-27 Windows
# 插件安装实测：失败账本被无声放行）。必须做功能探测：真解释器要能打印出 42。
PY=""
for c in python3 python; do
  p="$(command -v "$c" 2>/dev/null)" || continue
  [ -n "$p" ] || continue
  if [ "$("$p" -c 'print(42)' 2>/dev/null)" = "42" ]; then PY="$p"; break; fi
done
[ -z "$PY" ] && exit 0

PLUGIN_CACHE_SCAN="$(ls -1d "$HOME"/.claude/plugins/cache/*/plan-test/*/hooks/gate_scan.py 2>/dev/null | sort -V | tail -1)"
SCANNER=""
for cand in "$(dirname "$0")/gate_scan.py" "${CLAUDE_PLUGIN_ROOT:-}/hooks/gate_scan.py" \
            "hooks/gate_scan.py" ".claude/hooks/gate_scan.py" \
            "$HOME/.claude/hooks/gate_scan.py" "${PLUGIN_CACHE_SCAN:-}"
do
  [ -f "$cand" ] && SCANNER="$cand" && break
done
[ -z "$SCANNER" ] && exit 0

FAILED=0
FOUND=0
BRIEF=""      # 每个未闭环 run-dir 一行——永远输出
DETAIL=""     # 只有活动轮的完整诊断——可被指纹去重/断路器省略

SCAN="$("$PY" "$SCANNER" 2>/dev/null)"
LEDGERS="$(printf '%s\n' "$SCAN" | sed -n '/^LEDGERS$/,/^HALVES$/p' | sed '1d;$d')"
HALVES="$(printf '%s\n' "$SCAN" | sed -n '/^HALVES$/,/^ACTIVE$/p' | sed '1d;$d')"
ACTIVE="$(printf '%s\n' "$SCAN" | sed -n '/^ACTIVE$/,$p' | sed '1d')"

while IFS= read -r led; do
  [ -z "$led" ] && continue
  FOUND=1
  dir="$(dirname "$led")"

  # 用户已显式确认放弃这一轮（acknowledge，绑定用户批准消息 hash，写入 integrity 链）：
  # 不再阻断收尾。它**不等于通过**——该 run 从此报 RUN_ABANDONED，永远拿不到 receipt，
  # 也不可能被当成别人的继任 run。判定交给 gate，hook 不解读账本字段。
  if "$PY" "$GATE" ack-status --run-dir "$dir" >/dev/null 2>&1; then
    continue
  fi

  # fixture-only 账本不能出现在交付路径上：check-only 对它同样返回 0，
  # 只靠退出码会被"给 manifest 加一个 fixture_only 字段"整个绕过（独立审计实测）。
  if "$PY" -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1],encoding='utf-8')).get('fixture_only') else 1)" "$led" 2>/dev/null; then
    FAILED=1
    BRIEF="$BRIEF
  · $dir —— fixture-only（合成数据，跳过全部 git 校验），不能作为交付证据：真实交付请用 fixture_only=false 重新 init，确属演练请移出工作区。"
    continue
  fi

  # 未闭环的 run：只有**经 CLI 正当退役**（链自洽 + 有 retire 操作 + 继任 run 已 SHIPPABLE
  # 且覆盖本 run 的 required 场景）才放行。判定交给 gate 自己，hook 不解读账本字段——
  # 独立审计实测过：hook 自己读 retired 且放在 check-only 之前时，手写两个词就能绕过。
  if printf '%s\n' "$ACTIVE" | grep -Fxq "$led"; then
    out="$("$PY" "$GATE" finalize --run-dir "$dir" --check-only 2>&1)"
    rc=$?
    [ "$rc" -eq 0 ] && continue
    "$PY" "$GATE" retire-status --run-dir "$dir" >/dev/null 2>&1 && continue
    FAILED=1
    BRIEF="$BRIEF
  · ${dir}（活动轮，详见下方）"
    total="$(printf '%s\n' "$out" | wc -l | tr -d ' ')"
    DETAIL="$DETAIL
── 活动轮 $dir ──
$(printf '%s\n' "$out" | head -n "$MAX_LINES")"
    if [ "$total" -gt "$MAX_LINES" ]; then
      DETAIL="$DETAIL
  …… 还有 $((total - MAX_LINES)) 行；全文：$PY $GATE finalize --run-dir $dir --check-only"
    fi
  else
    # 非活动轮：一行摘要就够。要全文时代理自己去跑那条命令（附在下面的行动提示里）。
    line="$("$PY" "$GATE" summary --run-dir "$dir" 2>&1)"
    rc=$?     # 单独取退出码：不要写成 `... | head` 后再取 $?，那取到的是 head 的
    line="$(printf '%s\n' "$line" | head -n 1)"
    [ "$rc" -eq 0 ] && continue
    "$PY" "$GATE" retire-status --run-dir "$dir" >/dev/null 2>&1 && continue
    FAILED=1
    BRIEF="$BRIEF
  · $dir —— $line"
  fi
done <<EOF
$LEDGERS
EOF

while IFS= read -r mf; do
  [ -z "$mf" ] && continue
  d="$(dirname "$mf")"
  # 豁免（2026-08-04，用户确认）：manifest 已提交进 git 且本地零改动 = 从别的机器
  # 克隆/pull 下来的历史产物（账本通常没进 git），不是本会话开了一半的 run。
  # 拦它只会造成无限收尾死循环，而本会话对它既没有事实可入账、也不该擅自删仓库内容。
  # 取舍：若有人"先提交 manifest 再删账本"可借此绕过——但提交本身已留审计痕迹，
  # 且删之前账本仍会被 LEDGERS 段的 check-only 逮住。
  if git ls-files --error-unmatch "$mf" >/dev/null 2>&1 \
     && git diff --quiet HEAD -- "$mf" 2>/dev/null; then
    continue
  fi
  FOUND=1
  FAILED=1
  BRIEF="$BRIEF
  · $d —— 有 gate manifest 却没有账本：init 只开了一半，或账本被删/改名。补跑 init 并把测试事实入账，或删掉这个目录。"
done <<EOF
$HALVES
EOF

[ "$FOUND" -eq 0 ] && exit 0
[ "$FAILED" -eq 0 ] && exit 0

N_BLOCKED="$(printf '%s' "$BRIEF" | grep -c '^  · ' || true)"

# ---- 指纹去重 + 死循环断路器 -------------------------------------------------
# 旧版每次 Stop 都把同一份诊断整篇重放，成本随「历史轮数 × 回合数」线性增长，而信息量为零。
# 指纹只覆盖 BRIEF（判定结论），不覆盖 DETAIL 的行号截断，避免无意义的抖动。
STATE_DIR="${TMPDIR:-/tmp}"
# 计数器按**会话**分桶（Claude Code 把 session_id 放在 Stop hook 的 stdin JSON 里）：
# 否则上个会话攒下的次数会让新会话第一次收尾就直接放行——新会话理应至少被完整拦一次。
# stdin 不是管道时（手工执行/测试）不去读它，避免挂住。
HOOK_INPUT=""
[ -t 0 ] || HOOK_INPUT="$(cat 2>/dev/null || true)"
SESSION="$(printf '%s' "$HOOK_INPUT" \
  | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
KEY="$(printf '%s|%s' "$ROOT" "$SESSION" | { shasum 2>/dev/null || sha1sum; } | cut -c1-16)"
STATE="$STATE_DIR/plan-test-stop-gate-$KEY.state"
FP="$(printf '%s' "$BRIEF" | { shasum 2>/dev/null || sha1sum; } | cut -c1-40)"
PREV_FP=""; PREV_N=0
[ -f "$STATE" ] && { read -r PREV_FP PREV_N < "$STATE" 2>/dev/null || true; }
case "$PREV_N" in ''|*[!0-9]*) PREV_N=0 ;; esac

if [ "$FP" = "$PREV_FP" ]; then
  REPEAT=$((PREV_N + 1))
else
  REPEAT=1
fi
printf '%s %s\n' "$FP" "$REPEAT" > "$STATE" 2>/dev/null || true

if [ "$MAX_REPEATS" -gt 0 ] && [ "$REPEAT" -gt "$MAX_REPEATS" ]; then
  # 断路器：连续 MAX_REPEATS 次拦截而结论一个字没变 = 这条拦截对本会话不可行动
  # （典型：历史轮的出口是"等继任轮 SHIPPABLE"，而继任轮正是被这些噪音拖住的那个）。
  # 再拦下去只是烧 token。放行一次，但把话说清楚：账本仍然是红的，交付判定没有改变。
  # 取舍（如实说明）：这确实让"什么都不做地连按 N 次收尾"可以通过 hook。hook 从来不是
  # 防对手的那道门——账本、git diff 与 CI 才是（见 hooks/README.md「方式 B：CI」）。
  # 想要旧的"永不放行"行为：PLAN_TEST_GATE_MAX_REPEATS=0。
  {
    echo "plan-test 机器门：连续 $PREV_N 次拦截且结论无任何变化——本次放行以免死循环。"
    echo "**账本仍未闭环（$N_BLOCKED 处），交付判定没有改变**；请把下列各项如实告知用户并请其决定："
    echo "$BRIEF"
    echo ""
    echo "用户确认放弃某一轮后，用它退出阻断（会写进账本，该 run 从此不可能产出 receipt）："
    echo "  $PY $GATE acknowledge --run-dir <run-dir> --reason \"<用户为什么放弃>\" --approval-hash <用户批准原话的 sha256>"
  } >&2
  exit 0
fi

{
  echo "plan-test 机器门未通过：存在 gate 记账物但预检 FAIL，不能收尾（$N_BLOCKED 处未闭环）。"
  echo "$BRIEF"
  if [ "$FP" = "$PREV_FP" ]; then
    echo ""
    echo "（与上次检查结论完全一致，已省略重复诊断正文；要看全文就跑上面那条 --check-only 命令）"
  elif [ -n "$DETAIL" ]; then
    echo "$DETAIL"
  fi
  echo ""
  echo "怎么处理："
  echo "  1) 活动轮：按诊断补测/补证据，重跑 finalize --check-only。"
  echo "  2) **不要拿 record-run --result blocked 当逃生口**：blocked 只是「此刻做不到」，"
  echo "     它会让该场景一直是 BLOCKED 直到你**真的补上一条 root pass**——临时受阻（例如"
  echo "     需要用户本人输密码/授权）请保持 NOT_RUN，把阻塞原因写进证据，并升级给用户。"
  echo "  3) 历史轮：正当出口是 retire --superseded-by <已 SHIPPABLE 的继任轮>；继任轮还没跑完时，"
  echo "     请用户拍板后用 acknowledge 显式放弃（需绑定用户批准原话的 sha256）。"
} >&2
exit 2
