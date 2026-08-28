# 审计：挑战循环的门禁权威性（第五轮，2026-08-28）

> **这份文档是给下一位代理审计用的，不是执行授权。**
> 本文生成时 HEAD：`f77cf62`（其前为 `0a53b8b`）。工作树有未提交改动，见 §8。
> 前四轮背景见 `HANDOFF.md` 与 `HANDOFF-2026-08-28-runlog.md`。
>
> **与前四轮的区别**：第四轮的结论来自真实 run log 统计；本轮在此基础上做了两件事——
> **复核**（逐条验证第四轮的转述数字与代码论断，修正了两处）与**上溯**
> （从"三条成因"上升到共同的结构根因）。本轮**推翻了第四轮 §3.4 的建议方案**，理由见 §5。

---

## 0. 一句话结论

第四轮把 `CONTROL_NOT_REQUIRED` 定位为"第三条通向换 run-dir 的成因"，建议放宽
`scope-change-approved` 的状态检查。**本轮验证后认为该方案不应实施**：
整个挑战循环**根本不进 `finalize` 的判定路径**，改与不改，receipt 一张不多一张不少。
真正的结构根因是**记录职能与裁决职能寄生在同一次写入上**——拒绝不留痕，于是账本记的不是
"实际发生了什么"，而是"门允许发生了什么"。

---

## 1. 怎么复核本文每一条（先读这节）

**本文所有结论都可复现。** 下表给出逐条的验证方法。凡我未独立复算的，在 §7 显式列出。

| # | 结论 | 复核方法 |
|---|---|---|
| 1 | `die()` 不向账本写任何东西 | `sed -n '193,197p' skills/plan-test/scripts/plan_test_gate.py` |
| 2 | `die()` 有 161 处调用点 | `grep -c 'die(' skills/plan-test/scripts/plan_test_gate.py` |
| 3 | `validate()` 完全不引用 `challenge_loops` | `awk 'NR>=1335 && NR<=1905 && /challenge\|loop/' <gate.py>` → 应为空 |
| 4 | 三个 `LOOP_*` 是死码 | `grep -n 'LOOP_LIMIT_EXCEEDED' <gate.py>` → 只有 `CANONICAL_ORDER` 那一行 |
| 5 | 哈希正则 6 处重复且拼写分叉 | `grep -n '\[0-9a-f\]{64}\|\[a-f0-9\]{64}' <gate.py>` |
| 6 | `record-challenge-round` 无写前状态检查 | `sed -n '4454,4545p' <gate.py>`，对照 `sed -n '4891,4915p'` |
| 7 | `fail` 粘性未拆而 `blocked` 已拆 | `sed -n '724,745p' <gate.py>` 读 docstring |
| 8 | 账本统计（18 本 / 4 receipt / 56% 作废等） | §2.2 的解包步骤 + §2.3 的脚本 |
| 9 | rollout 统计（1888 次调用、失败率等） | §2.4 的脚本 |
| 10 | 4 本 receipt 账本零挑战循环 | §2.3 脚本第二段 |

`<gate.py>` = `skills/plan-test/scripts/plan_test_gate.py`（本轮 HEAD 时 5676 行）。

---

## 2. 证据基础

### 2.1 两份数据不可互证（沿用第四轮 §1.2，本轮再次确认）

| | 账本 collection | rollout 日志 |
|---|---|---|
| 体积 | 5.8 MB | 389 MB |
| 内容 | 18 本真实账本 + gate-checks + inventory | 83 个 codex rollout 会话 jsonl |
| 项目 | `agentOS`(17)、`DGXSpark`(1) | `simple_harness`、`AIPhone`、`web3wallet` 等 |
| 机器 | 一台 | **另一台** |
| 交集 | **无** | **无** |

**任何把两边数字并列的推断都是跨样本的**，本文引用时都会标注。特别注意：
§2.4 的 `init` 115 次与 §2.3 的 18 本账本**不是同一批**，不能相除当作漏斗率。

