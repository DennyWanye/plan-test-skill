---
name: plan-test
description: 端到端"矛盾分析→调查写plan→挑战定稿→执行→围绕主要矛盾验收→收尾DoD"全流程编排。当用户要对项目做优化/升级/重构、说"调研升级方向""写个能100%执行的plan并迭代""按计划并行执行并测试""做完要真人点击测试""写计划并执行测试""写个plan并执行并测试"时使用。注意：若用户只想要一份实现计划、不需要执行与测试（如"帮我写个plan""写个计划"），那是 writing-plans 的职责，不要用本 skill。Use for end-to-end research→plan→execute→verify→test workflows, NOT for plan-only requests.
---

# plan-test

把一份"优化/升级需求"走完整生命周期：从矛盾分析与可验证的验收标准，到代码级可执行的 plan，到执行，到围绕主要矛盾的验收测试，最后合上闭环。

**姊妹 skill**：本插件还提供两个拆分入口，共享本目录的阶段文档与配置——`plan-bs`（头脑风暴共创 plan → 迭代 + spike 验证 → review 定稿，不实现业务代码）和 `plan-task`（执行已定稿 plan + 测试闭环）。plan-test = plan-bs + plan-task 的一条龙自动版。

规则的历史原因放在冷路径 `rationale.md`；正常执行不要加载它。修改规则或做 gate 退休评审时再读。退休的阶段文档在 `retired/`。

## 总纲：战略上藐视，战术上重视

- **战略上藐视**：敢于裁剪仪式——默认 LEAN、默认 journal 收尾、挑战与测试的力度按矛盾地位收窄；说不出理由的门就跳过（留痕）。
- **战术上重视**：每条声明必须有实测证据——决定性 AC 必须真验证、真人测试不降级、提交态必须干净。**砍的是仪式，不是证据。**

## 用户注意力

开场读 `references/user-attention.md`。先调查、形成可审阅的 plan；已有授权覆盖方案时自主推进。需要用户决策时先提供事实、推荐、代价与未知项。各阶段的确认、BLOCKED、demo 和续接按该 reference 解释。

## 核心原则

