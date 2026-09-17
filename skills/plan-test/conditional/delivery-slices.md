# 切片条件细则（按命中条件读）

## OPS
- OPS 继续使用原运维路径，按目标服务状态分阶段，不强套代码提交模板。

## 体量超限
- 超 `RELEASE_UNIT_LIMITS` → BLOCKED，升级用户附拆分建议：拆 program plan + 垂直 slice，每个 slice 独立验收；不删 AC、不合并任务、不降级 MUST、不压缩数字、不隐藏全局风险。
- program 总览关联各独立交付片的执行 plan；总览保留全 AC 映射。
- 体量机检按实际 release unit：同一 run 内分片不缩小原 run 的计数或阈值；独立片 run 才按该片完整范围计数。

## program 多片
- 单片 `plan.md` 可沿用 finalized 标记；多片 program 的总体方案定稿不代表未来片已具备开工条件，以 plan 内明确的当前片和开工检查为准。
- 先确定验收范围与 run 的对应关系，不能执行到一半随意切换。
- **同一交付 run 内分片**：该 run 的 acceptance/contract、required 场景仍覆盖原声明范围；每片在原账本追加真实结果，未来项保留 NOT_RUN。片能力验收、适用 review、回归与提交身份核对后，记"SL-x 里程碑通过，整体未完成"并推进下片；此时不要求整个 run 的 READY_FOR_AUDIT/finalize，也不产生片 receipt；phase-4/final 的整体条件等全部 required 及组合验证完成后执行。既有整体 frozen run 默认沿此路径继续，不通过改 required/重开 run 适配新规则。
- **各片独立交付 run**：适用于需独立交付或超体量上限的 program，在开账前选定。总览保留全部原始 AC 和依赖；每片执行 plan + slice acceptance/contract 映射原始请求、本片断言及继承的全局风险。本片验收与 oracle 就绪后，机器门路径先按 `references/evidence-audit-lifecycle.md` compile/init，再按 phase-2 start-challenge-loop 完成挑战、关键假设验证与定稿，全部在实现前完成；冻结后需改 contract/oracle 走原机制。该片适用的审计/finalize 成功才算该片独立交付。未来片不提前伪造冻结 oracle，开工前同样完成准备。已冻结 run 的 scope/contract 变化仍按原批准机制，不可用新片丢弃旧义务。
- slice acceptance 说明原需求中本片的断言与外部约束；不能反写或削减整体 acceptance、降低继承的风险边界，既有冻结 contract 不静默改写。
- **无机器门的路径**：以同样明确的片承诺和全局映射记 journal，不为每片新增 ledger/receipt。是否使用机器门取决于实际风险及项目要求，不能用片数决定或降级。
