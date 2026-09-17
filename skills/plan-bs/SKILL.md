---
name: plan-bs
description: 头脑风暴式计划共创：通过多轮对话引导用户澄清需求与核心矛盾，共创出初始 plan，再用子代理挑战迭代到"100% 代码可执行"，关键技术假设用真代码 spike 验证后，和用户 review 定稿。当用户说"头脑风暴""和我一起讨论这个需求""一起想想怎么做""共创一份计划""帮我把想法变成可执行的 plan""/plan-bs"时使用。产出定稿 plan——会跑可丢弃的验证 spike，但不实现业务代码；实现与测试交给 plan-task。注意：用户不想对话讨论、只要直接出一份 plan → 用 writing-plans；用户要"一条龙做完（含执行测试）"→ 用 plan-test。
---

# plan-bs

对话共创定稿 plan。本 skill 不改业务代码、不执行 plan（spike 跑完即弃），定稿后交 `/plan-task`。共享文档在 `../plan-test/`。

## 开场（每次必做）

1. Announce：输出 "我正在使用 plan-bs skill 和你一起头脑风暴、共创 plan。"
2. 读配置：`../plan-test/config.md`；`.claude/plan-test.config.md` 则覆盖；`{大写变量}` 运行时替换。
3. 读 `../plan-test/RULES.md`；保留共创，先查事实再问价值取舍。
4. 判任务类型（`TASK_TYPE`，见 config"流程分档"）：ops 走 OPS（快照/回滚先行、1 轮实测挑战、journal 收尾，不套交付仪式）；delivery 读 `../plan-test/references/delivery-slices.md`：当前片细化定稿后交 plan-task 实施
5. 建 TodoWrite：按下面 5 步

**交接前检查（`HANDOFF_CHECK`）**：每次结束本轮回复前先问四问——让用户动手？要用户表态（含汇报里顺带一句）？说完成/通过/可推送？停下等用户？任一为是 = 交接：读 `../plan-test/checklists/handoff.md` 按对应档过一遍并派评估员（`MODE: full|light`），PASS 或（文字类问题改完）才发；消息第一段先写需要用户做什么。上下文压缩后第一次交接前必须重读该文件。

上下文压缩后重读本文件、`RULES.md`、当前阶段文档。

## 流程

### 1. 头脑风暴（不许跳过）

产出是想清楚而非文档。
- 先读已给材料和现状，复用已明确目标与限制，不要求用户重新描述可自行查到的事实；每轮只问真正缺失的 1–2 个问题，已清楚就直接归纳。
- 引导顺序（灵活）：
  1. 目标与动机：不做会怎样？挖到"为什么"，别停在"做什么"。
  2. 主要矛盾（`../plan-test/methods/research-method.md` 第 2 条）：决定成败的核心问题，引导用户亲口说出来或一起推出来。
  3. 现状与约束：什么不能动、时间/兼容/性能硬约束。
  4. 边界：明确不做什么（防蔓延）。
  5. 备选方案：先定向调查/spike，再用决策简报给方向、推荐及代价；目标与价值取舍归用户，授权范围内的技术细节由 Agent 调研后自决。
- 模糊回答追问具体场景，没想清楚处用例子帮他想。

### 2. 收敛为验收标准

按 `../plan-test/phase-A-acceptance.md` 收敛 `{ACCEPTANCE_FILE}`（R2）。草案即可继续调查；review 与定稿 plan 合并；不明确的目标先问最小问题。

### 3. 调查与共创初始 plan

按 `../plan-test/phase-1-plan.md`（调查→调研→spike→初始 plan）。技术细节调查后自主写入 plan；新事实推翻方向先查范围内替代，确需改目标/行为才决策简报，技术分歧本身不是理由。

### 4. 迭代 plan

- 按 `../plan-test/phase-2-iterate-plan.md` A 节（重点论、记账与编排）挑战；不平铺无焦点 challenger，不跳过 primary。
- 新暴露的关键假设当轮 spike 真跑（命令+输出），回写 plan 再进下一轮。
- 假设不成立→方案层面改（必要时回步骤 1），不许硬着头皮收敛；spike 代码即弃，不滚成实现。
- B 节"锁定绿色基线"归 plan-task。Ponytail minimality pass 按 phase-2 单独一次。

### 4b. 关键假设验证收口

定稿前对照整体与当前片关键假设清单（未来片记待细化项，不冒充已验证）：
1. 覆盖主要矛盾解法依赖的全部假设？
2. 每条有真跑证据（命令+输出）+结论，无"预计可行/理论上支持/读过源码应该行"？
3. 有遗漏或纸上项→回步骤 4 补验证，不许带着未验证假设定稿。

### 5. 和用户 review 定稿

- review 消息按 `../plan-test/checklists/handoff.md` 走轻量评估 + 表 1 原话对照；验收与 plan 一起给，已确认项不再问。含：主要矛盾、方案及理由、任务概览、关键改动、关键假设验证结果（怎么验、证据）。
- 通过后 `plan.md` 头部写 `<!-- plan-status: finalized (plan-bs) -->`。
- 收尾输出（交接消息，完整评估）：plan 与 acceptance 路径 + 提示运行 `/plan-task <plan 文件夹>`。

## 何时不要用

- 不想讨论只要 plan→`writing-plans`；要一条龙→`plan-test`；已有定稿 plan→`plan-task`。
