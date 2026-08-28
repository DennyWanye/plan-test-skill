# Handoff：run log 实证驱动的第四轮（2026-08-28）

> 交给下一位代理直接接手。**不是**跳过 review 直接实现全部剩余项的授权。
> 本文生成时 HEAD：`0a53b8b`（其前为 `fc0f94d`）。已提交，**未推送**。
> 前三轮的背景见 `HANDOFF.md`；本轮与前三轮的区别是：**结论全部来自真实 run log 统计，
> 不是设计推演**。

---

## 0. 一句话现状

本轮从两份真实日志（18 本账本 + 1888 次 gate 调用）里挖出**三条独立的成因，都通向同一个
动作：换个 run-dir 重来**。已堵掉两条并补了工具链记账；**第三条已定位、已给方案、等业主
拍板，尚未动手**——那是你要接的活。

---

## 1. 证据基础（先读这一节，否则后面的数字没有来源）

### 1.1 原始数据在哪

两个 zip，业主放在 Windows 侧：

```
C:\projects\plan-test\run log\
  plan-test-run-collection-20260828.zip     5.8 MB   18 本真实账本 + gate-checks + inventory
  plan-test-raw-rollout-logs-2026-08-28.zip 389 MB   83 个 codex rollout 会话 jsonl
```

WSL 路径：`/mnt/c/projects/plan-test/run log/`。**本机没有 `unzip`，用 python zipfile。**

### 1.2 两份数据不是同一台机器、不是同一批项目（重要）

| | 账本 collection | rollout 日志 |
|---|---|---|
| 项目 | `agentOS`（17）、`DGXSpark`（1） | `simple_harness`、`AIPhone`、`web3wallet` 等 |
| 交集 | **无。** `pair-relay` / `lan-session-hub` 在 rollout 日志里一次都没出现 |

**所以两份数据无法互相印证**，任何"账本现象 ⇄ 会话原因"的连线都是跨样本推断，下结论时
必须说明。业主本人也确认过是不同电脑。这正是本轮加工具链记账的直接动机（见 §2.1）。

### 1.3 怎么把 1888 次 gate 调用重新抽出来

scratchpad 会被清掉，这段脚本要能重跑：

```python
import zipfile, json, sys
z = zipfile.ZipFile('/mnt/c/projects/plan-test/run log/plan-test-raw-rollout-logs-2026-08-28.zip')
for n in sorted(x for x in z.namelist() if x.endswith('.jsonl')):
    pending = {}
    with z.open(n) as f:
        for raw in f:
            if b'plan_test_gate' not in raw and b'call_id' not in raw:
                continue                      # 不预筛的话要跑很久
            try: d = json.loads(raw)
            except Exception: continue
            p = d.get('payload')
            if not isinstance(p, dict): continue
            t = p.get('type')
            if t in ('custom_tool_call', 'function_call'):
                s = p.get('input') or p.get('arguments') or ''
                if 'plan_test_gate' in s:
                    pending[p.get('call_id')] = (d.get('timestamp'), s[:4000])
            elif t in ('custom_tool_call_output', 'function_call_output'):
                cid = p.get('call_id')
                if cid in pending:
                    ts, cmd = pending.pop(cid)
                    o = p.get('output')
                    if isinstance(o, list):
                        o = ''.join(x.get('text','') for x in o if isinstance(x, dict))
                    print(json.dumps({'sess': n.split('/')[-1], 'ts': ts,
                                      'cmd': cmd, 'out': str(o)[:6000]}, ensure_ascii=False))
```

**统计时的坑**：输出里出现某个诊断码 ≠ 该诊断真的触发了——代理经常 `grep`/`sed` gate 源码，
源码行里就有那些常量。按 `^ERROR: <CODE>:` 行首匹配才是真实触发。我第一遍没过滤，
`SCHEMA_INVALID` 报了 107 次，真实只有 20 次。

---

## 2. 本轮已完成（`0a53b8b`，286 项测试全过，两个冻结 fixture 输出未变）

### 2.1 `toolchain`：开账即记版本与环境

`init` 把工具链指纹冻进账本（写在 integrity 链首条 `init` **之前**，事后改动即
`LEDGER_TAMPERED`）：

```
gate_version / gate_sha256 / gate_path / plugin_version
python_version / platform / host / recorded_at
```