### 2.2 原始数据位置与解包

```
C:\projects\plan-test\run log\
  plan-test-run-collection-20260828.zip     5.8 MB
  plan-test-raw-rollout-logs-2026-08-28.zip 389 MB
```

WSL 路径 `/mnt/c/projects/plan-test/run log/`。**本机无 `unzip`，用 python zipfile。**

**Windows 侧解包的坑（本轮踩到）**：zip 里的 `__MACOSX/` 条目路径超过 Windows 长度限制，
`extractall` 会中途抛 `FileNotFoundError [WinError 206]`。必须跳过它并解到短路径：

```python
import zipfile
z = zipfile.ZipFile(r'C:\projects\plan-test\run log\plan-test-run-collection-20260828.zip')
for n in z.namelist():
    if not n.startswith('__MACOSX'):
        z.extract(n, r'C:\rl')      # 短路径，不要用 scratchpad 的深层目录
```

**另一个 Windows 坑**：`json.load(open(...))` 默认用 GBK 解码，中文账本直接抛
`UnicodeDecodeError`。一律 `io.open(p, encoding='utf-8')`。

### 2.3 账本统计脚本

```python
import json, io, glob, os
# 版本分层：只统计 schema 1.5.0（与当前 gate 一致）
for p in glob.glob('raw/**/plan-test-run.json', recursive=True):
    d = json.load(io.open(p, encoding='utf-8'))
    if str(d.get('schema_version')) != '1.5.0':
        continue
    rd = os.path.dirname(p)
    has_receipt = os.path.exists(os.path.join(rd, 'gate-receipt.json'))
    loops = d.get('challenge_loops') or []
    # 按 verification 目录分组，即可得到「重开链」与作废量
    print(d.get('run_id'), len(d.get('runs', [])), len(d.get('evidence', [])),
          len(loops), has_receipt)
```

### 2.4 rollout 统计脚本

沿用第四轮 §1.3 的抽取骨架，**纪律不变：只认行首 `ERROR: <CODE>:` 才算真实触发**
（代理 grep gate 源码会让诊断码字符串出现在输出里，制造假阳性）。本轮在其上增加了
"按子命令归类"：

```python
import re
SUB = re.compile(r'plan_test_gate\.py["\']?\s+([a-z][a-z-]+)')   # 取子命令
ERR = re.compile(r'^ERROR: ([A-Z_]+):', re.M)                    # 只认行首
# 对每次 (cmd, out) 配对：SUB.search(cmd) 归类，ERR.search(out) 判失败
```

> **口径局限（重要，下一位注意）**：argparse 的 "invalid choice" 报错**不带 `ERROR:` 前缀**，
> 所以本口径统计不到"敲了不存在的子命令"。§4.6 里 `status` 12 次、`report` 4 次
> 显示"失败 0 次"，实际是**全部失败但未被计入**。要统计它们需另加 `usage:` / `invalid choice`
> 匹配。

### 2.5 版本分层（第四轮未做，本轮补）

| schema | 账本数 | 时间 | 说明 |
|---|---:|---|---|
| 1.5.0 | 16 | 08-24 ~ 08-28 | 与当前 gate `SCHEMA_VERSION` 一致 |
| 1.4.0 | 2 | 08-18 | `tag-web-crud-001/002`，本文统计已剔除 |

**gate-checks/ 是收集时（08-28）用当时 gate 重跑的**，不等于历史 finalize 结果。
`TESTED_RUNTIME_MISMATCH` 18/18 全中属工作树漂移噪声；本文统计诊断分布时剔除了
`TESTED_RUNTIME_MISMATCH` / `ACTIVE_RUN_MISMATCH` / `RECEIPT_STALE` 三个漂移码。

---

## 3. 对第四轮转述数字的复核（两处修正）

第四轮部分数字为转述，本轮独立复算，结果如下。

### 3.1 ✅ 对上的

