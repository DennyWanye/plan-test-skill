# 交接点清单（`HANDOFF_MAP`）

本清单列出 plan-test / plan-task / plan-bs 三个入口及其共享文档里**所有会向用户发出消息的位置**，作为给 `checklists/handoff.md` 接线（在原文处加指针）的依据，接线完成后它同时是验收核对表。
**为什么用锚点句而不是行号**：这些文档会被重排、插入小节、改写措辞，行号当天就失效；锚点句是原文片段，改写时会一起被改，失配即提示该位置需要重新定位。
**怎么核对**：对每行执行 `grep -nF "<锚点句>" <文件>`——命中恰好 1 次 = 位置仍在；命中 0 次 = 原文已改，重新定位并更新本表；命中多次 = 锚点需要加长。
**评估模式**按 `checklists/handoff.md` 的三档表判：让用户动手（点/跑/看 demo 判断）或宣布完成 → 完整；只请用户表态或停下等用户 → 轻量；纯进度汇报、开放式澄清 → 自查。
**指针状态**：`已加指针` = 该位置原文已引用 `checklists/handoff.md`/`HANDOFF_CHECK`；`由三入口四问触发覆盖` = 未加就地指针，靠三个 SKILL.md 开场的四问兜住。

| 文件 | 锚点句 | 类型 | 评估模式 | 指针状态 |
|---|---|---|---|---|
| plan-test/SKILL.md | demo 给用户 + 矛盾转化再分析 | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/SKILL.md | 回到用户中检验（demo） | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/SKILL.md | 进度用用户语言汇报、以原始 plan 总进度表开头 | 进度汇报 | 自查 | 已加指针 |
| plan-test/SKILL.md | 要用户拍板的事攒成一批附默认建议一次问完 | 决策批次 | 轻量 | 已加指针 |
| plan-test/SKILL.md | 把验收标准、plan 与决策简报合并一次提交 | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 用户要求先确认或方案超出授权 → 等待对应决定 | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 异步 demo，再细化下一片 | demo/里程碑展示 | 完整 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 片内与整体状态分别报告 | 进度汇报 | 自查 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 测不了就 BLOCKED 升级 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 卡在哪/试过什么/需要什么解锁 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖 |
| plan-task/SKILL.md | 不许拿 plan 反推验收标准凑数 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-task/SKILL.md | 按共享规则准备决策简报/原批准机制 | 请用户拍板 | 轻量 | 已加指针 |
| plan-task/SKILL.md | 什么都找不到 → 停下，提示用户先跑 | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-task/SKILL.md | 基线本身是红的要先如实告知用户 | 基线是红的告知 | 轻量 | 由三入口四问触发覆盖 |
| plan-task/SKILL.md | 异步 demo 给用户（不自动等待确认） | demo/里程碑展示 | 完整 | 已加指针 |
| plan-task/SKILL.md | 一句用户语言汇报，以原始 plan 总进度表开头 | 进度汇报 | 自查 | 已加指针 |
| plan-task/SKILL.md | 要用户拍板的事攒成一批附默认建议一次问完 | 决策批次 | 轻量 | 已加指针 |
| plan-task/SKILL.md | 完成判定 = DoD 清单全绿（每条附证据位置） | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-task/SKILL.md | 交付措辞用 receipt 模板 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-task/SKILL.md | 任何 DoD 项达不成 → BLOCKED 升级 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-task/SKILL.md | 测不了就 BLOCKED 升级，不许静默换等价方案 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-task/SKILL.md | 不得宣布 complete | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-task/SKILL.md | 不许边挂着已知 BLOCKER 边收尾 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-task/SKILL.md | 这是已知失败版本、目的是复现/补证、非验收版本 | 已知失败版本启动告知 | 完整 | 已加指针 |
| plan-task/SKILL.md | 缩小测试范围必须用户显式批准 | 请用户拍板 | 轻量 | 已加指针 |
| plan-task/SKILL.md | 全绿，不得写成原范围全绿 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-task/SKILL.md | 超限 → BLOCKED 升级 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-task/SKILL.md | 实际需要用户解锁时先给决策简报 | 请用户拍板 | 轻量 | 已加指针 |
| plan-bs/SKILL.md | 每轮只问当前真正缺失的 1–2 个问题 | 开放式澄清 | 自查 | 已加指针 |
| plan-bs/SKILL.md | 再用决策简报展示可行方向、推荐及代价 | 请用户拍板 | 轻量 | 已加指针 |
| plan-bs/SKILL.md | 用户明显没想清楚的地方，用具体例子帮他想 | 开放式澄清 | 自查 | 已加指针 |
| plan-bs/SKILL.md | 尚不明确的目标先问最小问题 | 请用户拍板 | 轻量 | 已加指针 |
| plan-bs/SKILL.md | 确需改变目标/行为再提交决策简报 | 请用户拍板 | 轻量 | 已加指针 |
| plan-bs/SKILL.md | 必要时回步骤 1 和用户重新讨论方向 | 停下等用户 | 轻量 | 已加指针 |
| plan-bs/SKILL.md | 把验收标准与定稿 plan 一起给用户 review | 定稿/合并 review | 轻量 | 已加指针 |
| plan-bs/SKILL.md | 收尾输出（交接消息，完整评估） | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-A-acceptance.md | 这是少数允许打断用户的时刻 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/phase-A-acceptance.md | 纳入 plan 的合并 review，不单独逐句索取批准 | 定稿/合并 review | 轻量 | 已加指针 |
| plan-test/phase-A-acceptance.md | 作为选项提给用户，不得自行删减需求 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/phase-A-acceptance.md | 可信边界变化必须用户明确确认 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/phase-A-acceptance.md | 真实意图缺失才问最小问题 | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-A-acceptance.md | 实现前按合并 review/已有授权核对定稿 | 定稿/合并 review | 轻量 | 已加指针 |
| plan-test/phase-A-acceptance.md | 标记 BLOCKED，说明缺哪条信息 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/phase-1-plan.md | 完成决策所需的定向调查，再提问 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-1-plan.md | 附决策简报升级，不硬写 plan | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-1-plan.md | 必要时回 phase-A 和用户重新讨论方向 | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 核对已有授权或完成合并 review | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 确需跳过时必须取得用户明确批准 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 需要用户决定时进入合并 review | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 向用户报告原因 / 当前 loop 阻断 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 需要改变 profile/scope/trusted boundary | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 标记 BLOCKED 升级给用户拍板 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 将未获授权的重要行为变化纳入一次 plan review | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | frozen oracle 必须走上述批准 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/phase-2-iterate-plan.md | 用户可见行为变化仅带入 review 作为选项 | 定稿/合并 review | 轻量 | 已加指针 |
| plan-test/phase-2-iterate-plan.md | 向用户一起展示 acceptance、行为差异 | 定稿/合并 review | 轻量 | 已加指针 |
| plan-test/phase-2-iterate-plan.md | 当前哪些已经是坏的，区分 | 基线是红的告知 | 轻量 | 已加指针 |
| plan-test/phase-3-execute.md | 超限 → BLOCKED，升级给用户附拆分建议 | 体量超限升级 | 轻量 | 已加指针 |
| plan-test/phase-3-execute.md | 立即回炉（A2）或 BLOCKED | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/phase-3-execute.md | 把跑起来的实物给用户看一眼 | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/phase-3-execute.md | 配一句用户语言的进度汇报 | 进度汇报 | 自查 | 已加指针 |
| plan-test/phase-3-execute.md | 攒成一批、附默认建议一次问完 | 决策批次 | 轻量 | 已加指针 |
| plan-test/phase-3-execute.md | 测试失败只有两条路： | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/phase-3-execute.md | 附定向调研与决策简报升级 | A2 回炉升级 | 轻量 | 已加指针 |
| plan-test/phase-3-execute.md | 缺结论行按 FAIL 处理 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 只有实际解锁需要用户时 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 立即 BLOCKED 早停，不进任何昂贵步骤 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 已知 BLOCKER 还继续收尾 = 谎报进度 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 任何 required 测试无法执行（环境受阻、设备缺失） | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 该消息发出前按 `checklists/handoff.md` 走**轻量评估** | 决策批次 | 轻量 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 全 AI 驾驶须用户批准 | 叫用户验收/测试 | 完整 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 的 DoD 清单；交付说明如实写 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 不声称 receipt 或整体完成 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖 |
| plan-test/phase-final-dod.md | 任何一条附不上证据 → BLOCKED 升级 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-final-dod.md | 宣布完成前回看兑现表 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-final-dod.md | 推荐出口和需要的最小用户动作 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/phase-final-dod.md | 局部 PASS 必须标注作用域 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-final-dod.md | 这是已知失败版本、启动目的是复现/补证据 | 已知失败版本启动告知 | 完整 | 已加指针 |
| plan-test/phase-final-dod.md | 默认路径交付措辞：如实写明 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-final-dod.md | 最终总结：做了什么、主要矛盾如何被验证 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/config.md | 不得使用 receipt/SHIP 措辞 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/config.md | 或用户在 chat 显式批准跳过 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/config.md | 门禁与 DoD 一律 FAIL/BLOCKED | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/config.md | 失败 → 立即 BLOCKED 早停，不继续投入昂贵收尾 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/config.md | 在报告里 BLOCKED 升级 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/config.md | 不可撤销，须用户显式拍板 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/config.md | 输入语义敏感 + required UI 场景全 AI 驾驶时 | 叫用户验收/测试 | 完整 | 已加指针 |
| plan-test/config.md | 不得将沉默视为批准、扩大已授权范围 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/config.md | 每项按 `checklists/handoff.md` H3 三段写 | 决策批次 | 轻量 | 已加指针 |
| plan-test/config.md | 汇报结果、下一验证点和是否需要用户 | 进度汇报 | 自查 | 已加指针 |
| plan-test/config.md | 用户可感知的标的/行为差异必须复述确认 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 展示简短方案摘要后直接执行 | 进度汇报 | 自查 | 已加指针 |
| plan-test/references/user-attention.md | 合并为一次 review，明确停在实现之前 | 定稿/合并 review | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 只问尚未明确的目标/价值取舍 | 开放式澄清 | 自查 | 已加指针 |
| plan-test/references/user-attention.md | 按该边界保存现状与未完成项 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 以下情况才产生用户决策 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 决策简报的**格式与判据唯一出处是 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 不相关的重要问题尽可能合并在一次 review | 决策批次 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 明确说明卡点，结束本轮等待答复 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 附已试方法、结果、推荐出口和最小用户动作 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | 里程碑展示实物与结果 | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/references/user-attention.md | 已完成什么 / 现在验证什么 / 是否需要你 | 进度汇报 | 自查 | 已加指针 |
| plan-test/references/user-attention.md | 只说明影响结果的门与实际限制 | 进度汇报 | 自查 | 已加指针 |
| plan-test/references/delivery-slices.md | 提交/构建身份及限制，异步展示实物 | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/references/delivery-slices.md | 用户要求暂停/验收或实际越出授权时 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/references/delivery-slices.md | SL-x 里程碑通过，整体未完成 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/references/delivery-slices.md | SL-1 验收通过，整体尚有 SL-2/3 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/methods/research-method.md | 缺失的是用户目标或权限时直接说明缺口 | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/methods/research-method.md | 交用户拍板，不闷头自决 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/checklists/manual-test-mcp.md | 由用户亲自补测至少 1 个核心场景 | 叫用户验收/测试 | 完整 | 已加指针 |

## 统计（共 110 个交接点，随接线同步更新）

### 按类型

| 类型 | 条数 |
|---|---|
| 请用户拍板 | 21 |
| 宣布完成/交付措辞 | 18 |
| BLOCKED 升级 | 16 |
| 停下等用户 | 12 |
| 定稿/合并 review | 10 |
| 进度汇报 | 8 |
| demo/里程碑展示 | 7 |
| 决策批次 | 6 |
| 开放式澄清 | 3 |
| 叫用户验收/测试 | 3 |
| 基线是红的告知 | 2 |
| 已知失败版本启动告知 | 2 |
| 体量超限升级 | 1 |
| A2 回炉升级 | 1 |
| **合计** | 110 |

### 按评估模式

| 评估模式 | 条数 |
|---|---|
| 轻量 | 69 |
| 完整 | 30 |
| 自查 | 11 |
| **合计** | 110 |
