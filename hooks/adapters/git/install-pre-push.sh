#!/usr/bin/env bash
# 把 plan-test pre-push 适配器装进目标仓库。
#
# 用法：install-pre-push.sh [目标仓库路径]   （缺省 = 当前目录）
#
# 行为：
#   - 尊重 core.hooksPath（配了就装那里，没配装 .git/hooks/，worktree 用 git rev-parse
#     --git-path hooks 解析，别硬拼路径）；
#   - gate_scan.py 复制到钩子同目录（pre-push 的第一个扫描器候选就是 dirname $0）；
#   - 已存在**非本适配器**的 pre-push 时拒绝覆盖——串接是使用者的决定，不替人做。
#
# 安装前请先确认目标仓库全部账本能过 finalize --check-only（或已 retire/acknowledge），
# 否则装上即堵死自己的 push（handoff 风险 R1）。

set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-.}"

cd "$TARGET"
git rev-parse --git-dir >/dev/null 2>&1 || { echo "不是 git 仓库：$TARGET" >&2; exit 2; }

HOOKS_DIR="$(git config core.hooksPath 2>/dev/null || true)"
if [ -n "$HOOKS_DIR" ]; then
  # 相对的 hooksPath 按仓库顶层解析（git 的语义如此）
  case "$HOOKS_DIR" in
    /*) : ;;
    *) HOOKS_DIR="$(git rev-parse --show-toplevel)/$HOOKS_DIR" ;;
  esac
else
  HOOKS_DIR="$(git rev-parse --git-path hooks)"
fi
mkdir -p "$HOOKS_DIR"

if [ -f "$HOOKS_DIR/pre-push" ] && ! grep -q "plan-test git pre-push" "$HOOKS_DIR/pre-push"; then
  echo "已存在别的 pre-push 钩子，拒绝覆盖：$HOOKS_DIR/pre-push" >&2
  echo "请自行决定串接方式后重试。" >&2
  exit 3
fi

cp "$SRC_DIR/pre-push" "$HOOKS_DIR/pre-push"
cp "$SRC_DIR/../../gate_scan.py" "$HOOKS_DIR/gate_scan.py"
chmod +x "$HOOKS_DIR/pre-push"

echo "已安装：$HOOKS_DIR/pre-push（gate_scan.py 同目录）"
echo "验证（不真推）：git push --dry-run"
