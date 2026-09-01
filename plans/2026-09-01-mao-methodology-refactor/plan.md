# Plan：毛选方法论融合重构（plan-test skill 精简）

<!-- plan-status: finalized (用户 2026-09-01 在 chat 中批准方向："接受你的建议") -->

## 主要矛盾

- **核心问题（单一矛盾）**：plan-test 的仪式成本压过价值产出——毛选方法论只是点缀在字段里（主要矛盾是 1a 一个字段），而形式主义机制（机器账本、验证准备轨、独立架构文档维护）占据流程主干。实证：2026-08-31 DGX 复盘中机器门 100% 荒废、仪式占总耗时 22%、自造防御系统是最大故障源。
- **矛盾产生的原因**：这套流程是复盘驱动"只进不出"长出来的——每次翻车加一道门，但从未按重点论区分"防决定性逃逸的门"与"防边角逃逸的门"，导致所有门对所有任务同权重生效（本本主义地执行自己的规则）。
- **解法方向**：把"矛盾分析→调查→实践验证→围绕主要矛盾的挑战与测试"提升为流程骨架；把账本仪式降级为 FULL 且高外部性交付才启用的选项。
- **最小验证动作**：改完后以"帮用户做一个网站"场景通读新流程，确认阶段链条闭合；`grep` 校验无引用断链（phase-0/phase-5/验证准备轨/ARCH_DIR 的残留引用为零）。
- **矛盾的主要方面**：**砍仪式，不砍证据**——每一处精简必须保住"每条声明有实测证据"的战术纪律（战略上藐视，战术上重视）。

## 已确认的设计决策（用户 2026-09-01 批准）

| ID | 决策 | 对应毛选方法论 |
|----|------|---------------|
| D1 | Phase A 重组为"矛盾分析三问 + 矛盾的主要方面"作章节骨架；AC 从矛盾分析推导，标注**决定性/次要**，后续所有阶段力度分配引用此标注 | 矛盾论：主要矛盾、矛盾的主要方面 |
| D2 | Phase 0 撤销独立阶段：ARCHITECTURE.md 维护仪式去掉，"调查现状"职责并入 phase-1（解剖麻雀保留，结论直接写进 plan 的现状栏） | 没有调查，就没有发言权；调查为决策服务，不为存档服务 |
| D3 | Phase 1 实践先行：关键假设（决定成败且静态阅读无法确认）在写 plan 时**当场 spike 真跑**，带实测结果进挑战环节，不等 challenger 逼问 | 实践论：实践→认识→再实践 |
| D4 | Phase 2 挑战范围按重点论收窄：主要矛盾相关部分走完整四阶段挑战；其余部分一轮 breadth 无 P0 即收。3/5/8 出口保留 | 集中优势兵力；两点论与重点论统一 |
| D5 | Phase 2 出口加"有把握之仗"检查：每个任务开工前提 = 关键假设已 spike + 现状代码已读 | 不打无准备之仗，不打无把握之仗 |
| D6 | Phase 3 执行模式由 agent 自决：任务真独立且量大→分兵（并行子代理）；环环相扣或量小→集中兵力当前 session 串行打歼灭战。决策一行留痕 | 集中优势兵力，各个歼灭敌人 |
| D7 | 验证准备轨撤销，保留一句话规则：**oracle 先于实现**——写某 AC 的实现前先写下"什么算对"，禁止实现后照实现补预期 | （保住 black-box 纪律的最低成本形态） |
| D8 | 价值里程碑 PASS 后两个强制动作：①demo 给用户（跑起来的实物，非文档）；②矛盾转化再分析（重答三问、重排剩余任务） | 从群众中来到群众中去；矛盾的转化 |
| D9 | Phase 4 测试按重点论排布：主要矛盾场景先测深测（FAIL 即全停）；次要 AC 各过一遍；MCP 真人测试力度跟随矛盾地位。不降级铁律对决定性 AC 保留 | 重点论；两点论兜底 |
| D10 | 机器账本层（manifest 编译/init/record-run/attach-evidence/re-attest/finalize receipt）降级为 **FULL 且高外部性**才启用；默认完成记录 = 一页 journal（OPS 路径已验证的形态）。phase-5 撤销独立阶段，testcase 回写并入 phase-4 收尾，full-audit 仅机器门启用时保留 | 反对党八股（文牍主义） |
| D11 | 开场新增：列出本次要跑/跳过的门，各附一句话理由；说不出理由的门就是本本主义 | 具体问题具体分析 |
| D12 | 收尾新增"自我批评一行"：本次哪些门空转、哪里被仪式拖慢，写进 `plans/<feature>/retro.md`，作为门禁退休评审数据源 | 批评与自我批评 |
| D13 | SKILL.md 总纲写入"战略上藐视，战术上重视"：敢裁剪仪式（藐视），但每条声明必须有实测证据（重视） | 战略与战术 |

