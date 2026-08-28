# 技术 plan — s1：refusal ledger

> ⚠️ **已归档（2026-08-28）**：见 [`SCOPE-AUDIT-2026-08-28.md`](./SCOPE-AUDIT-2026-08-28.md)。
> 执行依据是 [`../s1a-refusal-log/`](../s1a-refusal-log/)。本文件保留三轮挑战的
> 处置记录（§7/§8）与 spike 结论（§0b），供 s1b/s1c 设计时引用。

> AC 唯一真相：[`acceptance.md`](./acceptance.md)　Program：[`../../program.md`](../../program.md)
> 目标文件：`skills/plan-test/scripts/plan_test_gate.py`（HEAD `95944c3` 时 5676 行）
> **plan-status: draft** —— rev2，已过 primary breadth challenge + spike，未过专项挑战与用户 review。

---

## 0. 三条已验证的技术约束（实读代码，非推测）

### 0.1 refusal 不能进账本 JSON

```python
# :1967
"ledger_sha256": canonical_digest({k: v for k, v in ledger.items() if k != "revision"}),
```

覆盖账本除 `revision` 外全部字段。写进账本 → 每次拒绝改变 `ledger_sha256`。

### 0.2 refusal 不能走 `_append`

```python
# :2371
def _append(run_dir, mutate, op="append"):
    with LedgerLock(run_dir):
        ...
        broken = integrity_check(ledger)
        if broken:
            die("LEDGER_TAMPERED: ...")      # ← _append 自己会 die
```

`die()` 若调 `_append`，`LEDGER_TAMPERED` 场景直接递归。

### 0.3 `die()` 拿不到 run_dir

`die(msg, code=2)`（:193）是模块级函数，签名无 run_dir，160 处调用点不可能逐个改签名。

---

## 0b. 关键假设的 spike 验证（已真跑）

可丢弃 spike，跑完即删。四条全部成立：

| # | 假设 | 结果 |
|---|---|---|
| H1 | `SystemExit` 不被 `except Exception` 吞 | ✅ 它继承 `BaseException` |
| H2 | 重入标志挡得住 `die → 写入 → die` 递归 | ✅ **无防护版实测递归 51 层**；有防护版只调 1 次，`exit(2)` 不变 |
| H3 | 写入失败时原 stderr 与退出码逐字不变 | ✅ 逐字节相同 |
| H4 | 上下文未就绪时静默跳过 | ✅ 写入 0 次 |

**H2 证明递归风险不是假想**。H4 顺带查清：`main()` 中 `parse_args` 之前的 `die` 调用数 = 0，
模块导入期 = 0——该路径当前不存在，但短路判断**必须保留**为将来的防线。

---

## 0c. ⭐ 落点决策（rev2 的核心变更）

### rev1 错在哪

rev1 把 `refusals.jsonl` 放在 run-dir 里，依据是 `rationale.md:19`「把 run-dir 排除在
digest 外」。**该依据是散文，代码不是这么实现的。**

`declared_exclusion_scope`（:363-390）只返回**该 run 在 init 时冻结的** `exclusion_scope`，
而 `repo_content_digest`（:429）对 `git ls-files -c -o --exclude-standard` 的每个未排除文件
取内容 hash。

**实测**（可复现）：run-003 冻结的排除范围是

```
plans/2026-08-26-enforcement-anchors/verification/run-001
plans/2026-08-26-enforcement-anchors/verification/run-002
plans/2026-08-26-enforcement-anchors/verification/run-003
```

**不含** `plans/2026-07-27-gate-hardening/verification/slice-a`。在后者下新增一个文件：

```
写入前: f6cb15b6434874161ca8ff06b1dbaaf209de4365346f33d66177f732f18ac667
写入后: 87f72cd17923f1ce7e1c26ea7658efa06a9aeedaf68f15b673f1383bec0d1ad9
删除后: f6cb15b6434874161ca8ff06b1dbaaf209de4365346f33d66177f732f18ac667
CHANGED = True   RESTORED = True
```

**结论：rev1 的落点会让任何一次拒绝把同仓其他 run 打成 `TESTED_RUNTIME_MISMATCH`。**
"零行为变更"不成立。