- **围绕主要矛盾（全流程的骨架）**：acceptance 第一节是矛盾分析四问（主要矛盾是什么/产生原因/怎么解决 + 最小验证动作/矛盾的主要方面，格式硬约束见 phase-A：单一矛盾、价值在前防御在后、复合句 = 没写，challenger P0 打回）；每条 AC 标注**决定性/次要**，挑战轮次（phase-2）、任务排序与执行火力（phase-3）、测试深度（phase-4）全部按它路由。价值验证里程碑未 PASS 前禁止任何昂贵加固（`VALUE_SMOKE_GATE`）；里程碑 PASS 后**demo 给用户 + 矛盾转化再分析**（phase-3 A.3）。
- **两点论与重点论统一**：火力集中在主要矛盾（重点论），但次要 AC 的下限是"一轮挑战、一遍测试"，不是零（两点论）——不许因为"不是主要矛盾"就删掉或不测。
- **实事求是，没有调查就没有发言权**：现状调查并入 phase-1（解剖麻雀，结论进 plan，不维护独立架构文档）；关键假设**实践先行**——写 plan 时当场 spike 真跑，不等 challenger 逼问；反对本本主义（外部实践必附本项目适配分析）。
- **不打无准备之仗，不打无把握之仗**：phase-2 收敛判据含逐任务核对"假设已实测、现状已真读"；没把握就补调查补实践，不靠 A2 回炉兜底。
- **具体问题具体分析（对本 skill 自己的规则同样适用）**：开场必须列出本次要跑/跳过的门各附一句话理由；条件门（输入敏感/LLM 载荷/冷启动）只在真命中判定时生效，不许套模板。
- **任务类型先于风险分档**：先判 `TASK_TYPE`（delivery / ops）——运维/部署任务走 OPS 路径，不套软件交付仪式（见 config"流程路径"）。
- **反对党八股（`MACHINE_GATE`，见 config）**：机器账本层仅在 FULL 且高外部性时启用；默认完成记录 = 一页 journal。未启用机器门时如实写"无机器 receipt"，不得使用 receipt/SHIP 措辞。
- **禁止自造防御系统 / 复验粒度跟随变更粒度**：见 config `SELF_BUILT_DEFENSE`、`REVALIDATION_SCOPE`。
- **唯一真相来源**：一切回溯到用户批准的 `{ACCEPTANCE_FILE}`（FULL 路径另含 `assurance-contract.json`）；challenger 不得自行扩大范围。
- **oracle 先于实现**：任何 AC 的"什么算对"在实现之前写下；禁止照实现补预期（phase-2/3）。
- **从群众中来，到群众中去**：需求从用户澄清中来（phase-A 提炼矛盾分析，按交互边界合并 review）；里程碑 PASS 后拿**跑起来的实物**回到用户中检验（demo）；进度用用户语言汇报（config `PROGRESS_REPORTING`）；用户可感知的标的差异必须在决策简报中说明并取得对应授权。
- **每个声明可验证**：不说"看起来做完了"，逐条核对可追溯矩阵；journal 里每条声明附实测证据。
- **每个失败有出口**：plan challenge 用 3/5/8 出口，其他循环用 `MAX_ROUNDS`（见 config）；任何 reset 不清零历史。
- **已批准行为不缩水**：`BEHAVIOR_POLICY = preserve-approved`；最小化按 `policies/acceptance-preserving-ponytail.md`。
- **小 slice 交付**：超 `RELEASE_UNIT_LIMITS` → 拆 program plan + 垂直 slice，每个 slice 独立验收。
- **testcase 是项目资产**：设计用例前先查已有资产并记录 reuse decision（`references/testcase-lifecycle.md`）；复用只复用 oracle，当前 run 仍须重新执行取证。
- **批评与自我批评**：challenger 子代理是对 plan 的批评；**代码 review 是对实现的批评（`CODE_REVIEW`，执行者不自审）**——delivery 且含非平凡代码时必做，挂 phase-3 A4 与 push 前两道，深度按矛盾地位路由，修复后按分层复验（便宜层全量 + 受影响决定性测试 + 价值 smoke）；收尾的 retro 一行是自我批评（config `SELF_CRITICISM`）——门禁退休评审的数据源，防规则集只进不出。

## 开场（每次必做）

1. **Announce**：输出 "I'm using the plan-test skill to run the full plan→execute→test workflow."
2. **读配置**：读本 skill 的 `config.md`；项目根存在 `.claude/plan-test.config.md` 则覆盖默认值。所有 `{大写变量}` 运行时替换。
3. **判任务类型与路径并宣布**（`TASK_TYPE` + `FLOW_TIER`，判据见 config"流程路径"）：先判 delivery / ops；delivery 再判 DIRECT / LEAN / FULL；FULL 再判 `MACHINE_GATE` 是否启用。疑义往高风险路径判（但 ops 误判成 delivery-FULL 的代价是仪式压垮任务，类型判定按交付物本质）。
4. **列门清单（存入 plan，不逐项要求用户阅读）**：记录本次要跑的门与跳过的门，**各附一句话理由**；理由说不出的门就是本本主义——跳过并留痕。
5. **建 TodoWrite**：把该路径要跑的阶段建成 todo，逐项 in_progress → completed 推进。

## 阶段全景

| # | 阶段 | 文档 | 关键产物 |
|---|---|---|---|
| A | 矛盾分析与验收标准 | `phase-A-acceptance.md` | `{ACCEPTANCE_FILE}`（矛盾四问 + 决定性/次要 AC） |
| 1 | 调查与写 plan | `phase-1-plan.md` | `{PLANS_DIR}/<feature>/plan.md`（含现状调查与 spike 证据） |
| 2 | 挑战与定稿（含锁定绿色基线） | `phase-2-iterate-plan.md` | 定稿 plan + 基线快照 |
| 3 | 执行（集中/分兵自决 + 里程碑 demo + 代码 review + 完成度审计） | `phase-3-execute.md` | 代码 + 矛盾再分析 + review 闭环 + 审计报告 |
| 4 | 验收（重点论测试 + testcase 收尾） | `phase-4-stage-gate.md` | journal / 机器账本 + 兑现表 + testcase 归档 |
| █ | 收尾 DoD + 文档回写 + 自我批评 | `phase-final-dod.md` | DoD 全绿 + journal 终态行 + retro 一行（FULL：receipt） |