| 指标 | 第四轮 | 本轮复算 | 
|---|---|---|
| gate 调用总数 | 1888 | **1888** |
| `record-challenge-control` 调用 | 28 | **28** |
| 其中失败 | 14 | **14**（全部 `CONTROL_NOT_REQUIRED`） |
| `finalize` 调用 | 39 | **39** |
| 被丢弃账本里的测试事实 | 75 条 | **75**（独立路径算出，见 §4.1） |
| 被丢弃账本里的证据 | 142 份 | **142** |

> 75 / 142 这组数字是本轮从账本 collection 独立算出的，与第四轮从另一路径得到的数字
> 完全一致。**两条独立路径同一组数字，可作硬事实使用。**

### 3.2 ❌ 需要修正的两处

**修正一：`init` 是 115 次，不是 137 次。**

复算：`init` 115 次（报错 1 次），`finalize` 39 次。第四轮 §5.2 记的 137 偏高。
**且必须记住**：这 115 次来自 rollout 日志（一台机器），18 本账本来自另一台，
**两者不能相除**。第四轮把"137 vs 39"与"18 本 4 receipt"并列，是跨样本并列。

**修正二（改变判断方向）：失败的 14 次不是集中在 `scope-change-approved`。**

第四轮 §3.1 记"其中 13 次是 `--action scope-change-approved`"。复算的实际分布：

| `--action` | 失败次数 |
|---|---:|
| `scope-change-approved` | **7** |
| `architecture-reset` | **3** |
| `user-review` | **2** |
| `scope-audit` | **2** |

**四个控制动作全部在失败。** 这不是 `scope-change-approved` 一个动作的毛病，
是四个动作共有的结构问题——直接支撑 §5 推翻单点放宽方案的判断。

---

## 4. 本轮核心发现

### 4.1 重开链的作废量：135 次执行作废 75 次（56%）

只统计 schema 1.5.0：

| slice | run 数 | 执行数 | 作废 | 损耗 |
|---|---:|---:|---:|---:|
| `s1-relay-foundation` | 6 | 64 | 45 | **70%** |
| `s2-mcp-room` | 3 | 18 | 18 | **100%** |
| `s1-lan-relay` | 4 | 36 | 12 | 33% |
| `dgx-200k-model-matrix` | 1 | 17 | 0 | 0% |
| **合计** | | **135** | **75** | **56%** |

证据侧：产出 281 份，作废 142 份（51%）。

重开原因**写在账本 note 里**，不需推断：

- run-003 开场：`Successor run corrects unsupported custom evidence identities`
- run-004 开场：`Clean successor verification after run-003 root-fail contamination`

即：**一次记账失误 / 一次被污染的执行，整本作废，前面 20 次执行全部白跑。**

### 4.2 ⭐ 挑战循环与 receipt 是两个不相交的集合

**这是本轮最重要的发现，第四轮未涉及。**

```
拿到 receipt 的账本: 4 本
  其中跑过挑战循环的: 0 本

跑过挑战循环的账本: 7 本
  其中拿到 receipt 的: 0 本
```

轨迹很清楚，以 `pair-relay-s1` 为例：run-001/002 跑挑战循环（CONVERGED）→
换到 run-003/004/005/006 做验证测试 → run-006 出 receipt，**而它没有任何挑战循环记录**。

**结论：「计划被严格挑战过」这件事，从来没有进过任何一张成绩单。**

### 4.3 ⭐ 代码层面的原因：`validate()` 不看挑战循环

| 事实 | 位置 | 复核 |
|---|---|---|
| `validate()` 函数体 1335–1905（下一个 `def` 是 1905 `compute_state`）**零引用** `challenge_loops` / `loop` | `<gate.py>:1335` | `awk 'NR>=1335&&NR<=1905&&/challenge\|loop/'` → 空 |
| `challenge_loops` 全文件只被读 4 处：schema 校验、链长计算、`_challenge_loop` 查找、`show-loop-history` | — | grep |
| `LOOP_LIMIT_EXCEEDED` / `LOOP_REGRESSION` / `LOOP_NO_PROGRESS` **无任何产生点** | `<gate.py>:169` | 各只 1 处引用 = 声明表本身 |
| 四个 loop 状态（`SCOPE_AUDIT_REQUIRED` 等）只作为字符串 print，从不作为 `DIAG` 发出 | — | grep |