### 决定性事实：gitignore 的文件不进指纹

`repo_content_digest` 用的是 `git ls-files -c -o --exclude-standard`。
`--exclude-standard` 会跳过 `.gitignore` 命中的文件。**实测**：

```
新建 .probe-tmp/f.jsonl          → ls-files 命中 1
把 .probe-tmp/ 加入 .gitignore   → ls-files 命中 0
```

### 三个方案与取舍

| 方案 | 指纹影响 | 跨机可见 | 风险 |
|---|---|---|---|
| A 只放 gitignore | 无 | ❌ 要人工打包 | 低 |
| B 进 git + 扩大排除范围 | 无 | ✅ | **高**——须改 `declared_exclusion_scope` 语义，按路径形态自动排除等于给"藏后门"开口子（其 docstring 记录了三次被打穿的历史） |
| **C 本机累积 + 显式导出** | **无** | ✅ 显式 | 低 |

**业主选定 C。** 日常写入零副作用；需要跨机器分析时跑一次 `export-refusals`。

### rev3：C 的落点再修一次——必须离开被测仓库

rev2 把 C 实现为"仓库内 `.plan-test/` + 本仓 `.gitignore` 加一行"。**closure review 打穿了它：**

**gate 是以插件形式分发、在别人的仓库里运行的。**
`hooks/stop-gate-check.sh:43` 与 `hooks/adapters/git/pre-push:34` 都从
`$HOME/.claude/plugins/cache/*/plan-test/*/skills/plan-test/scripts/plan_test_gate.py`
解析 gate——**消费仓库的 `.gitignore` 不含 `.plan-test/`**，那一行不随插件分发。
于是消费仓库里每一次拒绝都会改变整仓指纹，**与 rev1 被否决的落点是同一后果**。

附带第二个缺陷：`.gitignore` 是 **tracked 且随分支变化**的内容。checkout 到 T7 之前的
提交/分支/tag（bisect、release 分支、老 worktree）时它不再生效，而在用的 gate 仍是插件
缓存里的新版本——**P0 静默复发**。rev2 把它当成"一次性配置"是错的。

**rev3 落点**：`$PLAN_TEST_REFUSAL_HOME`（默认 `~/.plan-test/`）下按仓库分文件
`refusals-<repo_key>.jsonl`，`repo_key` = 仓库根绝对路径的 sha256 前 16 位。

这让 AC-2 从"依赖被测仓库恰好忽略了它"变成**结构上成立**，并顺带解决另外两条：

| 顺带解决 | 怎么解决的 |
|---|---|
| 测试污染真实账本（P1） | 测试基类把 `PLAN_TEST_REFUSAL_HOME` 指向 tmpdir |
| gitignore 是版本化状态（P1） | 不再依赖任何仓库内文件 |

导出物一旦提交，会像**新增任何文件一样**进入指纹——那是正常仓库活动
（本 plan 目录的创建本身就已经让 run-003 变红），区别在于它是**人显式发起的一次动作**，
不是每次拒绝自动发生。

---

## 1. 设计

### 1.1 落点

```
$PLAN_TEST_REFUSAL_HOME  （默认 ~/.plan-test/）
  └── refusals-<repo_key>.jsonl        append-only，一行一条 JSON
```

`repo_key` = 仓库根绝对路径的 sha256 前 16 位；定位不到仓库根时用 `no-repo`。

**不向被测仓库写入任何东西**——不建目录、不改 `.gitignore`。这是 AC-2 结构成立的前提。

**附带解决三个 P1**：
- init 被拒时账本尚不存在，rev1 的记录会落进 stats 永远扫不到的孤儿目录
  （`_stats_scan_ledgers` 的发现口径是"目录里有合法账本"）；
- 上下文不绑死 `--run-dir`，`compile-manifest` 等无 run-dir 的子命令也能记录；
- 测试可用 `PLAN_TEST_REFUSAL_HOME` 指向 tmpdir，不污染真实账本。

### 1.2 仓库根定位（解 0.3，且不依赖 run_dir）

从 `os.getcwd()` 向上查找 `.git`（目录**或文件**——后者是 worktree/submodule 情形，
内容形如 `gitdir: ...`），最多向上 40 层，取**最近**的一个。
找不到 → `repo_key = "no-repo"`，仍然记录（不再静默丢弃）。

