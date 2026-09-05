<!-- plan-status: finalized -->
# Plan：交付切片驱动执行

当前源基线5a9fab4；活跃安装c52f4ab，技能内容相同。按用户本轮明确授权实施本地优化，无远程发布。

## 现状与选择
skills/plan-test/phase-1-plan.md:30将任务作为拆分单位；phase-3:42每任务一个commit；config:247仅体量超限时明确切片。选择新增一个共享references/delivery-slices.md定义切片，阶段就地移除冲突，不新增门/状态机。整体验收不缩水，未来任务细节可延迟，但整体成败假设必须先验证。
最佳实践依据当前skill-creator的意图保持、按风险具体化、渐进披露及独立前向测试；适用于Markdown编排，不需要引入新框架。

## 本次交付切片 SL-1（本次优化为一个完整切面）
| 字段 | 内容 |
|---|---|
| 能力/AC | Agent能按可交付能力计划并逐片验收；覆盖AC-1至5 |
| 入口 | plan-test / plan-bs / plan-task三个技能入口 |
| 验证 | 冷启动Agent形成计划并真实交付首片；额外决策场景检查边界 |
| 依赖/边界 | 复用注意力规则及gate，不改gate脚本/schema，不远程发布 |
| 保留 | 原批准范围、冻结oracle、停止边界、真实证据要求 |

## 技术任务
1. 增加delivery-slices共享reference及三入口接入；phase-1模板改三层结构（AC-1/2）。
2. phase-2范围化收敛与challenger切片质询；phase-3逐片执行提交；phase-4/final明确片与整体验收区别（AC-2/3/4）。
3. config同步体量上限、执行单位和当前片假设规则；审计提示词范围化，独立审阅并修正冲突（AC-5）。
4. 冻结3类行为oracle，先真实首片价值smoke，再结构与现有回归；本仓AGENTS要求gate run，独立full-audit后finalize。本地提交，验证后同步当前安装的本次技能文件（全AC）。

## 调研、假设和授权
本次技能行为需真实Agent回放验证，字面检查不足。整体架构/重大风险规则及机器gate边界由独立review检查；可用性未知不能提前写PASS。用户已批准六项方案，不重复索取同一目标的批准；任何扩范围/发布仍需对应授权。
单切片多个文件必须协同更新才能可用，无额外实现worktree。独立调查/审阅/回放使用子代理，执行文件编辑由主Agent串行完成。
评测模型继承当前会话；配置默认异构引擎不可用，明确为同模型独立上下文评测，不声称跨模型稳定性。

## 专项补充：范围与账本对应（关闭 slice-scope-authority-unspecified）
新reference明确开账前选择：同一run中间片保留原required/未来NOT_RUN，片里程碑不要求整体READY/finalize；各片独立run保留global AC映射与继承风险，本片acceptance/oracle准备好后先compile/init再机器challenge，全部实现前完成；已冻结范围不能擅改。phase4出口与final收尾分别明确中间里程碑/独立run/整体完成。三入口准入不只看program finalized，还核当前片就绪。真实CLI首片完成后按用户停止要求停止，边界回放涵盖整体frozen run未接API时不准宣布片完成。