## 文件影响清单

| 文件（均在 `~/.claude/skills/` 下） | 改动 |
|------|------|
| `plan-test/SKILL.md` | 全量重写：新总纲、新阶段表（A/1/2/3/4/final 六阶段）、新推进规则、开场加 D11 |
| `plan-test/phase-A-acceptance.md` | 全量重写：矛盾三问+主要方面作骨架（D1） |
| `plan-test/phase-0-architecture.md` | 移入 `plan-test/retired/`（D2，保留原文供复盘追溯） |
| `plan-test/phase-1-plan.md` | 全量重写：吸收调查职责、实践先行（D2/D3） |
| `plan-test/phase-2-iterate-plan.md` | 定向修改：重点论收窄挑战范围、记账分档、有把握检查（D4/D5/D10） |
| `plan-test/phase-3-execute.md` | 全量重写：执行模式自决、oracle 先行、里程碑 demo+矛盾再分析、撤销 D 节（D6/D7/D8） |
| `plan-test/phase-4-stage-gate.md` | 全量重写：重点论测试排布、journal 默认、吸收 phase-5 的 testcase 收尾（D9/D10） |
| `plan-test/phase-5-testcase.md` | 移入 `plan-test/retired/`（D10） |
| `plan-test/phase-final-dod.md` | 全量重写：journal 默认收尾、receipt 仅机器门路径、自我批评一行（D10/D12） |
| `plan-test/config.md` | 定向修改：新增 `MACHINE_GATE` 与 `SELF_CRITICISM` 键、FLOW_TIER 表更新、`PARALLEL_TRACKS`→`EXECUTION_MODE`、机器门禁节标注条件生效、删 `ARCH_DIR` |
| `plan-bs/SKILL.md` | 定向修改：删架构基线步骤、对齐新 phase-A/1/2 |
| `plan-task/SKILL.md` | 定向修改：删验证准备轨、phase-5 引用改为 phase-4 收尾、机器门条件化 |

**不改动**：`scripts/`（gate 脚本本身不动，只改调用策略）、`prompts/`（architecture-challenger 等转为不再被主流程引用，留档）、`rationale.md`（冷路径）、`gate/`、`checklists/`（parallel-verification-track 转为仅供参考）、`references/`、`methods/`。

## 任务清单（最短价值路径优先）

- **Task 1** — 重写 phase-A（D1）。验证：新文档以矛盾三问开头，模板含决定性/次要标注。
- **Task 2** — 重写 phase-1（D2/D3）。验证：含"调查现状"与"实践先行"节；不再引用 ARCHITECTURE.md 产物。
- **Task 3** — 修改 phase-2（D4/D5/D10）。验证：含重点论范围声明、LEAN 轻量记账、有把握检查。
- **Task 4** — 重写 phase-3（D6/D7/D8）。验证：含自决判据、oracle 先行规则、里程碑双动作；无 D 节。
- **Task 5** — 重写 phase-4 + 移除 phase-5（D9/D10）。验证：主要矛盾场景先测深测；journal 为默认出口；testcase 收尾已并入。
- **Task 6** — 重写 phase-final（D10/D12）。验证：默认路径无 receipt 要求；含自我批评一行。
- **Task 7** — 修改 config.md。验证：MACHINE_GATE/SELF_CRITICISM/EXECUTION_MODE 键存在；机器门禁节头标注条件生效。
- **Task 8** — 重写 plan-test/SKILL.md（D11/D13）。验证：总纲、六阶段表、开场门清单要求。
- **Task 9** — 同步 plan-bs / plan-task。验证：两者无 phase-0/phase-5/验证准备轨引用。
- **Task 10** — 收尾校验（本 plan 的最小验证动作）：`grep -rn "phase-0\|phase-5\|parallel-verification-track\|ARCH_DIR" ~/.claude/skills/plan-{test,bs,task}/` 仅命中 retired/ 与 rationale/留档文件；以"做一个网站"场景通读一遍新流程确认闭合。

## 风险与边界

- **不缩水项**：BLOCKED 升级纪律、提交态硬门（COMMIT_STATE_GATE）、决定性 AC 的真人测试不降级、SELF_BUILT_DEFENSE 禁令、复验粒度跟随变更粒度、3/5/8 出口——这些是"战术上重视"的底线，本次全部保留。
- **可回退性**：phase-0/phase-5 原文移入 `retired/` 不删除；本 plan 与 chat 记录构成完整审计链。
- **范围外**：gate 脚本代码修改、prompts 重写、OPS 路径调整（已在 8-31 复盘中优化过，本次不动）。