**所以挑战循环的 authority 完全靠"代理自愿调用并尊重 exit code"支撑。**
这与 `SKILL.md` 核心原则"机器门是唯一完成 authority"直接冲突——它是一道纯自觉的门。

### 4.4 ⭐ 结构根因：记录职能与裁决职能绑在同一次写入上

```python
def die(msg, code=2):
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)
```

**161 处调用点，没有一处向账本写入"我拒绝了什么"。**

`cmd_record_challenge_control`（:4893–4902）在 append 之前算 `_challenge_state`，
不符即 `die`。于是**"这件事发生了"这个事实，因为"现在不该发生"而无法被记录**。

判据（为什么这是主要矛盾而非"门太严"）：如果矛盾真是"严 vs 松"，三条机制完全不同的成因
应导向三种不同的规避方式。实测是**多因一果**——全部导向"换个 run-dir 重来"。
说明卡点不在任何一道具体的门上，在所有门共用的那个结构。

**自我认知失效是最硬的佐证**：这个系统要发现自己 56% 的作废率，得去挖另一台机器、
另一批项目的 389MB 会话日志。一个宣称"账本是唯一真相来源"的系统，从自己的账本里
看不见自己最大的失效模式。`cmd_stats` 的 docstring 自己写着"诊断没有历史留痕"（:3508）。

### 4.5 ⭐ 正解已在同一文件里，只是没贯彻

| 命令 | 入口 | 权力体现在哪 |
|---|---|---|
| `re-attest`（:2710） | **无条件** | 机器判 doc-only/behavioral，behavioral 强制全量重测 |
| `resolve-audit-finding`（:2830） | **无条件** | 必须绑证据 ID；`required_retest` 须有晚于导入点的 root PASS |
| `reset-plan-defects`（:4022） | **无条件 + hash** | 旧记录归档进 history，不删除 |
| `acknowledge`（:3357） | **无条件 + hash** | 本 run 永久 `RUN_ABANDONED`，永不出 receipt |
| `record-challenge-round`（:4454） | **无条件** | 落账后用 exit code 表态（:4538–4541） |
| **`record-challenge-control`（:4891）** | **写前拦** | **后果为空（见 4.3）** |

`re-attest` 的 docstring 把道理写明白了：**"本命令不是把红灯按绿"**——
入口无条件，权力在机器推导的后果上。

**两种哲学并存于同一文件、同一循环、相邻两个函数。** 结构根因就在这道缝里。

另一个已自证的先例是 `applicability`（:143–152）：从"判一句不适用就让四道门合法消失且无人
知晓"改为"判不适用合法，但理由留痕、事后可追责"。**它既没加门也没开口子，结果是更严了。**

### 4.6 附：全子命令失败率（rollout 样本，1888 次调用）

| 子命令 | 调用 | 报错 | 失败率 |
|---|---:|---:|---:|
| `record-challenge-control` | 28 | 14 | **50%** |
| `record-challenge-synthesis` | 25 | 10 | **40%** |
| `record-challenge-round` | 120 | 25 | 21% |
| `compile-manifest` | 52 | 7 | 13% |
| `start-challenge-loop` | 47 | 4 | 9% |
| `audit` | 11 | 1 | 9% |
| 其余 ≥3 次的子命令 | — | — | ≤3% |

**失败高度集中在挑战层**（前三名全是挑战循环命令），而挑战层恰恰是唯一不进 receipt 的部分。

不存在的子命令被反复敲：`skills` 23 次、`status` 12 次、`report` 4 次、`testcase` 3 次。
（受 §2.4 口径局限，它们的失败未计入上表。）

