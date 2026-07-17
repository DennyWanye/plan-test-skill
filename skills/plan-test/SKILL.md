---
name: plan-test
description: 端到端"需求澄清→架构基线→写plan→子代理挑战迭代→并行执行→100%完成度校验→测试策略路由(MCP真人测试/自动化脚本)→收尾DoD"全流程编排。当用户要对项目做优化/升级/重构、说"调研升级方向""写个能100%执行的plan并迭代""按计划并行执行并测试""做完要真人点击测试""写计划并执行测试""写个plan并执行并测试"时使用。注意：若用户只想要一份实现计划、不需要执行与测试（如"帮我写个plan""写个计划"），那是 writing-plans 的职责，不要用本 skill。Use for end-to-end research→plan→execute→verify→test workflows, NOT for plan-only requests.
---

# plan-test

把一份"优化/升级需求"走完整生命周期：从可验证的验收标准，到代码级可执行的 plan，到并行执行，到 100% 完成度校验，到按被测对象路由的测试（MCP 真人点击 / 自动化脚本），最后合上闭环。

**姊妹 skill**：本插件还提供两个拆分入口，共享本目录的阶段文档与配置——`plan-bs`（头脑风暴共创 plan → 迭代 + spike 验证 → review 定稿，不实现业务代码）和 `plan-task`（执行已定稿 plan + 测试闭环）。plan-test = plan-bs + plan-task 的一条龙自动版。

**核心原则**
- **唯一真相来源**：一切（plan 收敛、完成度审计、testcase 覆盖）都回溯到 `acceptance.md` 里的验收标准。
- **每个声明可验证**：不说"看起来做完了"，而是逐条核对可追溯矩阵。
- **每个失败有出口**：所有"循环直到 100%"都有 `MAX_ROUNDS`，超限 → 标记 BLOCKED 升级给用户。
- **功能只增不减**：遇分歧按最佳实践自决（**自决仅限实现层**——plan 层缺陷走 phase-3 A2 回炉，不许打补丁绕），但绝不少做。

## 开场（每次必做）

1. **Announce**：输出 "I'm using the plan-test skill to run the full plan→execute→test workflow."
2. **读配置**：读取本 skill 的 `config.md`；若项目根存在 `.claude/plan-test.config.md`，用它覆盖默认值。本文档中所有 `{大写变量}` 在运行时用配置值替换。
3. **建 TodoWrite**：把下面 8 个阶段建成 todo，逐项 in_progress → completed 推进。

## 阶段全景

| # | 阶段 | 文档 | 关键产物 |
|---|---|---|---|
| A | 需求澄清 & 验收标准 | `phase-A-acceptance.md` | `acceptance.md`（唯一真相来源） |
| 0 | 架构基线 | `phase-0-architecture.md` | `{ARCH_DIR}/ARCHITECTURE.md` + index.md |
| 1 | 写 plan | `phase-1-plan.md` | `{PLANS_DIR}/<feature>/plan.md` |
| 2 | 迭代 plan（含锁定绿色基线） | `phase-2-iterate-plan.md` | 定稿 plan + 基线快照 |
| 3 | 并行执行 + 完成度审计 | `phase-3-execute.md` | 代码 + 审计报告 |
| 4 | 验收门禁（测试策略路由；昂贵层前先冻结 testcase，见 phase-5 时序说明） | `phase-4-stage-gate.md` | 测试通过证据 |
| 5 | testcase 收尾维护（编写与挑战已前移至 phase-4 昂贵层前） | `phase-5-testcase.md` | `{TESTCASE_DIR}/` + index.md |
| █ | 收尾 DoD + 文档回写 | `phase-final-dod.md` | DoD 清单全绿 |

**推进规则**：严格顺序执行。**每个阶段收尾必须过"100% 完成度审计 + 该阶段对应测试"才能进入下一阶段**（阶段门禁铁律）。任何阶段卡在"循环直到 100%"超过 `MAX_ROUNDS`，立即停下、标记 BLOCKED、带"卡在哪/试过什么/需要什么解锁"升级给用户。

- **每阶段先读文档（防跳步硬闸）**：进入每个阶段前，**先完整读该阶段的 `phase-X.md`** 并列出其必做项清单，逐项打勾——不许凭"我大概懂了"跳过子步骤（漏测几乎都源于此）。
- **⚠️ 末尾警戒**：越接近收尾越容易用便宜的代码审计替昂贵的真机测试来"尽快合上"。**`MANUAL_TEST=required` 的 UI 测试不许降级**，测不了就 BLOCKED 升级（见 phase-4 ①b 兑现表）。**"主流程通过"≠"每条 AC 都测了"。**

## 子代理用法

- 挑战/评估/审计/迭代类子代理：各自的提示词在 `prompts/` 下，派发时把对应文件内容作为子代理 prompt，引擎用配置里指定的值。
- 执行类子代理：用 `{EXECUTOR_ENGINE}` 并行派发（默认 codex-gpt5.5，未装则回退 claude）。
- 终审（完成度/测试覆盖最终确认）：用 `{AUDITOR_ENGINE}`（默认 opus-4.8）。
- 调研类步骤（phase-0/1/2）遵循 `methods/research-method.md` 的调研纪律。

### 上下文包（派发铁律，省 token）

子代理是冷启动的，不共享我的上下文。**每次派发必须随 prompt 附上"上下文包"**，而不是让子代理自己全仓摸索：

1. **直接嵌入**：`acceptance.md` 相关条款原文、plan 相关片段原文、上一轮挑战/审计的结论清单。
2. **圈定读取范围**：明确列出"只需读这些文件/目录"，禁止子代理全仓扫描。
3. **增量迭代**：多轮挑战/审计时，把"上一轮已确认闭环的问题清单"传给下一轮，声明**不必重复挑战已闭环项**，只挑战新增与未闭环部分。

### 结论行解析（VERDICT）

- 所有挑战/审计类子代理的输出**最后一行必须是 `VERDICT: PASS` 或 `VERDICT: FAIL`**（提示词里已规定）。
- 我只按这一行判定循环是否继续，不靠解读正文语气。
- 最后一行缺失或不合格式 → **一律按 FAIL 处理**，并在下一轮派发时要求补上结论行；不许自行脑补为通过。

## 何时不要用

- 单文件小改、一次性脚本、纯问答 → 直接做，别套这套重流程。
- 没有明确"项目"上下文（不在仓库里）→ 先确认工作目录。
- **只想要一份实现计划、不需要执行与测试**（"帮我写个plan""写个计划"）→ 用 `writing-plans`，不要用本 skill。本 skill 的"写计划"只是全流程中的一步。
- **想和用户对话讨论、共创出 plan 再说**（"头脑风暴""一起想想怎么做"）→ 用 `plan-bs`。
- **已有定稿 plan，只要执行和测试** → 用 `plan-task`。