**为什么非做不可**：账本此前只有 `schema_version`，而它在插件 v0.4.0→v0.4.1、8/11→8/28
全程都是 `1.5.0`。"这轮是哪版 gate、哪台机器跑的"事后查不到——直接导致 §2.3 那个 bug
一度无法定性。receipt 里的 `validator_version` 补不上：那是 finalize 时刻的值，而 18 本
账本里 **14 本根本没走到 finalize**。

`gate_sha256` 是承重字段：版本号会忘了升（`1.5.0` 横跨两个插件版本），文件哈希不会。
纯记账，不产生诊断码。老账本无此字段仍正常渲染（不制造迁移断裂）。

### 2.2 `SIBLING_RUN_UNRESOLVED`：换目录洗账本（新增阻塞码）

**现象**：`fail` 是粘性的 ⇒ 唯一出路是新建 `run-00N+1`（`compute_scenario_status` 的注释
里就是这么写的，轮换是**设计内的正路**）。问题是配套的 `retire --superseded-by` 没有
任何东西检查做没做。

**实测**：5 次轮换 4 次没挂账；`retire`/`acknowledge` 全局使用 **0 次**；被丢弃账本里躺着
**75 条测试事实、142 份证据、16 条 root fail**——比进了 receipt 的 65 条还多。两张历史
SHIPPABLE receipt（`s1-relay-foundation/run-006`、`s1-lan-relay/run-003`）都是在旁边躺着
红账本的情况下发出的。**receipt 没撒谎，但它把失败史藏起来了。**

#### ⚠️ 判据是"必测场景集相交"，不是"同目录"——别改回去

我第一版按目录判，被真实反例打脸：`plans/2026-08-18-memory-sdk-integration/verification/`
下并排躺着 `run-1..run-4`，分测 `AC-1..4 / AC-5..8 / AC-9..11 / AC-12..14`，用**四份不同
manifest**——那是四个不同 slice 各测各的，互不欠账。按目录判会让它们互相欠账、谁都发不出
receipt。按场景集判：8 处轮换现场 **7 处判真轮换、这 1 处正确放行**。

**也不能用 acceptance 哈希**：`s1-relay-foundation` 那 6 轮里 `acceptance.md` 被改过两次
（3 个不同哈希）而场景集 6 轮完全一致——用哈希判，改份验收文档就溜过去了。

#### 解开的两处时序死锁（本仓 HANDOFF 已记过四处同类，这是第五、第六处）

1. `retire` 原要求继任者**已有 receipt** → 与本门死锁（继任轮因兄弟未了结拿不到 receipt，
   兄弟又因继任轮没 receipt 而退役不掉）。改为接受**全绿但未盖章**的继任者
   （`successor_receipt_status(..., allow_pending=True)`）。放宽的**只有盖章这一条**：
   继任者仍须过其余全部阻塞门、state 仍须 SHIPPABLE、仍须同仓非 fixture、且自己不能已
   退役/已放弃（防退役链首尾相接）。
2. `retire-status` 在该中间态输出 **`PENDING` 且 exit 1**。判 0 会多出一条静默出口：
   造个全绿继任者、把红账本退役进去、然后永不 finalize——红账本从此对 hook 隐身而交付
   从未发生。真要放弃请走 `acknowledge`（需用户批准原话 hash）。

**合法收尾顺序**：兄弟轮红 → 本轮全绿 → `retire` 兄弟轮 → 本轮 `finalize` → 兄弟轮的
`retire-status` 此时才转 VALID。

注意 `retire` 会改写兄弟轮账本；若兄弟轮不在本轮 init 冻结的 `related_run_dirs` 里，本轮
随后会报 `TESTED_RUNTIME_MISMATCH`，需 `re-attest`。**这是刻意的**——按路径形态自动排除
`.../verification/<x>/` 等于给"藏后门"开口子（见 `declared_exclusion_scope` 的注释）。

发现死锁的方式值得复用：**仓库自己的 4 个 `RetireTestCase` 当场变红**。已按新的合法顺序
改写并补端到端证明（`test_retire_then_finalize_is_the_legal_way_out`）。

### 2.3 `ChainLengthInvariantTestCase`：链长不变量护栏

**查的是 `LEDGER_TAMPERED` 在诚实工作中触发 5 次。全部同一根因，且已修复：**

`record-run --exec` 一次写入追加**两条事实**（run + 它抓到的执行日志）却只写一条链，而
`expected_chain_length` 假设 1:1。时间线是决定性的：

| 日期 | 事件 |
|---|---|
| 2026-08-19 | `c0aa00f` 上线 `record-run --exec` |
| 08-19 → 08-24 | **5 天窗口**：每跑一次 `--exec`，下一条命令必报"篡改" |
| 2026-08-24 | `666c87d` 补上折扣 `n -= paired_exec_evidence` |