**推进规则**：

1. **A 草案 → 1 调查 → 2 挑战 → 授权核对**：调查和挑战可以基于明确标注的草案，不能先改用户目标；需要 review 时把验收标准、plan 与决策简报合并一次提交；
2. 当前授权已覆盖定稿方案且无重要未决取舍 → 直接进入 phase-3；用户要求先确认或方案超出授权 → 等待对应决定（见 `references/user-attention.md`）；
3. **价值里程碑是执行中段的战略节点**：PASS → demo + 矛盾转化再分析，然后推进剩余任务；FAIL → A2 回炉或 BLOCKED；
4. phase-4 验收：便宜门 → 核心价值 smoke（FAIL 即停）→ 决定性场景深测 → 次要各一遍 → testcase 收尾；
5. final：文档回写 → DoD → journal 终态行（`JOURNAL_VERDICT`）→ 自我批评 → 提交 →（要推送时）push 前 code review，P0/P1 修完再推（FULL 加 re-attest/full-audit/finalize）。

- **每阶段先读文档（防跳步硬闸）**：进入每个阶段前，先完整读该阶段的 `phase-X.md` 在 plan/journal 内记录必做项清单，逐项核对——不许凭"我大概懂了"跳过子步骤（漏测几乎都源于此）。
- **⚠️ 末尾警戒**：越接近收尾越容易用便宜的代码审计替昂贵的真机测试。**决定性 AC 的 UI 测试不许降级**，测不了就 BLOCKED 升级。"主流程通过"≠"每条 AC 都测了"。
- 任何阶段卡在"循环直到 100%"超过 `MAX_ROUNDS` → 停下、标 BLOCKED、带"卡在哪/试过什么/需要什么解锁"升级给用户。
- **会话续接先恢复事实**：按 `references/user-attention.md` 读取授权、未完成项与测试身份；按 config `REVALIDATION_SCOPE` 和 `FULL_SURFACE_SMOKE` 复验，不重复询问已记录的决定。旧的脏工作树 PASS 不得沿用。
- **增量 AC 不许绕流程**：见 config `INCREMENTAL_AC_MODE`。

## 子代理用法

- 挑战/评估/审计/迭代类子代理：提示词在 `prompts/` 下，派发时把对应文件内容作为子代理 prompt，引擎用配置指定值（`CHALLENGER_ENGINE` / `AUDITOR_ENGINE`）。
- 执行类子代理：分兵模式下用 `{EXECUTOR_ENGINE}` 并行派发（默认 `current` = 继承当前会话模型）。
- 调研类步骤遵循 `methods/research-method.md`。

### 上下文包（派发铁律，省 token）

子代理是冷启动的。**每次派发必须随 prompt 附上"上下文包"**：

1. **直接嵌入**：`{ACCEPTANCE_FILE}` 相关原文、plan 片段、上一轮 open/resolved finding 清单；不得只给自然语言摘要。
2. **圈定读取范围**：明确列出"只需读这些文件/目录"，禁止子代理全仓扫描。
3. **增量迭代**：第一轮 breadth；后续传当前 diff + open/resolved ID，只挑战未闭环与新事实。

### 输出 authority

- challenger 只输出结构化 findings JSON；LEAN 由主 agent 对照清单核对闭环，FULL 由 `plan_test_gate.py` 推导收敛——reviewer 自报 PASS/FAIL 没有 authority。
- 最终交付 authority：默认路径 = DoD 清单逐条证据核对；FULL（`MACHINE_GATE`）= `finalize` 的 exit code 与 receipt。

## 何时不要用（= DIRECT 路径）

- 单点小改、一次性脚本、纯问答（DIRECT 判据见 config）→ 不启动阶段流程，直接做；仍保留一句 AC 和提交态硬门。
- 没有明确"项目"上下文 → 先确认工作目录。
- **只想要一份实现计划**（"帮我写个plan"）→ 用 `writing-plans`。
- **想对话共创 plan**（"头脑风暴"）→ 用 `plan-bs`。
- **已有定稿 plan，只要执行和测试** → 用 `plan-task`。
