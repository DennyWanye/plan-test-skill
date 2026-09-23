---
name: plan-test
description: 端到端"矛盾分析→调查写plan→挑战定稿→执行→围绕主要矛盾验收→收尾DoD"全流程编排。当用户要对项目做优化/升级/重构、说"调研升级方向""写个能100%执行的plan并迭代""按计划并行执行并测试""做完要真人点击测试""写计划并执行测试""写个plan并执行并测试"时使用。注意：若用户只想要一份实现计划、不需要执行与测试（如"帮我写个plan""写个计划"），那是 writing-plans 的职责，不要用本 skill。Use for end-to-end research→plan→execute→verify→test workflows, NOT for plan-only requests.
---

# plan-test

`plan-bs`+`plan-task` 一条龙版，共享本目录。`rationale.md`/`retired/` 冷路径：正常执行不加载，改规则或 gate 退休评审时再读。

总纲：砍仪式（默认 LEAN、journal 收尾，说不出理由的门就跳过（留痕）），不砍证据（声明附实测证据）。

## 开场（每次必做）

1. Announce：输出 "我正在使用 plan-test skill 跑完整的 计划→执行→测试 流程。"
2. 读配置：`config.md`；`.claude/plan-test.config.md` 则覆盖默认值；`{大写变量}` 运行时替换。
3. 读 `RULES.md`。
4. 判类型与路径并宣布（`TASK_TYPE`+`FLOW_TIER`，见 config"流程分档"）：先 delivery/ops（按交付物本质，ops 不套交付仪式）→DIRECT/LEAN/FULL→FULL 判 `MACHINE_GATE`；疑义往高风险判。
5. 列门清单存入 plan：跑/跳过各附一句理由；条件门只在真命中时生效。
6. 建 TodoWrite：按路径阶段逐项推进

**交接前检查（`HANDOFF_CHECK`）**：结束本轮回复前按 RULES R10 交接卡走（四问 → 档位 → 派评估员 → fix_class 处置 → 末行）。

上下文压缩后重读 `RULES.md` 与 `{PLANS_DIR}/<feature>/checklist.md`（当前阶段必做项清单）；phase 文档只在清单不够用时再读。续接按 `references/user-attention.md` 恢复事实，重跑声明范围分级冒烟（R8）。

## 铁律索引（正文 RULES.md）

R1 唯一真相·R2 主要矛盾·R3 oracle·R4 价值 smoke·R5 真人测试·R6 提交态·R7 review·R8 复验·R9 BLOCKED/出口·R10 交接·R11 用户注意力·R12 终态行/retro·R13 行为不缩水·R14 禁自造防御/语言·R15 主 Agent 写代码·R16 高成本测试后置

## 阶段全景

| # | 阶段→产物 | 文档 |
|---|---|---|
| A | 矛盾四问+AC 分级→`{ACCEPTANCE_FILE}` | `phase-A-acceptance.md` |
| 1 | 调查+spike→plan.md | `phase-1-plan.md` |
| 2 | 挑战定稿+绿色基线 | `phase-2-iterate-plan.md` |
| 3 | 执行+demo+review+审计 | `phase-3-execute.md` |
| 4 | 验收→journal+兑现表 | `phase-4-stage-gate.md` |
| █ | DoD+终态行+retro（FULL：receipt） | `phase-final-dod.md` |

delivery 规划/执行同时读 `references/delivery-slices.md`。

推进规则：
1. A 草案→1→2→授权核对：可基于标注草案调查挑战，不先改用户目标；review 时验收+plan+决策简报合并一次提交。
2. 授权覆盖定稿方案且无重要未决取舍→直接进 phase-3，否则等对应决定（R11）。
3. 每片：真实入口 PASS→其余验证/review/审计/提交身份核对→异步 demo→细化下一片；FAIL→修复/A2 或真实阻塞；片内/整体分别报告。
4. phase-4：便宜门→核心价值 smoke（FAIL 即停）→决定性深测→次要各一遍→testcase 收尾；高成本测试只在此处、主体跑通后做（R16）。
5. final：文档回写→DoD→终态行→retro→提交→（要推送）push 前 review（FULL 加 re-attest/full-audit/finalize）。
- 防跳步：每阶段开工前读一次对应 phase 文档，把必做项清单写进 `{PLANS_DIR}/<feature>/checklist.md` 逐项核对；之后按清单推进，不为同一阶段重读。调研按 `methods/research-method.md`。

## 子代理

- 只做评测（挑战/审计/review/评估/只读调研）与主体跑通后的并行测试，不写仓库代码（RULES R15/R16）；prompt 在 `prompts/`，引擎 `CHALLENGER_ENGINE`/`AUDITOR_ENGINE`；编排/authority 见 `references/challenge-orchestration.md`。
- 上下文包（派发必附）：嵌入 acceptance 原文、plan 片段、open/resolved 清单（不只给摘要）；圈定范围禁全仓扫描；后续轮只传 diff+ID。

## 何时不要用

- DIRECT：直接做，仍留一句 AC+提交态硬门；无项目上下文先确认目录。
- 只要 plan→`writing-plans`；要共创→`plan-bs`；已有定稿 plan→`plan-task`。
