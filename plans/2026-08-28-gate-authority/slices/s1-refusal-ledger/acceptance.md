# Acceptance — s1：拒绝也是事实（refusal ledger）

> ⚠️ **已归档（2026-08-28）**：第 3 轮触发 `SCOPE_AUDIT_REQUIRED`，业主批准拆分为
> s1a/s1b/s1c，见 [`SCOPE-AUDIT-2026-08-28.md`](./SCOPE-AUDIT-2026-08-28.md)。
> **执行依据是 [`../s1a-refusal-log/`](../s1a-refusal-log/)，本文件仅作历史。**

> Program：[`../../program.md`](../../program.md)　证据：[`AUDIT-2026-08-28-gate-authority.md`](../../../../AUDIT-2026-08-28-gate-authority.md)
> **唯一真相来源。** 本文未列的行为一律不在本 slice 范围内。
> **rev3**（2026-08-28）：经 closure diff review 后再修。落点由「仓库级 + gitignore」改为
> **「用户级 `~/.plan-test/`，完全离开被测仓库」**——`.gitignore` 是被测仓库里随分支变化的
> 内容，而 gate 以插件形式分发到**别人的仓库**运行（`hooks/stop-gate-check.sh:43` 从
> `$HOME/.claude/plugins/cache/*/plan-test/*/.../plan_test_gate.py` 解析），本仓的一行
> gitignore 担保不了消费仓库。理由见 [`plan.md` §0c](./plan.md)。
> 沿革：rev1「run-dir 内」→ rev2「仓库级 + gitignore」→ rev3「用户级」。
> 三次落点变更针对的是同一条 P0：**写入不得改变被测仓库的内容指纹**。

---

## 主要矛盾

门拒绝一个操作时，这次拒绝不留任何痕迹（`die()` 只 print + exit，160 处调用点无一写记录）。
后果是**这套系统看不见自己在拒绝什么**，因而说不清哪道门在把代理逼去换 run-dir。

**本 slice 的核心约束**：让拒绝可见，且**不得因此改变任何一道门的判定**。
这两件事在错误的落点上不能同时成立——见 AC-2。

## 范围

### 做什么

1. 每一次 `die()` 记成一条可查的事实，落在**被测仓库之外**（用户级目录）；
2. `stats` 能消费它；
3. 提供**显式导出**命令，供跨机器分析。

### 明确不做（越界即返工）

- **不改变任何门的判定逻辑**——不放宽、不收紧、不新增、不删除任何诊断码
- **不改 `declared_exclusion_scope` 的语义**（按路径形态自动排除会给"藏后门"开口子，
  其 docstring 记录了三次被打穿的历史）
- **不向被测仓库写入任何文件**——不改 `.gitignore`，不在仓库内建目录。
  这是 rev3 的硬约束：任何仓库内落点都要靠"该仓库恰好忽略了它"担保，而 gate 跑在
  别人的仓库里，这个前提不成立
- 不动挑战循环（s2/s3）
- 不改 `_append` / `integrity_append` / 链算法
- 不改 `SCHEMA_VERSION`（保持 `1.5.0`），不改账本结构
- 不改任何既有命令的 stdout/stderr 文案与退出码
- **不修 `_stats_last_activity` 的既有 bug**——绕开它（见 AC-6），修它属另一个 slice

---

## 必须（MUST）

### AC-1 拒绝落盘，且带得起配对

任何以 `die()` 结束的 gate 调用，向
`$PLAN_TEST_REFUSAL_HOME`（默认 `~/.plan-test/`）下的
`refusals-<repo_key>.jsonl` 追加一条 JSON 行。

`repo_key` = 仓库根**绝对路径**的 sha256 前 16 位；定位不到仓库根时用 `no-repo`。
按仓库分文件，避免多仓混流。

| 字段 | 含义 | 缺失时 |
|---|---|---|
| `at` | ISO 时间戳 | 必有 |
| `repo` | 仓库根绝对路径（**脱敏后**） | 定位不到则 `null` |
| `cmd` | 子命令名 | 未解析出则 `null` |
| `code` | 诊断码（消息首段匹配 `^([A-Z][A-Z0-9_]{3,}):`） | 无码则 `null` |
| `run_dir` | run 目录：**在仓库根内**时为相对路径；在根外或定位不到时为**绝对路径脱敏值**，并置 `run_dir_external: true` | 该命令无 `--run-dir` 则 `null` |
| `detail` | 消息首行，脱敏后截断 500 字符 | 必有 |

