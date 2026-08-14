# P0-3: 循环账本详细设计

## 问题
T4.2 挑战推进到第 34 轮，`MAX_ROUNDS=15` 完全失效。代理可以：
- 重命名 plan 文件继续
- 声称"这是新问题"重新计数
- 删除循环记录重来

## 解决方案：持久化循环账本

### 数据结构

在 `plan-test-run.json` 中新增：

```json
{
  "challenge_loops": [
    {
      "loop_id": "plan-iteration-001",
      "loop_type": "plan-iteration",
      "target_file": "plans/xxx/plan.md",
      "baseline_hash": "abc123...",
      "started_at": "2026-08-14T10:00:00+0800",
      "rounds": [
        {
          "round": 1,
          "plan_hash": "abc123...",
          "dedupe_key": "def456...",  // sha256(plan_content + challenger_prompt)
          "findings": {
            "critical": 3,
            "major": 5,
            "minor": 2
          },
          "verdict": "FAIL",
          "timestamp": "2026-08-14T10:30:00+0800"
        },
        {
          "round": 2,
          "plan_hash": "bcd234...",
          "dedupe_key": "efg567...",
          "findings": {
            "critical": 2,
            "major": 3,
            "minor": 1
          },
          "verdict": "FAIL",
          "timestamp": "2026-08-14T11:00:00+0800"
        }
      ],
      "status": "active"  // active | converged | exceeded
    }
  ]
}
```

### 需要的命令

#### 1. start-challenge-loop
```bash
python plan_test_gate.py start-challenge-loop \
  --run-dir <run-dir> \
  --loop-type plan-iteration \
  --target-file plans/xxx/plan.md \
  --baseline-hash <sha256>
```

返回 `loop_id`，后续命令都引用它。

#### 2. check-loop-limit
```bash
python plan_test_gate.py check-loop-limit \
  --run-dir <run-dir> \
  --loop-id plan-iteration-001
```

- 当前轮次 >= 15 → exit 1, `LOOP_LIMIT_EXCEEDED`
- 输出：已执行 N 轮，还剩 M 轮

#### 3. record-challenge-round
```bash
python plan_test_gate.py record-challenge-round \
  --run-dir <run-dir> \
  --loop-id plan-iteration-001 \
  --round 3 \
  --findings findings.json \
  --plan-hash <current sha256> \
  --verdict PASS
```

自动计算 dedupe_key，检测：
- 若 plan hash 回退到历史某轮 → 警告 `LOOP_REGRESSION`
- 若连续 3 轮 critical findings 不减 → 警告 `LOOP_NO_PROGRESS`
- 若 dedupe_key 与历史重复 → 警告 "可能陷入循环"

#### 4. 防重置检测

在 `check-loop-limit` 中：
- 检测账本被删除、loop_id 改变、或 target_file 改名
- 若新 target_file 与历史某个的内容相似度 > 80% → `LOOP_RESET_EVASION`

### 工作量估计：2 天

- Day 1 上午：设计 schema，实现 start/check/record 命令
- Day 1 下午：实现 dedupe key、regression 检测、no-progress 检测
- Day 2 上午：实现防重置检测（文件相似度计算）
- Day 2 下午：写测试用例、集成到 phase-2-iterate-plan.md

### 集成到 phase-2

修改 `phase-2-iterate-plan.md`：

```markdown
## 开场：建立循环账本

```bash
loop_id=$(python plan_test_gate.py start-challenge-loop \
  --run-dir <run-dir> \
  --loop-type plan-iteration \
  --target-file <plan.md> \
  --baseline-hash $(sha256sum <plan.md> | cut -d' ' -f1))
```

## 每轮挑战前

```bash
python plan_test_gate.py check-loop-limit \
  --run-dir <run-dir> \
  --loop-id $loop_id
```

exit 1 → 立即 BLOCKED，升级给用户。

## 每轮挑战后

```bash
python plan_test_gate.py record-challenge-round \
  --run-dir <run-dir> \
  --loop-id $loop_id \
  --round $N \
  --findings <challenger-output.json> \
  --plan-hash $(sha256sum <plan.md> | cut -d' ' -f1) \
  --verdict <PASS|FAIL>
```
```

## 为什么重要

这是**本次失败的最明显信号**：34 轮挑战 = 循环失控。没有这个，代理可以无限循环。
