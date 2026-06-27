---
name: plan-test
description: 端到端"需求澄清→架构基线→写plan→子代理挑战迭代→并行执行→100%完成度校验→测试策略路由(MCP真人测试/自动化脚本)→收尾DoD"全流程编排。当用户要对项目做优化/升级/重构、说"调研升级方向""写个能100%执行的plan并迭代""按计划并行执行并测试""做完要真人点击测试""帮我写一个计划，是关于：""帮我写一个plan"时使用。Use for end-to-end research→plan→execute→verify→test workflows.
---

# plan-test

把一份"优化/升级需求"走完整生命周期：从可验证的验收标准，到代码级可执行的 plan，到并行执行，到 100% 完成度校验，到按被测对象路由的测试（MCP 真人点击 / 自动化脚本），最后合上闭环。

**核心原则**
- **唯一真相来源**：一切（plan 收敛、完成度审计、testcase 覆盖）都回溯到 `acceptance.md` 里的验收标准。
- **每个声明可验证**：不说"看起来做完了"，而是逐条核对可追溯矩阵。
- **每个失败有出口**：所有"循环直到 100%"都有 `MAX_ROUNDS`，超限 → 标记 BLOCKED 升级给用户。
- **功能只增不减**：遇分歧按最佳实践自决，但绝不少做。

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
| 4 | 阶段门禁（测试策略路由） | `phase-4-stage-gate.md` | 测试通过证据 |
| 5 | testcase 维护 | `phase-5-testcase.md` | `{TESTCASE_DIR}/` + index.md |
| █ | 收尾 DoD + 文档回写 | `phase-final-dod.md` | DoD 清单全绿 |

**推进规则**：严格顺序执行。**每个阶段收尾必须过"100% 完成度审计 + 该阶段对应测试"才能进入下一阶段**（阶段门禁铁律）。任何阶段卡在"循环直到 100%"超过 `MAX_ROUNDS`，立即停下、标记 BLOCKED、带"卡在哪/试过什么/需要什么解锁"升级给用户。

## 子代理用法

- 挑战/评估/审计/迭代类子代理：各自的提示词在 `prompts/` 下，派发时把对应文件内容作为子代理 prompt，引擎用配置里指定的值。
- 执行类子代理：用 `{EXECUTOR_ENGINE}` 并行派发（默认 codex-gpt5.5，未装则回退 claude）。
- 终审（完成度/测试覆盖最终确认）：用 `{AUDITOR_ENGINE}`（默认 opus-4.8）。

## 何时不要用

- 单文件小改、一次性脚本、纯问答 → 直接做，别套这套重流程。
- 没有明确"项目"上下文（不在仓库里）→ 先确认工作目录。