> `run_dir` 的"根外"情形是真实可达的：`--allow-external-run-dir`（`plan_test_gate.py:2237`）
> 显式允许 run-dir 在仓库之外；嵌套仓库时向上查找命中的是**最近**的 `.git`，
> 可能与账本里的 `repo_root`（:2230）不是同一棵树。
> rev2 只写"转为相对仓库根"，这些情形下 `os.path.relpath` 会产出 `../..` 前缀的垃圾值，
> 且被 AC-3 的失败安全**静默吞掉**。rev3 显式定义之。

验证：用例覆盖四类——有 code 有 run_dir（`CONTROL_NOT_REQUIRED`）、
有 code 无 run_dir（`compile-manifest` 的失败）、无 code（"找不到 loop_id: x"）、
run_dir 在仓库根外（断言 `run_dir_external: true` 且不含 `../`）。

### AC-2 ⭐ 零指纹影响（本 slice 最关键的一条）

拒绝写入**不得改变**任何 run 的 `repo_content_digest`，因而不得使任何既有 receipt 变 stale、
不得把任何 run 打成 `TESTED_RUNTIME_MISMATCH`。

**且该性质必须是结构性的**：不得依赖被测仓库的 `.gitignore`、不得依赖排除范围声明。
判据——**在一个全新的、`.gitignore` 为空的临时 git 仓库里**触发拒绝，指纹仍不变。

验证**必须能真的判红**，三段都要有：

1. **正向（本仓）**：取一个真实 run 的冻结 `exclusion_scope` → 算 `repo_content_digest` →
   触发一次拒绝 → 重算 → 断言**逐字节相等**。
2. **正向（消费仓库形态）**：`git init` 一个临时仓库，`.gitignore` 为空或不存在 →
   在其中触发拒绝 → 断言 `git ls-files -c -o --exclude-standard` 的输出**未增加条目**。
   > 这一段是 rev3 新增的，直接对应被打穿的那条：rev2 的零指纹保证由"本仓 .gitignore 加一行"
   > 担保，而 gate 以插件形式在**别人的仓库**里运行，那行不随插件分发。
3. **反向（防 oracle 失效）**：把落点改成仓库内（错误实现）→ 同样流程 →
   断言 **digest 确实变化**。没有这一段，AC-2 在任何实现上都会通过。

> **背景**：rev1 的 AC-2 比的是同一 run 的 `ledger_sha256` / `content_digest` / 链值，
> 而致害通道是整仓 `repo_content_digest`（`validate` 重算），**不在同一个量上**——
> 该 oracle 按构造无法判红。实测：在 `plans/2026-07-27-gate-hardening/verification/slice-a/`
> 下新增一个文件，run-003 的指纹 `f6cb15b6…` → 变化 → 删除后恢复；
> run-003 的冻结排除范围只含自己那三个 run-dir，**不含** slice-a。

### AC-3 失败安全

写 refusal 的任何异常（目录不可建、磁盘满、路径被占用、序列化失败）**不得改变**
原本的 stderr 消息与退出码。

验证：用**跨平台**的失败注入——把 `refusals.jsonl` 预先建成**目录**（POSIX 与 Windows
均使写入失败），断言原错误消息逐字节不变、exit code 不变。
> 不用 `chmod`：本仓声明支持 Windows，且 root 下 chmod 无效，会导致用例在未注入任何失败的
> 情况下静默判绿。

### AC-4 不递归

`die()` 内部的写入路径**不得再调用 `die()`**，不得触发链校验。
`LEDGER_TAMPERED` 场景（`_append` 在链坏时自己 `die`）必须只输出一次错误。

验证：手改账本制造断链 → 执行写入命令 → 断言进程正常退出（非 `RecursionError`）、
stderr 只出现一次 `LEDGER_TAMPERED`、refusals.jsonl 有且仅有一条记录。

### AC-5 覆盖面实测，且判据可判红

`die()` 的 160 个调用点中，实际可记录的比例**必须实测并写进 `gate/PROTOCOL.md`**。