**不调 `git rev-parse`**：`die` 是错误路径，不引入子进程开销与新的失败面。
结果模块级缓存，一次进程只查一次。

> **已知语义**：嵌套仓库时向上查找命中的是最近的 `.git`，可能与账本里的
> `repo_root`（`plan_test_gate.py:2230`）不是同一棵树。这不影响 AC-2
> （两者都在被测仓库之外写文件），但会影响 `run_dir` 的相对化——见 1.3。
> 该语义须写进 `PROTOCOL.md`。

### 1.3 上下文

```python
_REFUSAL_CTX = {"repo": None, "repo_key": None, "run_dir": None,
                "run_dir_external": False, "cmd": None, "writing": False}
```

`main()` 在 `args = ap.parse_args(argv)` 之后、`args.fn(args)` 之前填充。
`run_dir` 的相对化规则（rev3 显式定义，rev2 未定义）：

```
run_dir 在 repo 根内  → 相对路径，run_dir_external = False
run_dir 在根外/无 repo → 绝对路径的脱敏值，run_dir_external = True
```

**不得产出 `../..` 前缀的值**。rev2 只写"转为相对仓库根"，而
`--allow-external-run-dir`（:2237）显式允许 run-dir 在仓库之外，
`os.path.relpath` 在这些情形返回 `../..` 开头的垃圾值，
且会被 AC-3 的失败安全**静默吞掉**——表现为写入垃圾而非报错。

### 1.4 写入函数（解 0.2 + AC-3 + AC-4）

```python
def _record_refusal(msg):
    """把一次 die 记成事实。任何失败都必须静默——不得改变原本的报错与退出码。"""
    ctx = _REFUSAL_CTX
    if ctx["writing"] or not ctx["repo"]:
        return                      # 重入防护 + 上下文未就绪短路
    ctx["writing"] = True
    try:
        ...                         # 提取 code、脱敏、截断、trim、append
    except Exception:
        pass                        # 失败安全：吞掉一切
    finally:
        ctx["writing"] = False
```

不读账本、不验链、不加锁 → 与 `_append` 完全无关，不会递归到 `integrity_check`。
`except Exception` 不会吞掉 `sys.exit`（H1 已验）。

### 1.5 `die()` 改动（唯一侵入点）

```python
def die(msg, code=2):
    _record_refusal(msg)                       # ← 新增一行
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)
```

先记录后打印：打印/退出路径若异常，记录已落盘。

### 1.6 记录格式与脱敏

```json
{"at":"2026-08-28T18:40:11+0800","cmd":"record-challenge-control",
 "code":"CONTROL_NOT_REQUIRED","run_dir":"plans/x/verification/run-001",
 "detail":"action=scope-change-approved 仅在 ... 可记录；当前=CONVERGED"}
```

- `code`：首行匹配 `^([A-Z][A-Z0-9_]{3,}):`，无匹配则 `null`
- `run_dir`：**相对仓库根**；命令无 `--run-dir` 则 `null`
- `detail`：首行 →**脱敏**→ 截断 500

**脱敏在落盘时就做，不留到导出**：绝对路径就在 die 消息的插值里，
例如 `LedgerLock.__enter__`（:271）`die("LEDGER_LOCKED: %s 被其他进程持有…" % self.path)`、
`cmd_init`（:2238）`die("run-dir 在仓库之外（%s）…" % run_dir)`。

规则（rev3 补齐 Windows，本仓在 AC-3 明确声明支持 Windows）：

1. **仓库根前缀 → `<repo>`**，比对前**分隔符归一**（`\` 与 `/` 等价）。
   否则 ctx 里的 `C:\a\b` 与消息里的 `C:/a/b` 不相等，替换静默漏掉。
2. **其余绝对路径 → `<path>`**。Windows 形态**不得以空白为界**：
   `C:\Users\John Smith\proj\verification\run-1\.gate.lock` 若按空白切分，
   只有 `C:\Users\John` 被替换，残留 `Smith\proj\verification\...`
   ——**泄漏用户姓氏与目录结构**，而 `:271` 插值的正是这种路径。
   须匹配到行尾或明确的终止符（`）` / `"` / ` 被`）。

