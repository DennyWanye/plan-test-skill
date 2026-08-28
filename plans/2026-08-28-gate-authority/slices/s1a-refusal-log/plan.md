# 技术 plan — s1a：只把拒绝记下来

> AC 唯一真相：[`acceptance.md`](./acceptance.md)
> 目标文件：`skills/plan-test/scripts/plan_test_gate.py`
> 历史与已验证结论：[`../s1-refusal-ledger/plan.md`](../s1-refusal-ledger/plan.md)
> （§0 三条代码约束、§0b 四条 spike、§7/§8 两轮挑战处置——**均沿用，不重复验证**）
> **plan-status: finalized**（3 轮挑战 + scope-audit 拆分 + 业主批准，2026-08-28）
> 本体是收缩不是新设计：全部风险面继承三轮挑战的已验证结论（见归档目录），
> 新增面（全局单文件、默认守卫）均为删复杂度。

---

## 0. 继承的已验证约束（来源见归档 plan，此处只列结论）

1. refusal 不能进账本（`ledger_sha256` 覆盖除 `revision` 外全部字段，:1967）；
2. 不能走 `_append`（写前验链、链坏自己 die → 递归；spike 实测无防护递归 51 层）；
3. `die()` 无 run_dir 形参，160 调用点不可改签名 → 模块级上下文；
4. `SystemExit` 继承 `BaseException`，`except Exception` 吞不掉（H1）；
5. 重入标志有效（H2）；写入失败不改变原消息与退出码（H3）；
6. `main()` 里 `parse_args` 前与模块导入期 die 均为 0 处（H4，短路防线仍保留）；
7. 任何仓库内落点都会进 `repo_content_digest`（两轮 P0 实测），落点必须在仓库外。

## 1. 设计（全部从简）

### 1.1 落点：一个全局文件

```
$PLAN_TEST_REFUSAL_HOME/refusals.jsonl     默认 ~/.plan-test/refusals.jsonl
```

不分仓库。多仓混流由记录里的 `cwd` 原文区分——**读的时候再分，写的时候不分**。

### 1.2 默认路径守卫（AC-2）

写入前一次性判断（结果缓存）：

```python
if not os.environ.get("PLAN_TEST_REFUSAL_HOME"):
    repo = _find_repo_root(os.path.dirname(refusal_path))   # 从落点向上找 .git
    if repo is not None:
        return   # 默认落点竟在某个 git 仓库内（$HOME 是 dotfiles 仓库）——跳过，宁少记不打红
```

显式设置环境变量则不设防——这同时是 AC-2 反向用例的注入口。
`_find_repo_root`：向上找 `.git`（目录或文件），最多 40 层，结果缓存。

### 1.3 上下文与写入函数

```python
_REFUSAL_CTX = {"cmd": None, "run_dir": None, "writing": False}

def _record_refusal(msg):
    if _REFUSAL_CTX["writing"]:
        return
    _REFUSAL_CTX["writing"] = True
    try:
        ...   # 组装 {at, cwd, cmd, code, run_dir, detail}，追加写；超限则原子 trim
    except Exception:
        pass  # 失败安全：吞掉一切（SystemExit 除外，见约束 4）
    finally:
        _REFUSAL_CTX["writing"] = False

def die(msg, code=2):
    _record_refusal(msg)          # ← 唯一侵入点，先记后打
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)
```

`main()` 在 `parse_args` 后填 `cmd` / `run_dir`（原文，不加工）。
`cwd` 在写入时取 `os.getcwd()` 原文。`code` 取消息首段 `^([A-Z][A-Z0-9_]{3,}):`。

### 1.4 原子 trim

超 512 KB：读全部行 → 保留后一半 → 写临时文件 → `os.replace`（两平台原子）。

### 1.5 stats（AC-6）

`cmd_stats` 尾部加一段：读文件、逐行 `json.loads`（坏行跳过）、
按 `code` 与 `cmd` 各出一张计数表 + 总条数。无文件输出"（无）"。不碰任何时间字段。

## 2. 任务（6 个）

| # | 任务 | AC |
|---|---|---|
| T1 | `_find_repo_root` + 默认路径守卫 + `PLAN_TEST_REFUSAL_HOME` | AC-2 |
| T2 | `_REFUSAL_CTX` / `_record_refusal` / `die()` 一行 / 原子 trim | AC-1,3,4 |
| T3 | `cmd_stats` 计数段 | AC-6 |
| T4 | **测试隔离**：五个 harness 根设环境变量 → tmpdir；套件级基线快照（setUpModule/tearDownModule） | AC-7 |
| T5 | 用例：AC-1 三类 / AC-2 三段 / AC-3 目录注入 / AC-4 断链 / AC-6 计数与坏行 / AC-5 代表性行为用例 | AC-1~6 |
| T6 | 文档：PROTOCOL.md 新增一节（覆盖面实测清单 + 已知遗留四条）；更正 `HANDOFF-2026-08-28-runlog.md:282-284`（"286 项"与"约 80 秒"均过时，实测 292 项 / 86–150 秒） | AC-5,7 |

## 3. 实施顺序（每步一个 commit）

1. **T4 先行**——隔离不就位，后面每一步跑测试都在污染真实文件（第 2/3 轮实测的坑）；
2. T5 中 AC-2 反向用例 + AC-4 断链用例**先写并确认在无实现时失败**；
3. T1+T2；4. T3+T5 其余；5. T6。

## 4. 风险

| 风险 | 缓解 |
|---|---|
| `except Exception` 吞真 bug | T5 正向断言"正常时确实写了" |
| 并发 append 交错 | 逐行解析跳坏行；坏行用例 |
| 守卫误伤（用户真想放仓库里） | 显式环境变量即放行，PROTOCOL 写明 |
| 五个 harness 清单过时 | T4 动工时以 `grep -n "run_gate\|subprocess.run.*GATE" test*.py` 实查为准 |

## 5. 回滚

`git revert` 即净；`~/.plan-test/` 是本机数据，残留无影响（AC-7 覆盖"无此文件行为不变"）。

## 6. 与后续 slice 的接口（冻结两条，其余自由）

s1b/s1c 只依赖两件事：**文件是 JSONL、每条含 `at`/`cwd`/`cmd`/`code`/`run_dir`/`detail` 六字段**。
字段语义（原文、不加工）一并冻结。除此之外 s1b/s1c 不得反过来要求 s1a 改记录格式——
要加字段走新 slice 的 schema 演进，别回头翻烧饼。
