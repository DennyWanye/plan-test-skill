# Phase 2 — 条件细则（命中条件才读）

主流程见 `../phase-2-iterate-plan.md`。

## 行为契约

触发：需求触及易混实体（Session、Run、Task、话题、窗口、Profile、Driver 等）或会改变既有行为。定稿前：

1. 产出结构化行为契约；未获授权的重要行为变化纳入一次 plan review（RULES R11），已明确授权的行为逐项绑定原始请求，不换措辞反复问：
   - 术语表与实体关系（一个入口 ≠ 一个 Session；一个 Session 可有多个 Run……）；
   - before / after 行为表：现有行为 vs 目标行为逐行对照；
   - 明确保留、删除、改变的旧行为清单。
2. 行为契约与用户批准记录存 plan 文件夹（FULL 另入 gate 账本，见 `../full/phase-2-iterate-plan.md` §行为契约入账）。acceptance 每个行为断言都要能回溯到这张表。
3. 可选派 `prompts/acceptance-challenger.md` 挑战语义遗漏；它只产出风险与建议，不能替代结构化批准与 deterministic gate。

## 大仓基线

触发：测试文件 ≥ 200 或单套件预计 > 5 分钟。

- 必须用 `scripts/baseline_runner.py`，不许单条全量命令裸跑。
- 仓库根维护 `baseline-shards.json` 分片清单（没有就本次建好留给下次）。
- runner 提供：每片心跳、超时精确杀进程树、既有失败签名（`baseline-known-failures.json`）、新红即停、`--resume` 跳过已绿分片。
- 基线既有红用 `--accept-current-failures` 记入签名文件；新红永远阻断。
- `baseline.md` 记 runner 的 state / known-failures 文件路径。
