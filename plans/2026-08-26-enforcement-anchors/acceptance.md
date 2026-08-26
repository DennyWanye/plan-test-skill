# Acceptance — 强制层三锚点 + stats/遥测（commit 147980c 的验证闭环）

> 范围：2026-08-26 handoff T2/T3/T4/T6 落进本仓库的改动（pre-push 适配器、tier_check、
> stats 子命令、phase 遥测与开销表、插件化 hook 路径解析）。本 run 是对已提交实现的
> LEAN 档验证闭环，同日补账；实现内容见 commit 147980c。
> 判档依据：改的是门禁自身（高风险面），但改动全部为纯新增（git diff 无删改 hunk）、
> 可由自测套件完全回归 → LEAN，不走 FULL 的挑战循环。

- **AC-1（MUST）**：gate 自测套件 `test_plan_test_gate.py`（215 用例）全绿——存量门禁行为零回归。
- **AC-2（MUST）**：`stats` 子命令按诊断码统计全部 run 账本、零触发列全史清单、窗口不足不出退休结论（`test_gate_stats.py` 全绿）。
- **AC-3（MUST）**：`tier_check.py` 高风险改动面反查——命中 glob 无账本红、同 diff 带账本绿、`**`/`*` 语义与 merge-base 口径正确（`test_tier_check.py` 全绿）。
- **AC-4（MUST）**：`phase-end --subagents/--rounds` 遥测入账 + `render` 尾部开销表（`test_phase_cost.py` 全绿）。
- **AC-5（MUST）**：pre-push 适配器端到端——真实 `git push` 路径上失败账本拦、fixture_only 直查拦、干净仓库放行（`scripts/e2e-pre-push.sh`，自包含临时仓库）。
- **AC-6（MUST）**：Stop hook 端到端——失败账本 exit 2 并输出诊断、无记账物仓库 exit 0 放行（`scripts/e2e-stop-hook.sh`，自包含临时仓库）。
