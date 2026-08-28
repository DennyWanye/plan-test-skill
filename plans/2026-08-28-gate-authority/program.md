# Program：让门禁的记录与裁决分离（2026-08-28 起）

> 证据基础：[`AUDIT-2026-08-28-gate-authority.md`](../../AUDIT-2026-08-28-gate-authority.md)。
> 本文只定路线与切分，不含实现细节；每个 slice 的 AC 与技术设计在 `slices/<id>/` 下。
> **本文不是执行授权**，每个 slice 开工前需业主确认。

---

## 1. 主要矛盾

**记录职能与裁决职能寄生在同一次写入上。**

`die()`（`plan_test_gate.py:193`）只做两件事：打到 stderr、退出。**160 处调用点，
没有一处向账本写入"我拒绝了什么"。** `cmd_record_challenge_control`（:4893）
在 append 之前算状态，不符即 `die` ——于是**"这件事发生了"这个事实，因为
"现在不该发生"而无法被记录**。

账本记的不是"实际发生了什么"，而是"门允许发生了什么"。

**判据**（为什么这是主要矛盾，而不是"门太严"）：若矛盾真是"严 vs 松"，三条机制完全不同的
成因应导向三种不同的规避方式。实测是**多因一果**——全部导向"换个 run-dir 重来"，
作废率 56%。卡点不在任何一道具体的门上，在所有门共用的那个结构。

**最硬的佐证**：这个系统要发现自己 56% 的作废率，得去挖**另一台机器、另一批项目**的
389 MB 会话日志。一个宣称"账本是唯一真相来源"的系统，从自己的账本里看不见自己最大的
失效模式。

## 2. 路线的总方向

把权力从**入口的准入检查**搬到**机器推导的后果**上。

这不是新发明——本仓已经做对过五次，就在同一个文件里：

| 命令 | 入口 | 权力在哪 |
|---|---|---|
| `re-attest`（:2710） | 无条件 | 机器判 doc-only/behavioral，behavioral 强制全量重测 |
| `resolve-audit-finding`（:2830） | 无条件 | 必须绑证据 ID |
| `reset-plan-defects`（:4022） | 无条件 + hash | 旧记录归档，不删除 |
| `acknowledge`（:3357） | 无条件 + hash | 本 run 永久 `RUN_ABANDONED` |
| `record-challenge-round`（:4454） | 无条件 | 落账后用 exit code 表态 |
| **`record-challenge-control`（:4891）** | **写前拦** | **后果为空** |

`re-attest` 的 docstring 把道理写明白了：**"本命令不是把红灯按绿"**。

`applicability`（:143）是同一思路的另一次成功——从"判一句不适用就让四道门合法消失且无人
知晓"改为"判不适用合法，但理由留痕、事后可追责"。**它既没加门也没开口子，结果是更严了。**

## 3. Slice 划分与依赖

按 `config.md` 的 `RELEASE_UNIT_LIMITS`（8 条 MUST AC / 10 个 Task / 2000 行 plan /
3 个高风险子系统）拆分。**依赖是单向的，不得跳步**：

```
s1 refusal ledger  ──→  s2 挑战循环进判定  ──→  s3 decision 原语
   (纯增量记账)          (新增阻塞码)           (统一四动作 + 三处 waiver)
        │                                              │
        └──────────→ 提供"改动有没有效"的度量 ←─────────┘
```

| slice | 内容 | 行为变更 | 风险 | 状态 |
|---|---|---|---|---|
| **s1a** | 只记录：`die()` 落**原始**记录到用户级全局单文件 + `stats` 计数。不分仓库、不配对、不导出、不脱敏 | **零**（不改判定；不向被测仓库写任何文件） | 低 | 📋 已写，待用户 review |
| **s1b** | 「拒绝 → 新 run」间隔配对指标。**前置**：仲裁"当前仓库"的四种定义（`--root` / `--run-dir` / ledger `repo_root` / cwd）；配对规则用 s1a 真实数据定 | 零 | 中 | 未写（依赖 s1a 数据） |
| **s1c** | 显式导出 + 脱敏（Windows 分隔符归一、含空格路径） | 零 | 低 | 未写 |
| **s2** | 挑战循环进 `finalize`：新增 `PLAN_CHALLENGE_UNRESOLVED` | 有（新增阻塞码） | 中 | 未写 |
| **s3** | 统一 `decision` 原语；四个控制动作 + `acknowledge` + `reset-plan-defects` + specialist waiver 收敛为其特例 | 有（改判定路径） | 高 | 未写 |
| **s4** | `fail` 粘性按 `blocked` 先例改为可被合规 root pass 解除 | 有 | 中 | 未写 |
| **s5** | `status` 子命令 | 无 | 低 | 未写 |

