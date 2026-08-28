# 二次优化总 Program（2026-08-29）

> **业主指令**：不再逐 slice 分批请示——把全部优化点列全，决策点一次拍完，然后连续执行到底。
> **与仓库纪律的调和**：`RELEASE_UNIT_LIMITS` 的"小 slice 交付"保留为**执行内部结构**
> （每波独立 commit、每波全套测试绿、红测先行），取消的是**波次之间的逐次审批**。
> 执行中只在真 BLOCKED 或决策点范围外的新发现时打断业主。
> 前作：[`../2026-08-28-gate-authority/program.md`](../2026-08-28-gate-authority/program.md)
> 的 s1b–s5 **移交至此**（该文件将加指针，单一真相在本文）。

## 0. 证据底座

全部依据来自：`AUDIT-2026-08-28-gate-authority.md`（第五轮审计，逐条可复现）、
`HANDOFF-2026-08-28-runlog.md`（第四轮 run log 实证）、本会话两轮架构评审与三轮 plan 挑战、
以及更早的流程耗时分析。关键数字：18 本账本 4 张 receipt（22%）、测试执行作废 56%、
`record-challenge-control` 失败率 50%（四动作全中 7/3/2/2）、挑战循环与 receipt **零交集**。

## 1. 全量优化点（24 项，按波次排布）

### W1 · 独立 bug 修复（无行为争议，全可红测先行）

| # | 点 | 根据 | 动作 |
|---|---|---|---|
| 1 | `_stats_last_activity` 读错字段 | `integrity.chain` 是 str（`log` 才是 list），`isinstance(e,dict)` 恒 False，**永远**走 mtime 兜底——换机/CI 后时间轴失真 | 改读 `integrity.log`，mtime 仅兜底 |
| 2 | `gate_usage_report.py` Windows GBK 静默失败 | 实测：读线程 `UnicodeDecodeError` 崩掉但脚本输出三段空报告——**规则退休的唯一数据源在 Windows 上永远显示"（无）"**，规则集因此只进不出 | 子进程强制 UTF-8 + 读失败必须报错 |
| 3 | 哈希正则 6 处重复、`:4032` 拼写分叉 | 同一 `^[0-9a-f]{64}$` 抄 6 遍，一处写成 `[a-f0-9]` | 收敛为一个常量 |
| 4 | 链长下界盲区 | `record-phase-transition` / `record-plan-defect` 写的事实不在 `expected_chain_length`——删一条不会被长度检查发现 | 补进枚举 + `ChainLengthInvariantTestCase` 补行 |
| 5 | `compile-manifest` 13% 失败率根因 | 52 次调 7 次失败，根因未查 | 先查 rollout 日志定性，再按性质修（报错手感 or 真 bug） |

### W2 · s2：挑战循环接上成绩单（新增阻塞码，中风险）

| # | 点 | 根据 | 动作 |
|---|---|---|---|
| 6 | `PLAN_CHALLENGE_UNRESOLVED` 进 finalize | 4 张 receipt 全发在无挑战循环的账本上；`validate()` 零引用 `challenge_loops`——纯自觉的门 | 存在循环但非 CONVERGED 且无批准出口 → 不发 receipt |
| 7 | 三个 `LOOP_*` 死码处置 | `LOOP_LIMIT_EXCEEDED`/`LOOP_REGRESSION`/`LOOP_NO_PROGRESS` 无任何产生点 | 随 #6 激活或按登记纪律正式退休 |
| 8 | `GATE_REGISTRY_DISCIPLINE` 第四问 | 每次事故同形状：门堵死出口→换目录→全废 | config.md 加"这道门拒绝时合法出口是什么？答不出不许合入" |
| 9 | 补 `assurance-contract.json` | 全仓 0 个；本 program 三轮挑战因此**一条都入不了账**（gate:4264 要求绑定） | 出模板 + 为本 program 冻结一份，s2 起挑战真正走账本 |

### W3 · s3：decision 原语（动判定路径，高风险，**决策点 A**）

| # | 点 | 根据 | 动作 |
|---|---|---|---|
| 10 | 统一 `decision` 原语 | 四个控制动作**全部**从里面反锁（失败 7/3/2/2）；正解就在隔壁函数（`re-attest`/`acknowledge`：入口无条件+hash，权力在后果）；`applicability` 已自证"留痕代替禁止"更严 | 入口无条件（hash 必填），validate 时消费；`effect` 枚举复用 `CANONICAL_ORDER`；waivers 强制进 receipt 与 render |
| 11 | `_has_control` `>=` 预授权漏洞 | 放宽入口后可构造"批准早于要求"，绕过 `test_control_events_cannot_be_pre_authorized` 守的语义 | 收紧为 `>` 或按 `initiator` 区分满足性 |
| 12 | consolidated 连锁按快照区分 | 记一次 scope-change-approved 即强制下轮全量 8 键 coverage——用户拍完板反而要付一轮全审（正是"范围变了为什么全审"的病） | acceptance/contract 快照**真的换了**才强制 consolidated；只批准处置不触发 |
| 13 | acceptance/contract 替换特权拆分 | "记录事实"和"换掉唯一真相来源"共用一个入口；且 validate 从不复验运行级 acceptance hash，换约在 finalize 层不可见 | 独立命令 + 强制 consolidated |
| 14 | clustered loop 一次性锁 | `record-challenge-clusters` 仅限第 1 轮、synthesis 一次性——architecture reset 后既不能重聚类也不能重合成，**文档禁止的"开新 loop"是状态机唯一留下的出路** | reset 后允许重聚类/重合成（带控制事件绑定） |

