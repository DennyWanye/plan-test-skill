---
name: plan-test
description: 端到端"需求澄清→架构基线→写plan→子代理挑战迭代→并行执行→100%完成度校验→测试策略路由(MCP真人测试/自动化脚本)→收尾DoD"全流程编排。当用户要对项目做优化/升级/重构、说"调研升级方向""写个能100%执行的plan并迭代""按计划并行执行并测试""做完要真人点击测试""写计划并执行测试""写个plan并执行并测试"时使用。注意：若用户只想要一份实现计划、不需要执行与测试（如"帮我写个plan""写个计划"），那是 writing-plans 的职责，不要用本 skill。Use for end-to-end research→plan→execute→verify→test workflows, NOT for plan-only requests.
---

# plan-test

把一份"优化/升级需求"走完整生命周期：从可验证的验收标准，到代码级可执行的 plan，到并行执行，到 100% 完成度校验，到按被测对象路由的测试（MCP 真人点击 / 自动化脚本），最后合上闭环。

**姊妹 skill**：本插件还提供两个拆分入口，共享本目录的阶段文档与配置——`plan-bs`（头脑风暴共创 plan → 迭代 + spike 验证 → review 定稿，不实现业务代码）和 `plan-task`（执行已定稿 plan + 测试闭环）。plan-test = plan-bs + plan-task 的一条龙自动版。

规则的历史原因放在冷路径 `rationale.md`；正常执行不要加载它。修改规则或做 gate 退休评审时再读。

**核心原则**
- **唯一真相来源**：一切回溯到用户批准的 `acceptance.md` + `assurance-contract.json`。
  后者冻结保障等级、可信假设、范围内失败/对手和最大影响；challenger 不得自行扩大。
- **机器门是唯一完成 authority**（见 `gate/PROTOCOL.md` + `config.md`"机器门禁"）：Markdown 是给人读的视图，不是状态 authority。测试事实记入 `verification/<run-id>/plan-test-run.json` 唯一账本，状态由 `scripts/plan_test_gate.py` 重算；**最终交付判定只接受 `finalize` 的 exit code**，没有有效 `gate-receipt.json` 的手写 SHIP/100% 一律无效。qualitative auditor 负责发现未知问题，deterministic validator 负责阻止已知违规，两者不可互替。
- **条件门的适用性判定是 fact，不是口头判断**：`input_sensitive` / `llm_payload_driven` / `stateful_init` 必须在 gate manifest 的 `applicability` 里显式声明（值 + 理由 + 判定人），由 init 冻结进账本与 receipt。判"不适用"合法，但**理由留痕、事后可追责**；判"适用"则场景矩阵必须真的兑现，否则 `APPLICABILITY_GATE_UNSATISFIED`。此前判一句"这是确定性 UI"就能让四道门合法消失且无人知晓。
- **机器门要真的被调用才存在**：`hooks/` 提供 Stop hook 与 CI 片段，把"必须跑 finalize"从纪律变成强制。未启用任一种时，交付说明里要如实写"机器门为自愿调用"。
- **每个声明可验证**：不说"看起来做完了"，而是逐条核对可追溯矩阵。
- **testcase 是项目资产，不是一次性产物**：设计用例前先读取 `{TESTCASE_DIR}/index.md` 与
  机器 inventory，再阅读候选用例原文并记录 reuse decision；可直接复用就不重复创建，
  但复用只复用 oracle，当前 run 仍必须重新执行并取证。
- **每个失败有出口**：plan challenge 使用 3/5/8 的 scope-audit/user-review/hard-stop；
  其他循环使用 `MAX_ROUNDS`。任何 reset 都不清零历史。
- **已批准行为不缩水**（`BEHAVIOR_POLICY = preserve-approved`）：不得静默减少用户已批准的外部行为；
  可以删除、替换或重构内部实现，也可以删除 acceptance 明确批准删除的旧行为。下限之上的最小化
  统一按 `policies/acceptance-preserving-ponytail.md` 执行。
