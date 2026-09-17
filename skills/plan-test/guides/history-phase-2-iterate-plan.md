# phase-2-iterate-plan 病根与历史（冷路径）

- 重点论挑战范围：火力集中在主要矛盾；gate 曾强制每轮重审全部 finding，与"次要部分 primary 覆盖一次即收"冲突，后加 `contradiction_role: secondary` 机器兑现（见 `gate/PROTOCOL.md`）。
- 增量补丁挑战口径（primary + closure 各一轮，决定性 AC 只回归）于 2026-09-17 新增。
- 记账分档：反对文牍主义——LEAN 不启用 gate 记账，人判 3/5/8 出口。
- 行为契约冻结（P0）：防"单入口"被扩张成"单 Session"式语义跳跃。acceptance 事实源写错，后面 100% 只会更稳定地做错。
- oracle 先于实现（P0）：防测试被反转成验证错误行为——"照着实现写测试"会把 bug 测成预期行为；"看起来只是重写文案"不得自动放行。
- 真架构问题：挑战者提示词已加入"这是真架构问题吗、plan 是不是在用补丁绕过它"质疑项；判定要求全部命中，防止把一切都当架构问题去过度重写；范围闸兼顾防过度重构与用户知情权。主要矛盾常常就是真架构问题本身（`methods/research-method.md`）。
- Minimality 与正确性挑战分轮：前者删冗余、后者找遗漏，混跑会互相制造 finding。
- 大仓基线 runner：DeskPet 实测单条全量命令 15 分钟静默无终态，只能手工找 PID 精确终止，故强制 `baseline_runner.py` 分片。
- 收敛判据"不打无把握之仗"：防开工后靠 A2 回炉兜底。
