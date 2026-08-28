# Scope Audit — s1 拆分为 s1a / s1b / s1c（2026-08-28）

> 本文件是 `SCOPE_AUDIT_REQUIRED` 的控制事件记录。
> **说明**：本 plan 的挑战循环没有走 gate 账本（无 run-dir / loop / assurance-contract，
> 第 3 轮 challenger 已指出 in-scope P1 因缺 assurance 绑定而无法 `record-challenge-round`
> 入账——这本身就是 program 主要矛盾的又一实例）。故控制事件以本文件留痕，
> 待 s2/s3 落地后此类事件才有机器账本可进。

## 触发

`config.md` `PLAN_CHALLENGE_SOFT_LIMIT: 3`——第 3 轮 closure 仍报出 **2 条新增 in-scope P1**
（`refusal-ctx-cwd-vs-explicit-root`、`ac5-per-subcommand-oracle-unsatisfiable`），
另有 1 条第 2 轮 P1 未闭环（`tests-write-real-refusal-ledger`，补救只覆盖 5 个
harness 根中的 1 个）。

## 审计结论：问题在范围，不在方案

三轮 P0/P1 的分布：

| 轮 | 问题落点 |
|---|---|
| 1 | 落点（run-dir 内） |
| 2 | 落点（仓库内 gitignore）+ 修 P0 时引入新 P1（测试污染） |
| 3 | 落点已对，但仓库身份仲裁冲突 + AC 自身不可实现 + 测试隔离不全 |

s1 实际背了四件事：① 记录拒绝（真目标）② 仓库身份管理 ③ 间隔配对指标 ④ 导出+脱敏。
**三轮的 P0/P1 绝大多数来自 ②③④。** 典型症状：rev2 落点在仓库内时需要"落盘即脱敏"，
rev3 落点移出仓库后该前提消失，需求却被保留，反过来把 `repo` 字段涂成零信息量的
`<repo>`——需求没有随设计变更收缩。

## 决定（业主批准）

**拆分**。业主原话：「拆」（2026-08-28，本会话）。

| 新 slice | 承接 | 范围 |
|---|---|---|
| **s1a** | ① | 只记录：`die()` 落一条**原始**记录到全局单文件；`stats` 只做计数。不分仓库、不配对、不导出、不脱敏 |
| **s1b** | ②③ | 间隔配对指标。**前置**：仲裁"当前仓库"的四种定义（`--root` / `--run-dir` / ledger `repo_root` / cwd 找 `.git`），并用 s1a 攒的真实数据定配对规则 |
| **s1c** | ④ | 导出 + 脱敏（含 Windows 分隔符归一、含空格路径） |

## 第 3 轮 open findings 的去向

| finding | 去向 |
|---|---|
| `tests-write-real-refusal-ledger`（P1，未闭环） | **s1a 必须解决**：`PLAN_TEST_REFUSAL_HOME` 全 harness 覆盖 + 套件级基线快照 |
| `refusal-ctx-cwd-vs-explicit-root`（P1，新增） | s1b（配对才需要仲裁；s1a 不配对，矛盾不成立） |
| `ac5-per-subcommand-oracle-unsatisfiable`（P1，新增） | s1a 消解：AC 改为"实测覆盖率并记入 PROTOCOL"，放弃全称断言（`print-schema` 实测无 die 可达路径，rc=0） |
| `refusal-home-inside-repo-unguarded`（P2） | s1a：默认路径加守卫，显式 override 归操作者（详见 s1a plan） |
| `repo-identity-degenerate-in-export` / `repo-key-path-normalization`（P2×2） | 随 s1a 取消 repo_key 与脱敏而消失；s1b/s1c 重新设计时再议 |
| `stats-swallows-systemexit-mislabels-refusal`（P2） | s1a 记为已知遗留（记录=die 调用，非进程终态；唯一吞 SystemExit 处在 `cmd_stats:3519`） |
| `plan-body-stale-to-rev2`（P2） | s1a 全新成文，旧目录归档，自然消解 |
| `pairing-metric-not-recomputed`（P2） | s1b：配对规则**用 s1a 真实数据重算**，不沿用 rollout 估算表 |
| `handoff-runlog-stale-test-count`（P2） | s1a T-doc：`HANDOFF-2026-08-28-runlog.md:282-284` 的"286 项"与"约 80 秒"一并更正 |
| `assurance-contract-absent`（advisory） | 记入 program §7（本次真的写了，可 grep 验证） |

## 本目录状态

`s1-refusal-ledger/` 自此**归档**：三个 rev 的 acceptance/plan 与两轮挑战处置表
（plan.md §7/§8）保留作历史，不再作为执行依据。执行依据是 `../s1a-refusal-log/`。
