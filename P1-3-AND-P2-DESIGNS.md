# P1-3, P1-2, P2-1, P2-2 详细设计

## P1-3: 定时主动报告

### 问题
本次执行约 16 小时，用户在此期间无感知，直到 WIP 已累积到 22,000 行无法安全回退。

### 解决方案
每 60-90 分钟主动报告进度。

### 实现方式
不是新增命令，而是**修改 SKILL.md 主循环**。

在 phase-3/4/5 执行过程中输出：
```
[PROGRESS CHECKPOINT]
- Elapsed: 2h 15m since phase start
- Phase: 3 (Execute)
- Completed: 5/12 tasks
- Last milestone: T3.1 committed (abc1234)
- Current WIP: +1247 lines, 8 files
- Ledger status: 12 runs, 5 evidence, 3 timing events
- Challenge loop: N/A
```

### 工作量：0.5 天
- 设计 ProgressTracker 类
- 集成到主循环
- 测试

---

## P1-2: Plan 增长用户确认

### 问题
Plan 从 1200 行增长到 2032 行，用户不知情。

### 命令
```bash
python plan_test_gate.py check-plan-growth \
  --baseline <baseline-plan.md> \
  --current <plan.md> \
  --max-growth-ratio 1.5
```

### 输出
```
PLAN_SCOPE_EXPANSION (advisory)

Plan 体量从 1200 行增长到 2032 行 (+69%)

建议确认：
1. 范围扩张是否合理？
2. 是否需要拆分为多个 slice？
```

### 工作量：0.5 天

---

## P2-1: 循环去重与可视化

### 命令
```bash
python plan_test_gate.py show-loop-history \
  --run-dir <run-dir> \
  --loop-id plan-iteration-001
```

### 输出
```
Challenge Loop History: plan-iteration-001

Round | Verdict | Critical | Major | Plan Hash    | Notes
------|---------|----------|-------|--------------|-------
1     | FAIL    | 3        | 5     | a1b2c3d4     |
2     | FAIL    | 2        | 3     | b2c3d4e5     |
3     | FAIL    | 2        | 2     | b2c3d4e5     | ⚠️  DUPLICATE
4     | PASS    | 0        | 1     | c3d4e5f6     |

Status: CONVERGED (round 4)
```

### 工作量：1 天

---

## P2-2: Phase 转移审计日志

### 命令
```bash
python plan_test_gate.py record-phase-transition \
  --run-dir <run-dir> \
  --from-phase phase-2 \
  --to-phase phase-3 \
  --convergence-evidence <hash> \
  --plan-hash <hash>
```

### 账本记录
```json
{
  "phase_transitions": [
    {
      "from": "phase-2",
      "to": "phase-3",
      "timestamp": "2026-08-14T16:00:00+0800",
      "convergence_evidence": "abc123...",
      "plan_hash": "def456...",
      "a2_count_at_transition": 0
    }
  ]
}
```

### phase-final DoD 审计
检查是否有 convergence_evidence、phase-3 期间是否发生 A2。

### 工作量：0.5 天

---

## 总结

### 短期（1 周内）- 防止失控
- **P0-3**: 循环失控（34 轮）- 2 天
- **P0-4**: Plan defect 累积 - 0.5 天
- **P1-3**: 长时间执行无感知 - 0.5 天

**这些是核心防护，没有它们同样的失败会再次发生。**

### 中期（1 个月内）- 提升可观测性
- **P1-2**: Plan 增长提醒 - 0.5 天
- **P2-1**: 循环历史可视化 - 1 天
- **P2-2**: Phase 转移审计 - 0.5 天

**事后审计和可视化，有了更好但不影响核心安全性。**