5 次触发全落在窗口内，缺口对得上：两次缺 1（命令本身就是 `--exec`）、一次缺 16（该 run-dir
报错前跑了 **17 次** `--exec`）、另两次缺 1。

**没有再打补丁，而是焊死不变量**：逐条执行全部写入命令，断言 Δ事实 ≤ Δ链长。
**反向验证过**——注释掉那行折扣，测试当场失败并点名肇事命令。

> 为什么必须当回事：`LEDGER_TAMPERED` 阻塞且**没有任何修复命令**（有的话就等于"重算链即
> 洗白"），误判即账本报废，代理唯一出路是换 run-dir——**正好喂给 §2.2 那道门。一个门的
> 误报直接喂给另一个门。**

**新增写入命令时必须在 `ChainLengthInvariantTestCase` 的清单里补一行。**

### 2.4 顺带改正

`CLAUDE.md` 的"总计诊断码 46 个"与代码实际（改动前 54）对不上——手工计数早已失准，已按
实际改为 55 并注明。

---

## 3. ⏭️ 你要接的活：`CONTROL_NOT_REQUIRED`（**等业主拍板，勿擅自动手**）

### 3.1 现象

`record-challenge-control` 调用 28 次、失败 **14 次（50%）**，全是 `CONTROL_NOT_REQUIRED`。
其中 13 次是 `--action scope-change-approved`，当时循环状态是 `CONVERGED` / `ACTIVE` /
`CONTINUE`——从来不是它要求的 `USER_SCOPE_APPROVAL_REQUIRED`。

### 3.2 根因（读 `_challenge_state`，`plan_test_gate.py:4278`）

`USER_SCOPE_APPROVAL_REQUIRED` 只有两条产生路径：

1. 之前记过 `scope-audit`/`user-review` 且 `outcome=scope-change`——但那两个动作**各自又
   要求自己的前置状态**，而那些状态要靠"新增关键 finding > 0 且轮次达到软/复审上限"
   才自动出现；
2. 某轮 finding 带 `scope_relation: "scope-change-proposal"`。

**即：只有当门自己先提出要求，代理才能记录回应。用户主动拍板的场景**（日志原话
`"User requested rerun after explicit re…"`）**在账本里没有任何合法落点。门不是顺序卡住，
是从里面反锁。**

### 3.3 后果——这是第三条通向"换目录重来"的路径

14 次失败之后代理做了什么（逐条追过）：

| 之后的动作 | 次数 |
|---|---:|
| 立刻 `init` 一个全新 run-dir | 3 |
| `invalidate` 现有轮 + 新建 `-v2` run-dir | 1 |
| **`acknowledge` 放弃整轮验证** | 1 |
| 在同一 run-dir 另起第二个循环 `plan-iteration-002` | 1 |

最后一条正是 `LOOP_RESET_EVASION` 存在的理由——**现在知道代理为什么绕了：状态机不让它
记录真实发生过的事。**

至此三条成因齐了，全部通向同一个动作：

```
粘性 fail ─────────────┐
LEDGER_TAMPERED 误报 ──┼──→ 换个 run-dir 重来
CONTROL_NOT_REQUIRED ──┘
```

前两条已堵（§2.2 / §2.3），第三条未动。

### 3.4 建议方案（已呈给业主，等回复）

现设计有个不对称：**状态判定极严，而证据只是自由文本 `--evidence`**。而仓库已有更强原语
——`record-approval` / `acknowledge` 都要求绑定**用户批准原话的 SHA-256**。

> 建议：`scope-change-approved` 允许在**任意状态**下记录，**条件是必须带用户批准 hash**
> （与 `acknowledge` 同一套纪律）。状态机对"门主动要求的回应"保持原样；用户主动的决定
> 获得一个诚实、可追责的落点。

伪造成本仍是"算一条用户没说过的话的哈希"——与仓库已如实写明的 `acknowledge` 残余局限
**完全同源，不新增弱点**。整体反而更严（自由文本 → hash 绑定）。

**⚠️ 这动的是防伪造门。业主未明确同意前不要实现。** 若业主同意，记得：
- 用例要覆盖"任意状态 + 有 hash → 接受"与"任意状态 + 无 hash → 仍拒绝"；
- `render` 要显示这类控制事件的来源（门要求 vs 用户主动），否则读 receipt 的人分不清。

---

## 4. 第二优先：挑战层 `SCHEMA_INVALID` 手感损耗（可直接做，风险低）