> 反向的"误伤正常内容"风险实测低：die 字面消息中含 `://` 的 0 条、
> 以 `/` 开头的非路径 token 0 条。缺口是 Windows 下的**欠脱敏**，不是过脱敏。

### 1.7 文件上限与原子 trim

超过 512 KB 时读入全部行、保留后一半、**写临时文件后 `os.replace`**。

**必须原子**：`os.replace` 在 POSIX 与 Windows 上都是原子的。
rev1 写的是"重写"，在声明为无锁的路径上做非原子整文件重写，
并发或中断时是整段数据丢失，超出"容忍 append 交错"的边界。

### 1.8 stats 消费（AC-6）

`cmd_stats` 新增一段，读 `<repo>/.plan-test/refusals.jsonl`：

1. 按 `code` 计数（`null` 归入"无诊断码"）
2. 按 `cmd` 计数
3. **每个 `code` 的「拒绝 → 下一个新 run」间隔分布**：样本数 / 中位数 / 最小值，
   样本 < 2 只列计数

配对：refusal 的 `at` 之后、同仓库内 `created_at` 最早的新账本。
**时间源只用账本 `created_at` 与 refusal `at`，禁止调用 `_stats_last_activity`**
（它把 `integrity.chain`（str）当 list of dict 遍历，恒走 mtime 兜底——实测
`chain` 为 str、`log` 才是 list，遍历得到的首元素是字符 `'8'`）。

坏行（非法 JSON）跳过，不崩溃。

#### 为什么不设固定时间窗口

初稿设计为"30 分钟窗口内出现新 init 即计一次转化，输出转化率"。实测后放弃
（rollout 日志 71 次真实拒绝、33 次其后有 init）：

```
间隔分布（分钟）  P25=0.7  P50=64.4  P75=366.0  P90=877.4  最大 1699.5
窗口覆盖率       30 分钟 → 42%   60 分钟 → 48%   240 分钟 → 70%
```

分布跨四个数量级，任何单一阈值要么漏一半、要么把六小时后的无关 init 算进来。
而按诊断码分组后信号自明：

| 诊断码 | n | 中位数 | 读法 |
|---|---:|---:|---|
| `ACCEPTANCE_CHANGED` | 4 | 0.7 分钟 | 被拒即换 |
| `CONTROL_NOT_REQUIRED` | 7 | **4.9 分钟** | **被门逼的样子** |
| `LEDGER_TAMPERED` | 4 | 64.4 分钟 | 中间态 |
| `SCHEMA_INVALID` | 9 | **368.8 分钟** | **显然无关，只是手感问题** |

**分布本身就是结论**，阈值只会把它压扁成一个可疑的百分比。

> 输出脚注必须写明：相关性不是因果性，用途是**排序**（哪道门后面最常紧跟新 run），
> 不是判罪；退休决定仍需人工复核。上表口径是**同会话内配对**，跨会话统计不到，因此是**低估**。

### 1.9 导出命令（AC-7）

```
export-refusals --output <path>
```

- `--output` 必填、无默认（避免意外往仓库写文件）
- 输出前打印目标路径与条数
- 内容已在落盘时脱敏（1.6），导出**再做一次**同样的脱敏作为兜底

---

## 2. 任务分解

