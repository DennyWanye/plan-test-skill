# 交接点清单（`HANDOFF_MAP`）

本清单列出 plan-test / plan-task / plan-bs 三个入口及其共享文档里**所有会向用户发出消息的位置**，作为给 `checklists/handoff.md` 接线（在原文处加指针）的依据，接线完成后它同时是验收核对表。
**为什么用锚点句而不是行号**：这些文档会被重排、插入小节、改写措辞，行号当天就失效；锚点句是原文片段，改写时会一起被改，失配即提示该位置需要重新定位。
**怎么核对**：对每行执行 `grep -nF "<锚点句>" <文件>`——命中恰好 1 次 = 位置仍在；命中 0 次 = 原文已改，重新定位并更新本表；命中多次 = 锚点需要加长。
**评估模式**按 `checklists/handoff.md` 的三档表判：让用户动手（点/跑/看 demo 判断）或宣布完成 → 完整；只请用户表态或停下等用户 → 轻量；纯进度汇报、开放式澄清 → 自查。
**指针状态**：`已加指针` = 该位置原文已引用 `checklists/handoff.md`/`HANDOFF_CHECK`；`由三入口四问触发覆盖` = 未加就地指针，靠三个 SKILL.md 开场的四问兜住。

v0.9.0 SL-3 重排后按新文本重定位（2026-09-17）。