验证（**行为判据，不是清单自证**）：对**每一个**子命令构造一次必然失败的调用
（缺必填参数以外的方式，例如指向不存在的 run-dir、给非法 loop-id），
断言 `refusals-<repo_key>.jsonl` 中**确实新增了一条**且 `cmd` 字段正确。
任一子命令漏记即判红。

已知不可观测的两类，必须在 PROTOCOL.md 逐条列出并各配一个用例：
1. `parse_args` 之前的 `die`（现为 0 处，spike 实测——保留为将来防线）；
2. cwd 不在任何 git 仓库内（运行时条件，与调用点无关）——断言此时静默跳过、不报错。

> **rev2 的这条 oracle 不成立**：它写的是"遍历 `main()` 全部子解析器，断言声明的不可观测
> 集合与实际一致"，那是 rev1 按"有无 `--run-dir`"判可观测性时的判据。rev3 用 cwd 定位，
> 子解析器与可观测性再无关系，"不可观测集合"按构造为空，断言退化成空集等于空集——
> **任何实现都会通过**。这与 rev1 的 AC-2 是同一类缺陷，在重写中幸存了一轮。

### AC-6 stats 消费，且不复用已坏的时间源

`stats` 新增 refusal 段，输出三项：按 `code` 计数、按 `cmd` 计数、
**每个 `code` 的「拒绝 → 下一个新 run」间隔分布**（样本数 / 中位数 / 最小值；
样本 < 2 只列计数）。

配对规则（rev3 收窄，必须逐条实现）：

1. **按 verification 目录归属**：只与该 refusal 的 `run_dir` **同一父目录**下、
   `created_at` 晚于该 refusal 的新账本配对。跨 slice 的新账本不计入。
2. **多对一去重**：若多条 refusal 配到同一本新账本，**只保留时间最近的那条**，
   其余记为"未配对"。否则一次"换目录"会被计成 N 个样本，
   按码的 n 与中位数系统性膨胀——而按码排序正是本 slice 唯一的产出指标，可能因此反转。
3. `run_dir` 为 `null` 或 `run_dir_external` 的 refusal **不参与配对**，只进计数。
4. 时间源**只用**账本 `created_at` 与 refusal `at`；**禁止调用 `_stats_last_activity`**。

验证：`test_gate_stats.py` 新增用例，覆盖——非法 JSON 行不崩溃；
多条 refusal 配同一账本时只计一条；跨 verification 目录的账本不被配对；
并断言实现中未引用 `_stats_last_activity`。

> rev2 的规则写的是"同仓库内 `created_at` 最早的新账本"。对一个**每仓一份**的文件，
> "同仓库"是同义反复——`run_dir` 字段实际不参与任何配对判断，AC-1 却宣称它是"配对键"。
> 两条 AC 自相矛盾，rev3 一并修正。

> **背景**：`_stats_last_activity`（:3494）把 `integrity.chain` 当 list of dict 遍历，
> 而它实际是 **str**（时间戳在 `integrity.log`）——`isinstance(e, dict)` 恒 False，
> 该函数**永远**落到 `os.path.getmtime` 兜底。mtime 会被 clone/checkout 重置，
> 复用它会让间隔分布在换机与 CI 上系统性失真。这是既有 bug，本 slice 绕开、不修。

### AC-7 显式导出，且脱敏

`export-refusals --output <path>` 把 `~/.plan-test/refusals-<repo_key>.jsonl`
导出为可提交文件（默认当前仓库，`--repo-key` 可指定其他）。

- `--output` **必填**，无默认值（避免意外往仓库里写文件）；
- 导出内容**必须已脱敏**（落盘时即脱敏，导出再做一次兜底）；
- 导出前打印将写入的路径与条数，供人确认。

**脱敏规则必须覆盖 Windows**（本仓在 AC-3 明确声明支持 Windows）：

1. 仓库根前缀 → `<repo>`，比对前**分隔符归一**（`\` 与 `/` 视为等价），
   否则 ctx 里的 `C:\a\b` 与消息里的 `C:/a/b` 不相等，替换会静默漏掉；
2. 其余绝对路径 → `<path>`。Windows 路径**不得以空白为界**——
   `C:\Users\John Smith\proj\...` 会只替换掉 `C:\Users\John`，
   导出物残留 `Smith\proj\verification\...`，泄漏用户姓氏与目录结构。
   须匹配到行尾或到明确的分隔符（如 `）`、`"`、` 被`）为止。