### 4.7 真实触发过的诊断码只有 15 种

行首 `ERROR:` 口径，1888 次调用里触发过的全表：

```
SCHEMA_INVALID 22        CONTROL_NOT_REQUIRED 14   CLOSURE_FINDING_COVERAGE_INVALID 7
LEDGER_TAMPERED 5        ACCEPTANCE_CHANGED 5      PLAN_HASH_MISMATCH 4
SYNTHESIS_SPIKE_REQUIRED 3  PLAN_BASE_HASH_INVALID 3  PRIMARY_CHALLENGE_REQUIRED 3
TESTCASE_INVENTORY_INVALID 3  EVIDENCE_CONTRACT_INVALID 2  ACCEPTANCE_REQUIRED 1
TESTCASE_LOCK_MISMATCH 1  TESTCASE_REVISION_MISMATCH 1  RESOLUTION_EVIDENCE_REQUIRED 1
```

`CANONICAL_ORDER` 有 55 个诊断码。**注意：这不能直接推出"40 个该退休"**——
威慑型的门本来就不该触发（代理知道有门所以不违规），与真·死码需要分开判。
但 §4.3 的三个 `LOOP_*` 是**结构上不可能触发**（无产生点），属于后者。

---

## 5. 为什么推翻第四轮 §3.4 的方案

第四轮建议：放宽 `scope-change-approved` 的状态检查，允许任意状态记录（哈希要求不变）。

**本轮结论：不应按原样实施。** 四条理由，全部可复核：

1. **改与不改，receipt 一张不多一张不少**（§4.3）。挑战循环不进 `validate()`，
   放宽入口只是调一道自愿门的手感。
2. **失败不集中在这一个动作**（§3.2 修正二）。7/3/2/2 四个动作全中，
   单点放宽只解决一半。
3. **会引入一条真漏洞**：`_has_control`（:4295–4297）用 `>=` 而非 `>`。放宽后可构造
   预授权——先记 `scope-change-approved`（`after_round = len(rounds)`，:4914），
   再记 `scope-audit --outcome scope-change`，两者 `after_round` 相同，
   `_has_control` 命中 → `USER_SCOPE_APPROVAL_REQUIRED` 永不出现。
   仓库现有用例 `test_plan_test_gate.py:2562 test_control_events_cannot_be_pre_authorized`
   守的正是这条语义。
   > ⚠️ **由此推论**：`scope-audit` / `user-review` **绝不能照抄放宽**——
   > 它们的 `_has_control` 用默认 `minimum_round=0`，一条预记录事件会永久关闭该项升级。
4. **自带副作用**：记一次 `scope-change-approved` 会让 `major_change=True`（:4186–4194），
   **强制下一轮 `consolidated`**，而 consolidated 要求重做完整 8 键 coverage（:4198–4202）。
   放宽后这个动作会出现在 `CONVERGED` 状态，等于用户拍完板、代理被要求重跑一次全覆盖复核
   ——**这很可能是下一个"被拒→换目录"的候选**。
   同时 `CONSOLIDATED_REVIEW_UNAUTHORIZED`（:4195）从此形同虚设。

> 第 3、4 两条是子代理从代码推出、**未实测**。实现前应先写失败用例验证推导无误。

---

## 6. 建议路线（按依赖排序，非授权）

### P0 — 必须先做，否则任何改动都无法验证效果

1. **`die()` 记 refusal**。能定位 run-dir 时，先向账本追加
   `{type:"gate_refusal", cmd, code, state, at}` 再退出。
   **建议单独存 `refusals[]` 且不进 `facts_digest`**——否则每次误操作都改变链值，
   还给了"用垃圾命令灌链"的空间。
   收益：`stats` 从"今天这些门各拦着谁"升级为"历史上拦过多少次、拦掉之后代理干了什么"，
   并得到一个直接的病灶指标——**refusal → new-init 转化率**。