- **小 slice 交付**：交付体量超 `RELEASE_UNIT_LIMITS`（默认 8 条 MUST AC / 10 个 Task /
  2000 行 plan / 3 个高风险子系统）→ validator 直接 `RELEASE_UNIT_TOO_LARGE`，拆 program plan +
  垂直 slice，每个 slice 独立验收。

## 开场（每次必做）

1. **Announce**：输出 "I'm using the plan-test skill to run the full plan→execute→test workflow."
2. **读配置**：读取本 skill 的 `config.md`；若项目根存在 `.claude/plan-test.config.md`，用它覆盖默认值。本文档中所有 `{大写变量}` 在运行时用配置值替换。
3. **判路径并宣布**（`FLOW_TIER`，见 config.md“流程路径”）：按风险与可逆性判
   DIRECT / LEAN / FULL，明确依据和跳过的阶段。DIRECT = 不启动本流程。疑义往高风险路径判。
   LEAN 仍保留“primary 主挑战 → 按 cluster 专项挑战”的顺序，只压缩无新增关键问题后的轮次。
4. **建 TodoWrite**：把该路径要跑的阶段建成 todo，逐项 in_progress → completed 推进。

## 阶段全景

| # | 阶段 | 文档 | 关键产物 |
|---|---|---|---|
| A | 需求澄清 & 验收标准 | `phase-A-acceptance.md` | `acceptance.md` + `assurance-contract.json` |
| 0 | 架构基线 | `phase-0-architecture.md` | `{ARCH_DIR}/ARCHITECTURE.md` + index.md |
| 1 | 写 plan | `phase-1-plan.md` | `{PLANS_DIR}/<feature>/plan.md` |
| 2 | 迭代 plan（含锁定绿色基线） | `phase-2-iterate-plan.md` | 定稿 plan + 基线快照 |
| 3 | 并行执行 + 完成度审计 | `phase-3-execute.md` | 代码 + 审计报告 |
| 4 | 验收门禁（测试策略路由；昂贵层前先冻结 testcase + gate init，出口是 `finalize --check-only`） | `phase-4-stage-gate.md` | 账本内的测试事实 + READY_FOR_AUDIT |
| 5 | testcase 收尾维护（编写与挑战已前移至 phase-4 昂贵层前；**独立 full-audit 在本阶段末尾**） | `phase-5-testcase.md` | `{TESTCASE_DIR}/` + index.md + audit 入账 |
| █ | 收尾 DoD + 文档回写 | `phase-final-dod.md` | `finalize` exit 0 + gate receipt + DoD 清单全绿 |

**推进规则：依赖图，不是全局串行**（DeskPet 2026-08-03 复盘 P1-6：testcase/fixture/gate
准备耗时 3h27m，几乎全部本可与 2h30m 的实现段重叠；全局串行是那次 10h20m 里最大的可压缩项）。

阶段间真正的硬依赖只有这几条，**其余允许并行**：

1. **A → 1 → 2 → 用户批准** 必须串行（唯一真相与行为契约没定，后面全是沙上建塔）；
2. 用户批准后分**双轨并行**：
   - **代码轨**：phase-3 实现 + 完成度审计（A/A2/B/C 节）；
   - **验证准备轨**：testcase inventory 读取与候选复用评估、必要用例编写与 challenger 迭代、fixture/种子数据、冒烟脚本、
     测试环境准备脚本、gate manifest 草案（场景矩阵/impact_paths/applicability）——
     见 phase-3 D 节与 `checklists/parallel-verification-track.md`。
     **black-box 纪律**：本轨只准读 acceptance/plan/行为契约，**禁止读实现代码与 diff**
     ——oracle 在实现落地前定稿，才防得住"照着实现写测试、bug 被测成预期行为"；
3. **汇合闸**：两轨都收尾 → testcase 冻结 + gate init（phase-4 昂贵层前置）→ 便宜门序 →
   **昂贵真人测试**——这是唯一必须等代码冻结的环节；