| # | 任务 | 覆盖 AC | 文件 |
|---|---|---|---|
| T1 | `_find_repo_root()`（向上找 `.git`，含 worktree 的 file 形态，取最近，缓存）+ `repo_key` | AC-1,2,5 | `plan_test_gate.py` |
| T2 | `_REFUSAL_CTX`、`_record_refusal()`、**跨平台脱敏**、`PLAN_TEST_REFUSAL_HOME` | AC-1,3,4,7 | 同上 |
| T3 | `main()` 填充上下文（含 `run_dir` 相对化 / external 判定）；`die()` 加一行 | AC-1 | 同上 |
| T4 | 原子 trim（临时文件 + `os.replace`） | 非功能 | 同上 |
| T5 | `cmd_stats` refusal 三段统计（配对按 verification 目录 + 多对一去重；不碰 `_stats_last_activity`） | AC-6 | 同上 |
| T6 | `export-refusals` 子命令 | AC-7 | 同上 |
| **T7** | **测试隔离**：基类设 `PLAN_TEST_REFUSAL_HOME` → tmpdir，并断言真实目录未被写入 | **AC-8** | `test_plan_test_gate.py` |
| T8 | `RefusalLedgerTestCase`：四类落盘 / **AC-2 三段（含空 gitignore 的临时仓库）** / 失败安全（目录占位）/ 断链不递归 / 三形态脱敏 / **逐子命令覆盖面** | AC-1~5,7 | 同上 |
| T9 | `test_gate_stats.py` refusal 统计 + 坏行 + 多对一去重 + 跨目录不配对 | AC-6 | `test_gate_stats.py` |
| T10 | 文档：`PROTOCOL.md` 新增一节（实测覆盖率 / 嵌套仓库语义 / 导出物指纹说明）；**更正 `HANDOFF-2026-08-28-runlog.md:284`** 的测试耗时 | AC-5,8 | 两个 md |

10 个任务，触及 `RELEASE_UNIT_LIMITS` 上限，**不得再加**。

> T7 由 rev2 的"改 `.gitignore`"整体替换为"测试隔离"——rev3 不再向被测仓库写任何文件，
> 那个任务消失了；而测试隔离是 rev3 的落点变更**新引入**的必需项。
> T10 的文件也从 `HANDOFF.md` 更正为 `HANDOFF-2026-08-28-runlog.md:284`：
> 实测那句"约 80 秒、别用 120s 超时"只在后者，`HANDOFF.md` 无任何耗时字样，
> 照 rev2 字面执行会改错文件、把肇事的那条建议原样留下。

## 3. 实施顺序（每步一个 commit）

1. **T8 的 AC-2 反向用例先写**——先证明"落点放 run-dir 内会判红"，
   否则 AC-2 的正向断言在任何实现上都会通过（rev1 就是这么错的）
2. T1+T2+T3+T7 —— 核心路径
3. T4 —— 原子 trim
4. T8 补全 + T5+T9 —— 用例与 stats
5. T6 —— 导出
6. T10 —— 文档

## 4. 风险与开放问题

| 风险 | 影响 | 缓解 |
|---|---|---|
| `except Exception: pass` 吞掉真实 bug | 写入静默失效 | T8 正向断言"正常情况确实写了" |
| 并发写入交错 | 单行 JSON 损坏 | 逐行解析跳过坏行；T9 加坏行用例 |
| 脱敏漏网（非路径的敏感内容） | 导出物含本地信息 | 只记首行 + 双重脱敏；`--output` 必填让人过目 |
| 向上找 `.git` 找错仓库（嵌套仓库） | refusal 写进外层仓库 | 取**最近**的 `.git`；PROTOCOL 注明该语义 |
| 间隔分布被当因果 | 误退真门 | 输出脚注写明相关性/排序用途/低估 |
| 样本过小（多数码 n≤4） | 中位数不稳 | n<2 不出分布；恒带样本数 |

**开放问题**：无。rev1 的两个已在 rev2 消解（落点由业主选定 C；窗口经实测取消）。

## 5. 回滚

代码改动集中在 `_find_repo_root` / `_record_refusal` / `die()` 一行 / `cmd_stats` 一段 /
`export-refusals` 一个子命令，`git revert` 可完全回退。
`.plan-test/` 是 gitignore 的本机数据，回退后残留不影响任何命令（AC-8 覆盖"无此目录时行为不变"）。

## 6. 与 GATE_REGISTRY_DISCIPLINE 的关系

本 slice **不新增任何诊断码**，三问不适用。它反过来是**为退休评审提供数据源**——
`config.md:269` 指定数据源为 `stats`，而 `cmd_stats` 的 docstring 自陈"诊断没有历史留痕"。

## 7. 挑战与复核记录

**rev1 → rev2 由 primary breadth challenge 驱动。** 结论：