验证：用例覆盖三种形态——POSIX（`LEDGER_LOCKED: /home/x/... 被其他进程持有`）、
Windows 无空格（`C:\proj\...`）、**Windows 含空格**（`C:\Users\John Smith\...`），
断言导出后均不含原路径片段；断言无 `--output` 时报错而非写默认位置。

> 反向的"误伤正常内容"风险实测较低：die 字面消息中含 `://` 的 0 条、
> 以 `/` 开头的非路径 token 0 条。真正的缺口是 Windows 下的**欠脱敏**，不是过脱敏。

> 导出产物一旦提交，会像**新增任何文件一样**进入 `repo_content_digest`。
> 这是正常仓库活动，不是本 slice 引入的副作用——区别在于它是**人显式发起的一次动作**，
> 而不是每次拒绝自动发生。此点须写进 `PROTOCOL.md`。

### AC-8 零回归、测试隔离与老仓兼容

- 现有测试**全绿**；
- **测试不得写入真实的 refusal 账本**；
- 无 `~/.plan-test/` 的环境，所有既有命令行为不变。

验证：`python3 -m unittest discover -s skills/plan-test/scripts -p 'test*.py'`，
**超时不得低于 300 秒**。

**测试隔离是硬要求**：测试基类必须把 `PLAN_TEST_REFUSAL_HOME` 指向 tmpdir，
并在用例中断言真实 `~/.plan-test/` 未被写入。
> **为什么必须有这条**：仓库根由 cwd 向上查找得出，而测试以子进程调 gate
> （`test_plan_test_gate.py:55-57`），**143 处 `run_gate(` 里只有 24 处传 `cwd`**——
> 其余继承测试运行者的 cwd，即真实仓库。跑一次套件会向真实账本追加上百条合成 refusal，
> 污染 AC-6 唯一的数据源，并提前触发 512 KB trim 把真实记录淘汰掉。
> rev1 用 `--run-dir`（天然落在 tmpdir）没有这个问题，是 rev2 改用 cwd 时引入的。

> **用例条数不写死**，只断言全绿。
> 更正 rev2 的一处错误：**292 就是 `unittest` 报告的真实用例数**（多次独立复跑均为 292），
> 静态 `grep "def test"` 得 216 才是不可比的口径（继承复用会让同一方法运行多次）。
> rev2 说"292 是错的口径"属归因颠倒，结论（不写死条数）仍然成立。

> 耗时实测 91.5 / 86.2 / 149.3 / 93.8 秒，波动大。
> **`HANDOFF-2026-08-28-runlog.md:284`**（不是 `HANDOFF.md`）里的
> "约 80 秒，注意别用 120s 超时跑"已过时，须一并更正——那条正是上一轮误报
> "测试套件不终止"的直接原因。

## 非功能边界

- 单个 `refusals-<repo_key>.jsonl` 上限 512 KB，超限**丢弃最旧的一半**而非停写——
  诊断数据不得阻塞交付。按仓库分文件，一个仓库的噪声不会淘汰另一个仓库的记录。
- trim 是读-改-写，**必须原子**（写临时文件后 `os.replace`），复用既有 `atomic_write_json`
  的思路。不得在无锁路径上做非原子整文件重写。
- 单条 `detail` 截断 500 字符，且**落盘时即脱敏**（不只在导出时）。
- append 不加锁：容忍并发交错，不容忍因它失败（AC-3 覆盖）。

## 不在本 slice 的已知遗留

- refusal 不进 integrity 链，**可被手工删改而无检测**。刻意取舍：它是诊断数据不是交付事实，
  进链会带来"误操作即改链值"与"垃圾命令灌链"两个新问题。
  将来若需防篡改，应在 s3 的 `decision` 原语里另行设计，**不要回头给 refusal 加链**。
- argparse 的 "invalid choice"（敲 `status` / `report` 等不存在的子命令）**不经过 `die()`**，
  本 slice 统计不到。补它属 s5。
- `_stats_last_activity` 的既有 bug 不修，仅绕开（AC-6）。
- 跨机器分析依赖人显式导出并提交，**不是自动同步**。