> **s1 拆分记录**（2026-08-28）：原 s1 经三轮挑战触发 `SCOPE_AUDIT_REQUIRED`——
> 三轮 P0/P1 绝大多数来自仓库身份/配对/脱敏这些附加职能，而非"记录"本身。
> 业主批准拆为 s1a/s1b/s1c，控制事件与 findings 去向见
> `slices/s1-refusal-ledger/SCOPE-AUDIT-2026-08-28.md`（该目录已归档）。

### 为什么 s1 必须最先

**没有 s1，后面每一个 slice 上线后都无法知道有没有效。** 拒绝不留痕 → `stats` 取不到
数据（其 docstring 自陈"诊断没有历史留痕"，:3508）→ 下一轮仍要去挖另一台机器的日志。

病灶指标分两步拿：**s1a 先给按码/按命令的计数**（哪道门拦得最多），
**s1b 再给「拒绝 → 下一个新 run」的间隔分布**（哪道门拦完之后紧跟着换目录）。
后者是 `GATE_REGISTRY_DISCIPLINE` 退休评审真正需要而现在拿不到的数据。

> **不是"固定窗口 + 转化率"**——初稿如此设计，实测后放弃：真实间隔跨四个数量级
> （P25=0.7 / P50=64 / P90=877 分钟），任何单一阈值要么漏一半要么误报；
> 而按码分组后信号自明（`CONTROL_NOT_REQUIRED` 中位 4.9 分钟
> vs `SCHEMA_INVALID` 中位 368.8 分钟）。s1b 的配对规则**须用 s1a 攒的真实数据重定**，
> 不沿用上述 rollout 估算（口径不同）。

### 为什么 s2 排在 s3 之前

审计发现 4 张 receipt **全部发在没有挑战循环的账本上**，跑过挑战循环的 7 本账本一张
receipt 都没有。在挑战循环进入 `finalize` 判定之前，围绕它的入口松紧（s3）**改与不改，
receipt 一张不多一张不少**——那是在调一道自愿门的手感。

## 4. 明确排除的方案

**不实施第四轮 `HANDOFF-2026-08-28-runlog.md` §3.4 的单点放宽。** 四条理由见审计文档 §5，
摘要：

1. 挑战循环不进 `validate()`，放宽入口不改变任何 receipt；
2. 失败不集中在一个动作——`scope-change-approved` 7 / `architecture-reset` 3 /
   `user-review` 2 / `scope-audit` 2，**四个动作全中**，单点放宽只解决一半；
3. 会引入真漏洞：`_has_control`（:4295）用 `>=`，放宽后可构造预授权，
   绕过 `test_control_events_cannot_be_pre_authorized`（`test_plan_test_gate.py:2562`）守的语义；
4. 自带副作用：会让 `major_change=True`（:4186），**强制下一轮 consolidated 重做完整
   8 键 coverage**——很可能是下一个"被拒→换目录"的候选。

> ⚠️ 承接第 3 条：`scope-audit` / `user-review` 的 `_has_control` 用默认 `minimum_round=0`，
> **一条预记录事件会永久关闭该项升级**。它们在 s3 里只能走 `initiator` 区分方案，
> **绝不能照抄"任意状态可记"**。

## 5. 验收判据（适用于本 program 每一个 slice）

**不看新增了几道门，看 receipt 覆盖率（receipt / init）有没有升。**

理由：18 本账本 4 张 receipt（22%）意味着 78% 的交付发生在门禁之外，而门对此一无所知。
继续加强门，提高的是那 22% 的严格性，降低的是覆盖率，**总保障水平可能是下降的**。

> 注意口径：审计文档 §3.2 已指出，rollout 日志的 `init` 115 次与 18 本账本**来自不同机器**，
> 不可相除。本判据要求在**同一批数据内**计算。s1 落地后才具备这个条件。

## 6. 建议加进 `GATE_REGISTRY_DISCIPLINE` 的第四问

现有三问（防哪个诊断码 / 防哪条实测逃逸 / 复审日期）之外加：

> **"代理在这道门拒绝它的那个状态下，合法出口是什么？"** 答不出来的门不许合入。

依据：本仓每一次事故都是同一个形状——门堵死合法出口 → 代理换 run-dir → 前面测试全废。
`config.md:265` 待改，建议随 s2 一并提交。

## 7. 待办：本 program 自己缺 `assurance-contract.json`

第 3 轮 closure 的 advisory（首轮即可发现、被迫核对时才暴露）：`phase-A-acceptance.md:19-26`
要求 acceptance 同目录冻结 `assurance-contract.json`，全仓实测 **0 个**（历史 slice 也没有）。
直接后果：`plan_test_gate.py:4264-4272` 要求 in-scope P0/P1 绑定冻结快照内的 assurance ID，
**本 program 三轮挑战的任何 finding 都无法 `record-challenge-round` 入账**——
挑战只能像现在这样以 markdown 留痕，恰是审计文档 §4.2「挑战循环与 receipt 不相交」的活例。
处置：s1a 不阻塞于此；**s2 动工前为本 program 补一份 assurance-contract.json**，
让 s2/s3 的挑战循环第一次真正走进账本。