4. phase-5 结果回写 → **full-audit（输入定型之后）** → final DoD `finalize` 必须串行收尾。

**每个阶段/轨道收尾必须过"100% 完成度审计 + 该阶段对应测试"才算完成**（阶段门禁铁律不变，
并行改变的是排布，不是任何一道门的强度）。任何阶段卡在"循环直到 100%"超过 `MAX_ROUNDS`，
立即停下、标记 BLOCKED、带"卡在哪/试过什么/需要什么解锁"升级给用户。

- **每阶段先读文档（防跳步硬闸）**：进入每个阶段前，**先完整读该阶段的 `phase-X.md`** 并列出其必做项清单，逐项打勾——不许凭"我大概懂了"跳过子步骤（漏测几乎都源于此）。
- **⚠️ 末尾警戒**：越接近收尾越容易用便宜的代码审计替昂贵的真机测试来"尽快合上"。**`MANUAL_TEST=required` 的 UI 测试不许降级**，测不了就 BLOCKED 升级（见 phase-4 ①b 兑现表）。**"主流程通过"≠"每条 AC 都测了"。**
- **会话续接先复验**：压缩/跨会话/换 agent 后，推进前先重跑当前路径声明范围的分级冒烟；
  旧的脏工作树 PASS 不得沿用。
- **增量 AC 不许绕流程**：新 AC 必须先进 acceptance；可只跑受影响兑现表，但提交态硬门不得豁免，
  smoke 按 config 分级执行。

## 子代理用法

- 挑战/评估/审计/迭代类子代理：各自的提示词在 `prompts/` 下，派发时把对应文件内容作为子代理 prompt，引擎用配置里指定的值。
- 执行类子代理：用 `{EXECUTOR_ENGINE}` 并行派发（默认 `current` = 继承当前会话模型，不指定 model 参数；用户当前用什么模型，执行子代理就用什么模型）。
- 终审（完成度/测试覆盖最终确认）：用 `{AUDITOR_ENGINE}`（默认 opus-4.8）。
- 调研类步骤（phase-0/1/2）遵循 `methods/research-method.md` 的调研纪律。

### 上下文包（派发铁律，省 token）

子代理是冷启动的，不共享我的上下文。**每次派发必须随 prompt 附上"上下文包"**，而不是让子代理自己全仓摸索：

1. **直接嵌入**：`acceptance.md`、`assurance-contract.json` 相关原文、plan 片段、上一轮
   open/resolved finding ledger；不得只给自然语言摘要。
2. **圈定读取范围**：明确列出"只需读这些文件/目录"，禁止子代理全仓扫描。
3. **增量迭代**：第一轮 breadth；后续传当前 diff + open/resolved ID，只挑战未闭环、diff 和
   第一轮不可知的新事实。重大 architecture/scope/trust-boundary 变化才做 consolidated review。

### 输出 authority

- plan challenger 只输出结构化 findings JSON；`plan_test_gate.py` 按真实 ID、scope、状态和控制
  事件推导收敛，reviewer 自报 PASS/FAIL 没有 authority。
- 其他 qualitative auditor 仍按各自 prompt 的 `VERDICT` 契约输出；最终交付 authority 始终是
  deterministic gate 的 exit code 与 receipt。

## 何时不要用（= DIRECT 路径）

- 低风险且可快速回滚、不涉及权限/资金/身份/迁移/新持久化状态/公共协议/信任边界/新依赖的
  单点小改、一次性脚本、纯问答 → 不启动阶段流程，直接做；仍保留一句 AC 和提交态硬门。
- 没有明确"项目"上下文（不在仓库里）→ 先确认工作目录。
- **只想要一份实现计划、不需要执行与测试**（"帮我写个plan""写个计划"）→ 用 `writing-plans`，不要用本 skill。本 skill 的"写计划"只是全流程中的一步。
- **想和用户对话讨论、共创出 plan 再说**（"头脑风暴""一起想想怎么做"）→ 用 `plan-bs`。
- **已有定稿 plan，只要执行和测试** → 用 `plan-task`。