2. **挑战循环进 finalize 判定**：新增 `PLAN_CHALLENGE_UNRESOLVED`——
   存在挑战循环但既非 `CONVERGED`、又无经批准的出口（`acknowledge` / 带 hash 的 BLOCKED 升级），
   则不发 receipt。
   **§4.2 的数据说明这是最高优先级**：4 张 receipt 全部发在没有挑战循环的账本上。
   顺带把三个死码要么激活、要么按 `GATE_REGISTRY_DISCIPLINE`（`config.md:265`）退休。

### P1 — 用普遍机制替代单点开口

3. **统一 `decision` 原语**。入口无条件（只校验哈希格式、rationale 非空、effect 在枚举内），
   后果由 validate 时消费。
   - `effect` 枚举**直接复用 `CANONICAL_ORDER`**，保证"人能豁免什么"与"门能拦什么"
     永远同构，不会各长各的——这本身就是防"只进不出"的结构性约束。
   - `initiator`：`gate-requested` / `user-initiated` / `agent-proposed`。
   - 命中时该诊断码由 error 降为 advisory，**并强制出现在 receipt 的 `waivers[]` 与 render 里**。
   - 核心不变量：**豁免不隐身，变成公开账目。** 今天这些偏离是"换个 run-dir 无声消失"，
     改后变成成绩单上的一行。**不是放松，是把不可见变成可见。**
   - 四个控制动作 + `acknowledge` + `reset-plan-defects` + specialist waiver 收敛为其特例；
     六处哈希正则收敛为一处（含修掉 :4032 的拼写分叉）。

4. **`_has_control` 的 `>=` 收紧为 `>`**，或按 `initiator` 区分满足性：
   只有 `gate-requested` 的事件才算"满足了门的要求"，`user-initiated` 的只是被如实记下。
   现有用例 :2562 的断言相应从"记不进去"改为"记进去了但不满足要求"。

5. **拆分 acceptance/contract 替换特权**（:4929–4952）。
   "记录一个事实"和"换掉唯一真相来源"不该共用一个入口。
   注意 `validate()` **从不复验运行级 acceptance 文件 hash**（只有 :4391 和 :4480 做），
   这个换约动作在 finalize 层完全不可见。

### P2

6. **`fail` 粘性按 `blocked` 的先例改**（:727–734 的理由逐字适用）：
   可被其后一条合规 root pass 解除，硬门一条不少。
   今天的替代路径是新建 run-dir 从零跑，**那条 pass 面对的门完全一样，只是额外丢掉了失败史**
   ——同强度证据，一个留痕一个洗账，现设计在奖励洗账。
7. **`status` 子命令**。在"入口无条件"的新框架下它不是人体工学小事，而是必需的另一半：
   必须有"我在哪、能做什么、越过需要哪种 decision"的查询接口，否则无条件写入会退化成乱写。
   实测被敲 12 次（§4.6）。

### 建议加进 `GATE_REGISTRY_DISCIPLINE` 的第四问

现有三问（防哪个诊断码 / 防哪条实测逃逸 / 复审日期）之外，加：

> **"代理在这道门拒绝它的那个状态下，合法出口是什么？"** 答不出来的门不许合入。

依据：本仓每一次事故都是同一个形状——门堵死合法出口 → 代理换 run-dir → 前面测试全废。

### 验收判据（适用于后续每一次改动）

**不看新增了几道门，看 receipt 覆盖率（receipt / init）有没有升。**
这是唯一同时反映严格性与可用性的单一指标。

---

## 7. 诚实边界

**本轮独立复算的**：§3.1 全部、§3.2 全部、§4.1、§4.2、§4.6、§4.7，
以及 §1 表中 1–7 项的代码事实（逐条 grep/sed 验证过）。

**未独立验证的**：
1. **§5 的第 3、4 条（预授权路径、consolidated 连锁）是代码推导，未实测。**
   实现前必须先写失败用例。
2. **`fail` 粘性的消费者未全量追**，只看了 `compute_scenario_status`。
   改动前应 grep 全部 `"FAIL"` 消费点。
