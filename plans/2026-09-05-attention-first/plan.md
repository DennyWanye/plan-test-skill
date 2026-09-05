<!-- plan-status: finalized -->
# Plan：先调研再决策，授权内自主交付

## 范围依据
见同目录 acceptance.md；用户当前请求已授权这次本地优化。无需再批准同一目标。当前基线 33c297f0303262b4d4bf215890bfa12f4c3046e4，两个本地 checkout 一致且干净。

## 调查与选择
主要矛盾是 Agent 反复把流程责任交回用户。关键调用链是三个 SKILL.md → phase-A → phase-1/2 → phase-3 A2 → phase-final。现有 config 的 EXECUTE_AUTONOMY 只覆盖执行分歧，phase-A 强制逐句批准，plan-bs 先选择方案后调查，phase-3 A2 又要求重新批准。共享规则缺位导致冲突。
选择一个短共享 references/user-attention.md 作为交互语义来源，入口必读，并直接移除相冲突的阶段要求。保留风险与证据门。相比只加“少打扰”口号，此方案改变实际分支；相比新增交互状态机/validator，不增加运行成本。
本次最佳实践依据本机 skill-creator/SKILL.md：只保留改变决策的指导、保留意图与范围、按风险细化、渐进披露、用独立行为测试验证。适配于当前 Markdown 编排，不引入新系统。

## 任务与 oracle
1. AC-1：读取备份 README 与 raw/text logs，形成 analysis.md，事件按时间标版本，原始用户话与代理输出分开，不以提示词出现次数代表中断次数。
2. AC-2/3/4：新增共享注意力 reference，并修改 config、三个入口、phase-A/1/2/3。清楚规定权限延续、plan 合并 review、范围内回炉、决策简报与未答复的依赖隔离。最小价值 smoke 是隔离样例自主修复。
3. AC-5：调整 phase-4/final、research-method 的相关引用和恢复说明；不变更门禁机器语义。完成独立挑战闭环与冷启动行为测试；结构验证和现有回归确认无破坏。
4. 全 AC：本仓 AGENTS.md 要求行为性变更有 gate 验证 run。用现有 CLI 记录真实测试和独立审计，限定本地提交，finalize 后同步本地活跃安装（仅本次技能文件），核验一致性。

## 关键假设与验证
本次无第三方 API 运行假设。核心未验证假设是新规则能改变冷启动 Agent 的动作选择，必须通过实际行为回放验证，文字检查不足以替代。
规则解释成本用少量代表场景检验，长期用户注意力改善需后续真实 run 观察，不能从一次回放宣称百分比下降。

## Complexity inventory
仅新增一个共享 reference；复用已有 gate/test runner，不新增运行时协议、诊断码或交互计数器。分析与测试证据沿用 plans 目录。

## 交互边界
允许范围内技术选择、调研、修复、局部计划修订和重测。若需改变用户目标、缩减 AC、付费或生产操作，先形成决策简报；不以本次“节省注意力”要求推导额外权限。demo 与进度报告不产生新等待点。

## 挑战与验证说明
Primary未发现范围内P0/P1；实现review发现plan-task缺矩阵强制重复确认，已修复并独立复核闭环，见closure-review*.json。行为评测见verification/run-001产物；最终状态只取该run的finalize。当前环境不提供配置默认的claude/opus引擎，使用继承当前模型的独立冷启动Agent，明确记录为同模型独立上下文，不声称跨模型审计。