| finding | 处置 |
|---|---|
| P0 refusal 文件扰动同仓其他 run | ✅ 独立复现，**采纳**——落点改为 C 方案 |
| P1 AC-2 oracle 按构造无法判红 | ✅ **采纳**——AC-2 重写为正反两段 |
| P1 init 被拒留下 stats 扫不到的孤儿目录 | ✅ **采纳**——仓库级单一文件天然解决 |
| P1 AC-5 缺配对键 | ✅ **采纳**——记录加 `run_dir` |
| P1 `_stats_last_activity` 读错字段 | ✅ 独立验证，**采纳**——AC-6 明令绕开 |
| P1 die 覆盖缺口 24/160 未声明 | ✅ **采纳**——改为实测并写进 PROTOCOL（AC-5） |
| P1 AC-7 oracle 未定义比对面 | ✅ **采纳**——rev2 的 AC-8 只断言"全绿"，不做 golden 比对 |
| P2 detail 泄漏绝对路径 | ✅ **采纳**——落盘时即脱敏 |
| P2 trim 非原子 | ✅ **采纳**——`os.replace` |
| P2 AC-3 失败注入不可移植 | ✅ **采纳**——改用"建成目录"，跨平台 |
| P1 测试套件不终止 | ❌ **驳回**——同机三次全绿（91.5 / 86.2 / 149.3 秒）。挑战者用 `timeout 150`，最长一次差 0.7 秒撞线，看到的是超时截断不是挂死。**但采纳其中的真事实**：耗时波动大且逼近常用超时线，AC-8 因此写明"超时不得低于 300 秒"，并更正 `HANDOFF.md` §6 过时的"约 80 秒"。 |

## 8. rev2 → rev3：closure diff review 的处置

closure 复核了上表的 11 条处置，判定 **7 条落实、3 条部分落实、1 条驳回成立**，
并报出 1 个新 P0 + 3 个新 P1。全部采纳：

| finding | 严重度 | 处置 |
|---|---|---|
| **落点在消费仓库里不被忽略** | **P0** | ✅ 已验证（gate 从 `$HOME/.claude/plugins/cache/...` 解析，跑在别人仓库里）→ **落点改为用户级 `~/.plan-test/`** |
| `.gitignore` 是版本化状态，checkout 老分支即失效 | P1 | ✅ 随落点变更一并消解 |
| **测试会写进真实 refusal 账本** | P1 | ✅ 已验证（143 处 `run_gate(` 只有 24 处传 `cwd`）→ 新增 T7 测试隔离 + AC-8 硬要求 |
| AC-5 的 oracle 不可证伪 | P1 | ✅ 采纳——rev2 的判据是 rev1 残留（按有无 `--run-dir` 判可观测性），rev3 下"不可观测集合"按构造为空。改为**逐子命令行为判据** |
| 配对键 AC-1/AC-6 自相矛盾 | P2 | ✅ 采纳——配对收窄为"同 verification 目录 + 多对一去重" |
| T10 指错文件 | P2 | ✅ 采纳——改为 `HANDOFF-2026-08-28-runlog.md:284` |
| Windows 脱敏欠覆盖 | P2 | ✅ 采纳——补分隔符归一与含空格路径规则 |
| `run_dir` 在仓库根外未定义 | P2 | ✅ 采纳——AC-1 显式定义 external 情形 |
| rev2 的数字错误 | P2 | ✅ 采纳，见下 |
| 无 `assurance-contract.json` | advisory | ⏸ 仓库级惯例缺口，非 s1 返工项，记入 program 待办 |

### 更正 rev2 的两处数字错误

1. **292 vs 216 归因颠倒。** rev2 称"rev1 写 292 是错的口径，静态 `def test` 为 216"——
   **反了**。292 正是 `unittest` 报告的真实用例数（主代理三次、closure 一次，四次独立复跑
   均为 292），216 是静态 grep 计数，因继承复用而不可比。
   结论（只断言全绿、不写死条数）仍然成立，但理由是错的。
   **成因**：主代理采信了 primary challenger 的数字未复算——与"引 `rationale.md` 散文
   未验代码"是同一类错误，本轮第二次。
2. **`die` 调用点数**：`program.md` 写 161，acceptance/plan 写 160。
   实测 `grep -o "die(" | wc -l` = 161，其中 1 处是 `:193` 的 `def die(`，
   故 **160 正确**，`program.md` 多算了定义处，已改。