### W4 · s4+s5：出口与指路（**决策点 B**）

| # | 点 | 根据 | 动作 |
|---|---|---|---|
| 15 | `fail` 粘性改非粘性 | `blocked` 先例 2026-08-09 已拆，注释论证逐字适用；现设计下同强度证据"留痕"vs"洗账"二选一，**奖励洗账**——56% 作废的直接来源 | fail 可被其后合规 root pass 解除，硬门一条不少；`SIBLING_RUN_UNRESOLVED` 降级为对账门 |
| 16 | `status` 子命令 | 不存在的子命令被敲：`status`12 次 `skills`23 次 `report`4 次；"我在哪、能做什么"无处可问——入口无条件化后它是必需的另一半 | 输出当前 state/合法动作集/前置条件；argparse 敲错给近似建议 |

### W5 · s1b+s1c：refusal 数据链路补全

| # | 点 | 根据 | 动作 |
|---|---|---|---|
| 17 | s1b 间隔配对指标 | `CONTROL_NOT_REQUIRED` 拒后中位 4.9 分钟开新 run vs `SCHEMA_INVALID` 368 分钟——分布即结论 | **前置**：仲裁"当前仓库"四定义（--root/--run-dir/ledger repo_root/cwd）；机制先行，参数标注"待真实数据校准"（见决策点 C） |
| 18 | s1c 导出+脱敏 | 跨机器数据不可见是本轮全程的痛 | `export-refusals`；脱敏须过 Windows 三形态（分隔符归一/含空格路径） |
| 19 | 轮次门退休评审 | 3/5/8/15 在 `PLAN_ITERATIONS:1` 下结构上不可达 | 用 s1b 数据跑 `stats`+usage report 定夺，**不预设结论** |

### W6 · 流程与文档减负（更早的耗时分析，实证充分）

| # | 点 | 根据 | 动作 |
|---|---|---|---|
| 20 | 真人覆盖账本表自动化 | phase-4 ①c 要求人肉抄一张账本里全有的表；"Markdown 不是 authority"是仓库自己的原则 | `render` 生成，人只填业务终态/quality_bar 结论 |
| 21 | 热冷路径分离 | phase 文档 1178 行是"一轮 15–25 万 token"主源；病根解释属冷路径 | phase-2/phase-4 的病根段外迁 rationale.md，热路径只留必做项 |
| 22 | FLOW_TIER 判档入账 | 判 LEAN 使三样合法消失却不留痕；run-001 判档理由"无删改 hunk"实测失实（40 行删除）只靠人肉发现 | manifest 加 `flow_tier{value,rationale,evidence_basis}`；`FLOW_TIER_UNDECLARED`/`BASIS_FALSE`（basis 可机器复核）；input_sensitive=true 与 LEAN 冲突直接拦 |
| 23 | phase 遥测必记 | 18 本账本仅 9 本有 phase 事件；run-001 `user_wait declared 896.9min/measured 0`——LEAN 压缩效果永远无法评估 | phase-start/end 从自愿升必记（finalize 检查配对已存在，补"必须存在"） |

### W7 · 发布与回写

| # | 点 | 动作 |
|---|---|---|
| 24 | 发布 + 文档回写 | bump 版本→推→两侧 `claude plugin update`；CLAUDE.md/PROTOCOL/HANDOFF 同步；memory 更新。发布节奏见决策点 C |

## 2. 决策点（已于 2026-08-29 由业主一次拍完）

- **A（W3 防伪造门 / decision 原语）**：✅ **做**。入口无条件但 hash 必填、waivers 强制进
  receipt——业主经大白话解释后批准（"改（推荐）"）。
- **B（W4-15 fail 非粘性）**：✅ **做**。同样严格标准下订正翻盘、失败史留档不洗掉——
  业主批准（"改（推荐）"）。
- **C（发布节奏）**：**不发布**。业主原话："不要再提发布的事情了，等我做完，再会让你发布的。"
  W7 的发布动作移除，只保留文档回写；W5-17/19 的数据校准显式标注"待发布后有真数据再校准"。
- **D（查证型小项）**：✅ **允许砍、留记录**。挖出大坑时写明根因、列入未做清单、主线不停。

## 3. 执行纪律（继承 s1a 实证有效的做法）

红测先行入 git 历史 → 实现 → 全套测试真 rc 校验（≥300s 超时）→ 每波一批 commit →
波间不请示。子代理挑战只用于 W3（唯一的高风险波），其余靠红测+全量回归。
每波完成后 push（认证已固化）。W2 起挑战循环走真账本（#9 补齐后）。

## 4. 完成判据

程序级唯一指标不变：**receipt 覆盖率（receipt/init）上升**——在 s1a 落地后的同批数据内计算。
辅以：24 项逐项有 commit + 测试证据；未做的项有显式记录与理由，不静默消失。