真实触发 20 次，其中 **13 次是纯格式问题**，不拦任何实质风险：

| 归类 | 次数 |
|---|---:|
| finding id 不合 `^[a-z][a-z0-9-]{2,63}$` | 5 |
| findings 缺必填字段 | 4 |
| findings 含未知字段（如 `trusted_boundary_stop`） | 2 |
| findings 元素不是 object | 2 |

典型错法：代理写 `scope_relation='in_scope'`（门要 `in-scope`）、`origin='upstream_contract'`
（非法枚举值）。**报错只给正则，不给合法取值。**

建议（低成本）：
1. 报错时直接列出合法枚举值与必填字段，而不是只回一个正则；
2. 提供 `--print-schema` 或一份可复制的 findings 模板。

剩下 7 次（`LATE_FINDING_UNEXPLAINED`、`BREADTH_REVIEW_INCOMPLETE`、
`CONSOLIDATED_REVIEW_UNAUTHORIZED`、`SYNTHESIS_SPIKE_REQUIRED`）是**门在正常工作**，别动。

---

## 5. 已发现但未处理的线索

1. **CLI 人体工学**：44 个子命令里没有 `status`。代理在 **5 个不同会话**里都敲了不存在的
   `plan_test_gate.py status`，另外还猜过 `report`(×2)、`check-only`、`plan-review`、
   `challenge-status`、`record-baseline`、`activate`、`create-auditor-input` 等十余个。
   没有任何命令能回答"我这轮跑到哪了、下一步该干嘛"。加个 `status` + `report` 别名
   + 猜错时给近似提示，成本很小。（业主此前说"不懂为什么要做"，我解释后没再确认，
   **属于未获批准项**。）
2. **漏斗数据**：`init` 137 次 vs `finalize` 39 次；18 本账本只有 4 本拿到 receipt
   （22%），4 本 init 完再无动静。原因未深查。
3. **链长下界的覆盖盲区**：`record-phase-transition` 和 `record-plan-defect` 写的事实
   **不在** `expected_chain_length` 统计内（Δ事实=0）。方向安全（链比需要的长），但这两类
   事实不受长度下界保护——删一条不会被长度检查发现（链值检查仍覆盖，所以不是漏洞，
   只是保护弱一档）。要不要补进枚举，业主未定。
4. **`compile-manifest` 失败率 13%**（52 次调 7 次失败），根因未查。

---

## 6. 工作环境与验证

```bash
# 全套测试（286 项，必须全绿；两个静态 fixture 是冻结契约）
python3 -m unittest discover -s skills/plan-test/scripts -p 'test*.py'
# 约 80 秒，注意别用 120s 超时跑
```

- 仓库策略：**直接在 `main` 上开发**，不建分支/worktree（见 `CLAUDE.md`）。
- **未经业主明确要求不要 push。** 本轮 `0a53b8b` 已提交未推送。
- Stop hook 会拦收尾：`plans/2026-08-26-enforcement-anchors/verification/run-00{1,2,3}`
  目前均报 `TESTED_RUNTIME_MISMATCH`（因为本轮确实改了 gate 代码，**这个红是对的**）。
  run-001/run-002 都已正经 `retire` 到 run-003，所以 §2.2 的新门在本仓**不新增任何拦截**。
  要收尾需走补测流程，或由业主拍板 `acknowledge`（需绑定业主原话的 sha256，**代理不能代签**）。

### 与业主协作的注意事项

- 业主要求**用中文回复**。
- 业主不熟悉门禁内部细节，**要求先用大白话解释清楚再让他决策**——直接抛选项会被打断。
  有效的做法是打比方（例：把每个 run 比作一次考试、把 receipt 比作成绩单）。
- 业主会中途叫停并追问"你在干嘛、调研做透了没有"。**不要在调研没做透时就动手**——
  本轮第一版设计就是因为没看会话现场，差点把 memory-sdk 那个多 slice 场景误伤（§2.2）。
  如实说明证据边界（哪些是统计、哪些是推断）比给一个漂亮结论更重要。

---

## 7. 建议的接手顺序

1. 读 §1（证据基础）→ §3（待办根因）。
2. 找业主确认 §3.4 的方案是否可做。**同意再动手。**
3. 同意的话：实现 + 用例 + `PROTOCOL.md` §5.8 补一节 + `CLAUDE.md` 诊断表。
4. 顺手做 §4（纯改善，无需批准）。
5. §5 的线索按业主意愿排期。