3. **`decision` 原语的迁移成本未评估**（schema 1.5.0 需升版、老账本渲染兼容）。
   本仓有"老账本无新字段仍正常渲染"的先例（第四轮 §2.1 的 toolchain 字段），方向可行，
   工作量未知。
4. **"`validate()` 不看 challenge_loops"是靠行区间 grep 确认的**，可信度高，
   但不排除通过某个未追进去的 helper 间接读取。**这是全文最承重的事实，值得再复核一次。**
5. **样本外普适性未知**：18 本账本来自 2 个项目、5 天内；rollout 来自另一台机器。
   §4.2 那条结论（挑战循环与 receipt 不相交）只有 4 个 receipt 样本，**基数很小**。

**方法**：本轮结论由两个独立子代理分别从"架构不变量"与"方法论"角度产出，
主代理逐条复核其可证伪论断后采信；§3.2 的两处修正、§4.2 与 §4.6、§4.7 是主代理独立发现。
子代理未复算任何数字，其数据引用均来自第四轮转述——**这正是 §3.2 修正得以出现的原因，
也提示下一位：子代理的数据引用需自行复核。**

---

## 8. 工作树现状（未提交）

```
 M CLAUDE.md
 M skills/plan-test/scripts/plan_test_gate.py
 M skills/plan-test/scripts/test_plan_test_gate.py
```

内容是第四轮 §4（挑战层报错手感改善，文档标注"可直接做，无需批准"）：

- 枚举错误统一带合法值清单（新增 `_enum_error`），覆盖 severity/scope_relation/origin/status/review_mode
- **顺带修了 cluster/synthesis 路径**——原本连出错的值都不显示（第四轮 §4 未点到，错法同源）
- `id` 报错给正则解释与示例；未知/缺失字段报错附完整清单
- 新增 `print-schema` 子命令（`--format human|template`）
- 新增 `FindingSchemaHelpTestCase` 6 条用例，其中 `test_template_is_self_consistent` 是护栏：
  将来加字段忘了同步模板会当场变红

**测试：292 项全绿**（286 + 6，约 86 秒）。无新增诊断码，`CLAUDE.md` 的"55 个"计数不用动。

**§4 的实测收益很小，别高估**：1888 次调用里 SCHEMA_INVALID 真实触发 22 次，
挑战层 20 次，纯格式问题 14 次；且 19 段失败连击中 **18 段是"连续 1 次"**
——代理基本错一次就自己改对了。它是手感改善，不是提速。

业主已确认"留"。**尚未 commit。**

---

## 9. 与业主协作（沿用第四轮 §6，本轮补充）

- 用中文。
- **先用大白话解释再让他决策**，直接抛选项会被打断。打比方有效（考试/成绩单、病历）。
- 业主会追问"调研做透了没有"。**如实说明证据边界比给漂亮结论更重要。**
- **本轮新增教训**：业主两次把方案往上推——先问"§4 有意义吗"（逼出了实测收益很小的诚实结论），
  再问"是否有更符合哲学的架构"（推翻了单点开口方案）。
  **他要的是结构性解法，不是补丁。给建议时先自问：这是在治现象还是治实质。**
- 业主熟悉《矛盾论》的分析框架，且本仓 `methods/research-method.md` 第 2 条就要求
  识别主要矛盾——用这套语言沟通是有效的，不是修辞。

---

## 10. 建议的接手顺序

1. 读 §1（复核方法）→ §2（证据边界）→ §4.2/§4.3（最重要的两个发现）。
2. **亲自复核 §7 第 4 条**（`validate()` 不看 challenge_loops）——全文最承重。
3. 复核 §5 第 3、4 条的代码推导，**写失败用例**验证。
4. 找业主确认 P0 是否开工。§8 的改动可一并提交。
5. P0-1（refusal ledger）改动小、无行为风险、是后续一切验证的前提，建议先做。
