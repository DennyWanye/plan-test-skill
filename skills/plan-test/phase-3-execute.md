# Phase 3 — 并行执行 + 完成度审计

**目的**：按定稿 plan 实现代码，并审计到 100% 完成、无回归。

## A. 并行执行

1. 用 `{EXECUTOR_ENGINE}` 子代理**并行**完成 plan 中相互独立的任务（默认 codex-gpt5.5；未装则回退 claude）。
   - 有依赖的任务按依赖顺序；独立任务并行派发。
   - 多代理并行写文件时用 git worktree 隔离，避免冲突。
2. `EXECUTE_AUTONOMY = high`：遇分歧按最佳实践自决，不打断用户（BLOCKED 例外）。
3. `FEATURE_POLICY = only-add`：不少做。
4. 频繁提交（每个任务一个 commit），保留可回滚点。
5. **与本机 hook 共处**（用户环境常挂 PostToolUse 类型检查 hook，每次编辑后自动跑 tsc/analyze）：
   - **编辑一次成型**：同一任务对同一文件的改动合并为一次 Edit/Write，别用多次小编辑逐步逼近——每次编辑都会触发一轮类型检查，碎片化编辑等于把最贵的检查跑 N 遍。
   - hook 报的类型错误**当场修**，不许攒到阶段门禁再统一处理（hook 会反复对同一批错误报警，越攒越贵）。
   - hook 拦截了某个操作 → 视为用户意图，改走别的路或标记 BLOCKED，不许绕过。

## B. 完成度审计（循环至 100%）

1. 派 `{AUDITOR_ENGINE}` 子代理，用 `prompts/completion-auditor.md` 评估完成度。
   - 审计走**可追溯矩阵**：`{ACCEPTANCE_FILE}` 的每条 AC ↔ plan 任务 ↔ 实际代码改动，逐条核对有无断点。
   - 按 SKILL.md"上下文包"规则派发：附 acceptance.md 原文、plan 任务清单、本次改动文件列表（git diff --stat）；复审轮附上一轮的缺口清单，声明**只需复核上轮缺口与新改动**，已确认 ✅ 的条目免重查。
2. 以输出末行 `VERDICT` 判定：FAIL（不足 100%）→ 补完缺口 → 再次审计（`AUDIT_RETRY = until-100`）；缺结论行按 FAIL 处理。
3. 超过 `{MAX_ROUNDS}` 仍到不了 100% → 标记 BLOCKED，列出始终无法完成的条款与原因，升级。

## C. 回归门（不破坏既有）

- 对照 phase-2 的 `baseline.md`：现有构建/测试/lint/类型检查必须回到**不低于基线**的状态。
- 本次新引入的红，必须修复后才算本阶段通过。

## 出口

- 完成度审计 100% + 无新增回归 → 进入 phase-4 阶段门禁。
