# phase-1-plan.md 瘦身移出的病根与说明（SL-3 W2a）

- 调查步骤原为"原架构基线阶段"，已并入 phase-1：调查为写 plan 服务，不产出独立 ARCHITECTURE.md；项目自己维护架构文档的，收尾时顺手更新（见 phase-final）。
- 生产接缝病根：s5b 调查给全了 file:line，却从没让生产入口推过这条链，9 个既有缺陷全留到验收才爆（config `VALUE_SMOKE_GATE`）。规则正文归入 RULES R4：主要矛盾 spike 从用户实际入口（CLI / HTTP / WS / UI 通道）进入，经真实装配跑到业务终态；"现状调查"结论只能停在"端到端可驱动"，不能停在"组件存在"。
- 关键假设举例：三方库/API 真实能力、LLM 输出契约、数据源真实形态、性能可达性、关键链路运行时行为；spike 要用真实调用/真实数据/真实 provider，命令 + 实际输出记入 plan"关键假设与实践证据"节。
- `SELF_BUILT_DEFENSE: forbidden` 同样适用于 spike（RULES R14）；`BEHAVIOR_POLICY = preserve-approved` 内部实现可删可换可重构（RULES R13）。
- 原 plan.md 模板的 Markdown 表格形式压成"plan.md 各节"清单；Task 字段：覆盖 AC / 改动文件 / 现状 / 修改方式 / 验证（oracle 先于实现，RULES R3）/ 依赖。