| 文件 | 锚点句 | 类型 | 评估模式 | 指针状态 |
|---|---|---|---|---|
| plan-test/phase-3-execute.md | 把跑起来的实物给用户看一眼 | demo/里程碑展示 | 完整 | 已合并：见 plan-test/phase-3-execute.md 把跑起来的实物给用户看一眼 |
| plan-test/phase-3-execute.md | 把跑起来的实物给用户看一眼 | demo/里程碑展示 | 完整 | 已合并：见 plan-test/phase-3-execute.md 把跑起来的实物给用户看一眼 |
| plan-test/RULES.md | 先总进度表，用户语言 | 进度汇报 | 自查 | 已加指针（SL-3 语义核对后补回） |
| plan-test/RULES.md | 攒批编号，`checklists/handoff.md` H3 | 决策批次 | 轻量 | 已合并：见 plan-test/RULES.md 攒批编号，`checklists/handoff.md` H3 |
| plan-test/SKILL.md | 验收+plan+决策简报合并一次提交 | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 否则等对应决定（R11） | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 异步 demo→细化下一片 | demo/里程碑展示 | 完整 | 由三入口四问触发覆盖 |
| plan-test/SKILL.md | 片内/整体分别报告 | 进度汇报 | 自查 | 由三入口四问触发覆盖 |
| plan-test/RULES.md | 有 UI 的被测对象不省略不降级，测不了→BLOCKED | BLOCKED 升级 | 轻量 | 已合并：见 plan-test/RULES.md 有 UI 的被测对象不省略不降级，测不了→BLOCKED |
| plan-test/RULES.md | 附已试/结果/推荐出口/最小用户动作 | BLOCKED 升级 | 轻量 | 已合并：见 plan-test/RULES.md 附已试/结果/推荐出口/最小用户动作 |
| plan-task/SKILL.md | 不许拿 plan 反推验收标准凑数 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-task/SKILL.md | 否则走决策简报/原批准机制 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-task/SKILL.md | 都找不到→停下，提示先跑 | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-task/SKILL.md | 基线本身是红的要先如实告知用户 | 基线是红的告知 | 轻量 | 由三入口四问触发覆盖 |
| plan-task/SKILL.md | 里程碑 PASS 后异步 demo+矛盾再分析 | demo/里程碑展示 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/RULES.md | 先总进度表，用户语言 | 进度汇报 | 自查 | 已加指针（SL-3 语义核对后补回） |
| plan-test/RULES.md | 攒批编号，`checklists/handoff.md` H3 | 决策批次 | 轻量 | 已合并：见 plan-test/RULES.md 攒批编号，`checklists/handoff.md` H3 |
| plan-task/SKILL.md | 文档回写→DoD 逐条证据 | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/full/phase-final-dod.md | FULL 路径用 receipt 模板 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-task/SKILL.md | DoD 达不成→BLOCKED，不谎报完成 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/RULES.md | 等价方案须用户批准并表注 | BLOCKED 升级 | 轻量 | 已合并：见 plan-test/RULES.md 等价方案须用户批准并表注 |
| plan-test/conditional/config.md | `MANUAL_REQUIRED_PENDING_POLICY`: block | 宣布完成/交付措辞 | 完整 | 已合并：见 plan-test/conditional/config.md `MANUAL_REQUIRED_PENDING_POLICY`: block |
| plan-test/phase-4-stage-gate.md | 已知 BLOCKER 还继续收尾 = 谎报进度 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-task/SKILL.md | 已知失败版本启动警告 | 已知失败版本启动告知 | 完整 | 已加指针 |
| plan-test/RULES.md | 缩测试范围须用户批准 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/RULES.md | 批准缩减后回写范围节 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/RULES.md | DoD 缺证据、循环超限 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-3-execute.md | 附定向调研与决策简报升级 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-bs/SKILL.md | 每轮只问真正缺失的 1–2 个问题 | 开放式澄清 | 自查 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-bs/SKILL.md | 再用决策简报给方向、推荐及代价 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-bs/SKILL.md | 没想清楚处用例子帮他想 | 开放式澄清 | 自查 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-bs/SKILL.md | 不明确的目标先问最小问题 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-bs/SKILL.md | 确需改目标/行为才决策简报 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-bs/SKILL.md | 假设不成立→方案层面改（必要时回步骤 1） | 停下等用户 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-bs/SKILL.md | 验收与 plan 一起给，已确认项不再问 | 定稿/合并 review | 轻量 | 已加指针 |
| plan-bs/SKILL.md | 收尾输出（交接消息，完整评估） | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/phase-A-acceptance.md | 少数允许打断用户的时刻 | 停下等用户 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-A-acceptance.md | 纳入 plan 的合并 review，不单独逐句索取批准 | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-A-acceptance.md | 作为选项提给用户，不得自行删减需求 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/full/phase-A-acceptance.md | 可信边界变化必须用户明确确认 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/RULES.md | 只在意图缺失、可感知行为变化或缩 AC | 停下等用户 | 轻量 | 已合并：见 plan-test/RULES.md 只在意图缺失、可感知行为变化或缩 AC |
| plan-test/phase-A-acceptance.md | 实现前按合并 review/已有授权核对定稿 | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-A-acceptance.md | 标记 BLOCKED，说明缺哪条信息 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/phase-1-plan.md | 完成决策所需的定向调查，再提问 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-1-plan.md | 附决策简报升级，不硬写 plan | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-1-plan.md | 必要时回 phase-A 和用户重新讨论方向 | 停下等用户 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 实现前核对授权或合并 review | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/references/challenge-main-agent.md | 确需跳过须用户明确批准 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/full/phase-2-iterate-plan.md | 需要用户决定时进入合并 review | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/full/phase-2-iterate-plan.md | 向用户报告原因 / 当前 loop 阻断 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/full/phase-2-iterate-plan.md | 需要改变 profile/scope/trusted boundary | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | 标 BLOCKED 请用户拍板 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/conditional/phase-2-iterate-plan.md | 未获授权的重要行为变化纳入一次 plan review | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖 |
| plan-test/phase-2-iterate-plan.md | frozen oracle 删/反转/放宽走批准 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/challenge-main-agent.md | 用户可见行为变化仅带入 review 作为选项 | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-2-iterate-plan.md | 一并展示 acceptance、行为差异、plan、决策简报并等 | 定稿/合并 review | 轻量 | 已加指针 |
| plan-test/phase-2-iterate-plan.md | 基线已红 → 先如实告知用户 | 基线是红的告知 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-3-execute.md | 超限 → BLOCKED，升级给用户附拆分建议 | 体量超限升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-3-execute.md | 立即回炉（A2）或 BLOCKED | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-3-execute.md | 把跑起来的实物给用户看一眼 | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/phase-3-execute.md | 配一句用户语言的进度汇报 | 进度汇报 | 自查 | 已加指针 |
| plan-test/phase-3-execute.md | 攒成一批、附默认建议一次问完 | 决策批次 | 轻量 | 已加指针 |
| plan-test/phase-3-execute.md | 测试失败只有两条路： | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-3-execute.md | 附定向调研与决策简报升级 | A2 回炉升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-3-execute.md | 缺结论行按 FAIL 处理 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-4-stage-gate.md | 只有实际解锁需要用户时 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 立即 BLOCKED 早停，不进任何昂贵步骤 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-4-stage-gate.md | 已知 BLOCKER 还继续收尾 = 谎报进度 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-4-stage-gate.md | 任何 required 测试无法执行（环境受阻、设备缺失） | BLOCKED 升级 | 轻量 | 已加指针（SL-3 语义核对后补回） |
| plan-test/phase-4-stage-gate.md | 发出前按 `checklists/handoff.md` 轻量评估 | 决策批次 | 轻量 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 全 AI 驾驶须用户批准 | 叫用户验收/测试 | 完整 | 已加指针 |
| plan-test/phase-4-stage-gate.md | 完成判定 = journal + phase-final DoD | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-4-stage-gate.md | 不声称 receipt 或整体完成 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖 |
| plan-test/phase-final-dod.md | 附不上证据 → BLOCKED 升级 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-final-dod.md | UI 测试被换成审计？受阻场景未升级就替代 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-final-dod.md | 升级按 `checklists/handoff.md` H0/H3 | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/RULES.md | 局部 PASS 标作用域 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-final-dod.md | 先告知是已知失败版本 | 已知失败版本启动告知 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-final-dod.md | 交付措辞：写明"完成判定依据 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/phase-final-dod.md | 全绿总结：做了什么 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/RULES.md | 不用 receipt/SHIP 措辞 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/RULES.md | 或用户批准跳过并留痕 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/conditional/config.md | 门禁与 DoD 一律 FAIL/BLOCKED | 宣布完成/交付措辞 | 完整 | 已加指针 |
| plan-test/RULES.md | FAIL→立即 BLOCKED 或 A2 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/full/config.md | 报告里 BLOCKED 升级 | BLOCKED 升级 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/full/config.md | 不可撤销，须用户显式拍板 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖 |
| plan-test/full/config.md | 输入语义敏感 + required UI 场景全 AI 驾驶时 | 叫用户验收/测试 | 完整 | 已加指针 |
| plan-test/config.md | 不得视沉默为批准、扩大授权 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/RULES.md | 攒批编号，`checklists/handoff.md` H3 | 决策批次 | 轻量 | 已合并：见 plan-test/RULES.md 攒批编号，`checklists/handoff.md` H3 |
| plan-test/references/user-attention.md | 已完成什么/现在验证什么/是否需要你 | 进度汇报 | 自查 | 已加指针（SL-3 语义核对后补回） |
| plan-test/references/user-attention.md | 可感知标的差异（模型/端口/模式）定稿前复述 | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/user-attention.md | 摘要后执行，不重复要 | 进度汇报 | 自查 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/user-attention.md | 合并一次 review 停在实现前 | 定稿/合并 review | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/user-attention.md | 只问未明确的目标/价值取舍 | 开放式澄清 | 自查 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/user-attention.md | 按用户边界保存现状与未完成项 | 停下等用户 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/RULES.md | 只在意图缺失、可感知行为变化或缩 AC | 请用户拍板 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/user-attention.md | 决策简报格式只在 `checklists/handoff.md` H3 | 请用户拍板 | 轻量 | 已加指针 |
| plan-test/RULES.md | 攒批编号，`checklists/handoff.md` H3 | 决策批次 | 轻量 | 已合并：见 plan-test/RULES.md 攒批编号，`checklists/handoff.md` H3 |
| plan-test/references/user-attention.md | 无独立工作则说明卡点结束本轮 | 停下等用户 | 轻量 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/user-attention.md | BLOCKED 升级消息按 `checklists/handoff.md` | BLOCKED 升级 | 轻量 | 已加指针 |
| plan-test/references/user-attention.md | demo 给实物（URL/截图/命令） | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/references/user-attention.md | 已完成什么/现在验证什么/是否需要你 | 进度汇报 | 自查 | 已加指针（SL-3 语义核对后补回） |
| plan-test/references/user-attention.md | 对用户只说影响结果的门与限制 | 进度汇报 | 自查 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/delivery-slices.md | 提交/构建身份及限制，异步展示实物 | demo/里程碑展示 | 完整 | 已加指针 |
| plan-test/references/delivery-slices.md | 用户要求暂停/验收或实际越出授权时 | 停下等用户 | 轻量 | 已加指针 |
| plan-test/conditional/delivery-slices.md | SL-x 里程碑通过，整体未完成 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
| plan-test/references/delivery-slices.md | SL-1 验收通过，整体尚有 SL-2/3 | 宣布完成/交付措辞 | 完整 | 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） |
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

### 按指针状态（v0.9.0 SL-3 重定位后）

| 指针状态 | 条数 |
|---|---|
| 已合并（新位置条目含指针或原为四问覆盖） | 11 |
| 已加指针（SL-3 语义核对后补回） | 5 |
| 由三入口四问触发覆盖 | 21 |
| 由三入口四问触发覆盖（原表误标已加指针，SL-3 核对发现） | 50 |
| 已加指针 | 23 |
| **合计** | 110 |
