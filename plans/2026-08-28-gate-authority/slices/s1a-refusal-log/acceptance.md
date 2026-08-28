# Acceptance — s1a：只把拒绝记下来

> Program：[`../../program.md`](../../program.md)
> 拆分依据：[`../s1-refusal-ledger/SCOPE-AUDIT-2026-08-28.md`](../s1-refusal-ledger/SCOPE-AUDIT-2026-08-28.md)
> **唯一真相来源。** 本文未列的行为一律不在范围内。

---

## 主要矛盾

门拒绝一个操作时不留任何痕迹（`die()` 只 print + exit，160 处调用点无一写记录），
系统看不见自己在拒绝什么。**本 slice 只解决"看得见"，一个字都不多做。**

## 范围

### 做什么

1. 每次 `die()` 向**一个全局文件**追加一条**原始**记录；
2. `stats` 按诊断码、按子命令**计数**。

### 明确不做（越界即返工；这些是三轮挑战证明会翻车的地方）

- 不按仓库分文件、无 `repo_key`、无仓库身份判定（→ s1b）
- 不做「拒绝 → 新 run」配对与间隔分布（→ s1b）
- 不做导出、不做脱敏——**本机原始数据，记原文**（→ s1c）
- 不改任何门的判定、不新增诊断码、不改 schema、不改既有命令的输出与退出码
- 不向被测仓库写任何文件
- 不修 `_stats_last_activity` 的既有 bug（本 slice 不用任何时间源聚合，天然不碰它）

---

## 必须（MUST）

### AC-1 拒绝落盘

任何以 `die()` 结束的调用，向 `$PLAN_TEST_REFUSAL_HOME/refusals.jsonl`
（默认 `~/.plan-test/refusals.jsonl`）追加一行 JSON：

| 字段 | 内容 | 缺失时 |
|---|---|---|
| `at` | ISO 时间戳 | 必有 |
| `cwd` | 进程 cwd，**原文** | 必有 |
| `cmd` | 子命令名 | 未解析出则 `null` |
| `code` | 消息首段匹配 `^([A-Z][A-Z0-9_]{3,}):` | 无码则 `null` |
| `run_dir` | `--run-dir` 参数值，**按用户所给原文**（不相对化、不解释） | 无该参数则 `null` |
| `detail` | 消息首行，截断 500 字符，**不脱敏** | 必有 |

验证：用例覆盖三类——有 code 有 run_dir（`CONTROL_NOT_REQUIRED`）、
有 code 无 run_dir（`compile-manifest` 失败）、无 code（"找不到 loop_id: x"）。

> 记原文是刻意的：这是本机诊断数据，不进 git、不出机器。加工丢的信息补不回来
> （rev3 的 `repo` 字段被脱敏成零信息量就是教训）；解释留给读数据的人（s1b/s1c）。

### AC-2 零指纹影响，且默认路径带守卫

拒绝写入不得改变任何 run 的 `repo_content_digest`。

**守卫**：默认路径（无环境变量覆盖）下，若解析出的落点位于当前定位到的 git 仓库内
（`$HOME` 本身是 dotfiles 仓库的情形），**跳过写入**——宁可少记，不可打红别人的 run。
显式设置 `PLAN_TEST_REFUSAL_HOME` 时不设防，责任归操作者（这也给反向用例留了口）。

验证三段：
1. 正向（本仓）：取真实 run 的冻结 `exclusion_scope` 算 digest → 触发拒绝 → 重算 → 逐字节相等；
2. 正向（消费仓库形态）：`git init` 临时仓库（`.gitignore` 空）→ 在其中触发拒绝 →
   `git ls-files -c -o --exclude-standard` 条目数不变；
3. 反向（防 oracle 退化）：`PLAN_TEST_REFUSAL_HOME` 显式指进临时仓库内 → 触发拒绝 →
   断言 ls-files 条目**确实增加**。

### AC-3 失败安全

写入的任何异常不得改变原 stderr 消息与退出码。
验证：把 `refusals.jsonl` 预先建成**目录**（POSIX/Windows 均使写入失败），
断言消息逐字节不变、exit code 不变。

### AC-4 不递归

写入路径不得调用 `die()`、不得触发链校验。
验证：手改账本制造断链 → 执行写入命令 → 进程正常退出（非 `RecursionError`）、
stderr 只出现一次 `LEDGER_TAMPERED`、refusals.jsonl 恰一条。

### AC-5 覆盖面实测入档（不做全称断言）

实测并写入 `gate/PROTOCOL.md`：哪些子命令/路径的拒绝会被记录、哪些不会，各配理由。
已知不记录的三类须逐条列出：
1. `parse_args` 之前的 die（现为 0 处，spike 实测；防线保留）；
2. 无 die 可达路径的子命令（如 `print-schema`，实测 rc 恒 0）；
3. argparse "invalid choice"（不经过 `die()`，归 s5）。

验证：对 PROTOCOL 声明"会记录"的每类**抽一个代表**做行为用例（构造必败调用 → 断言新增一条）。
> 不做"46 个子命令逐个断言"的全称判据——第 3 轮实测证明它不可实现
> （`print-schema` 没有失败路径），那样的 AC 只能靠实现者私下放宽，恰是 oracle 退化的温床。

### AC-6 stats 计数

`stats` 新增 refusal 段：按 `code` 计数（`null` 归"无诊断码"）、按 `cmd` 计数、总条数。
无文件/空文件输出"无"；坏行跳过不崩溃。**不做任何时间聚合。**
验证：`test_gate_stats.py` 用例覆盖正常计数与坏行。

### AC-7 零回归 + 套件级测试隔离

- 现有测试全绿（超时 ≥300 秒；条数不写死）；
- **全部** harness 根隔离：`PLAN_TEST_REFUSAL_HOME` 指向 tmpdir 须覆盖
  `GateHarness`、`RealRepoAttestationTestCase`、`FixtureReplayTestCase`、
  `StatsHarness`（test_gate_stats.py）、`PhaseCostTest`（test_phase_cost.py）**五个根**
  （第 3 轮实测清单，实现时以实际为准重查）；
- **套件级基线快照**：`setUpModule` 记录真实 `~/.plan-test/` 状态 → `tearDownModule`
  断言未变。
  > 断言写在已隔离的用例内是"按构造无法失败"——它看不见其他 harness 在别的时刻的写入。
  > 这类 oracle 缺陷已三轮三现（rev1 AC-2 / rev2 AC-5 / rev3 AC-8），此为第四次设防。

## 已知遗留（写进 PROTOCOL，不在本 slice 修）

- 记录含本机路径**明文**，文件不进 git、不出机器；跨机器分析走 s1c 的导出+脱敏。
- 记录的语义是"`die()` 被调用"，**不是"进程以失败终止"**：全仓唯一吞 `SystemExit` 的
  `cmd_stats`（`plan_test_gate.py:3519-3522`）内部的 die 会留下记录而进程 rc=0。
  s1b 做配对时须知此口径。
- refusal 可被手工删改无检测（诊断数据，非交付事实；防篡改若需要归 s3 的 decision 原语）。
- 单文件 512 KB 上限，超限原子地（临时文件 + `os.replace`）丢弃最旧一半。
