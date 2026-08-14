# P0-4: A2 Plan Defect 记录详细设计

## 问题
Handoff §7.4 指出："phase 3 中持续重写 plan"，说明 phase 2 未真正收敛。

现状：
- phase-3-execute.md A2 节只说"回炉 plan"
- 代理可以无限次回炉而不被察觉
- 没有机器记录累计了多少次 A2

## 解决方案：在账本中记录 A2 事件

### 数据结构

在 `plan-test-run.json` 中新增：

```json
{
  "plan_defects": [
    {
      "event_id": "a2-001",
      "occurred_at": "2026-08-14T15:30:00+0800",
      "affected_tasks": ["T4.1", "T4.2"],
      "defect_type": "contract-conflict",
      "description": "WorkflowLease 与 Runtime lease 的 owner 责任未明确",
      "resolution": "回退 phase-2，修订 H16 contract",
      "resolved_at": "2026-08-14T18:00:00+0800"
    },
    {
      "event_id": "a2-002",
      "occurred_at": "2026-08-14T20:15:00+0800",
      "affected_tasks": ["T3.2"],
      "defect_type": "scope-drift",
      "description": "child signal claim authority 未在 T2.3 中声明",
      "resolution": null,  // 尚未解决
      "resolved_at": null
    }
  ]
}
```

### 需要的命令

#### 1. record-plan-defect（已在 phase-3-execute.md 中引用）

```bash
python plan_test_gate.py record-plan-defect \
  --run-dir <run-dir> \
  --affected-tasks T4.1,T4.2 \
  --defect-type contract-conflict \
  --description "具体问题描述"
```

功能：
- 写入 `plan_defects[]` 数组
- 生成唯一 `event_id`
- 记录时间戳
- 写入 integrity 链（op=record_plan_defect）

#### 2. check-plan-stability（已在 phase-3-execute.md 中引用）

```bash
python plan_test_gate.py check-plan-stability \
  --run-dir <run-dir>
```

功能：
- 统计未解决的 A2 事件数量
- 若 >= 3 → exit 1, `PLAN_UNSTABLE`
- 输出每个 A2 的简要信息

诊断消息：
```
PLAN_UNSTABLE

Phase 2 未真正收敛，已累计 3 次 plan defect：

1. [a2-001] contract-conflict: WorkflowLease owner 责任未明确
   - 影响任务: T4.1, T4.2
   - 发生时间: 2026-08-14T15:30:00
   - 状态: 已解决

2. [a2-002] scope-drift: child signal claim authority 漏声明
   - 影响任务: T3.2
   - 发生时间: 2026-08-14T20:15:00
   - 状态: 未解决

3. [a2-003] 假设失败: precreated admission 无 zero-seed 顺序
   - 影响任务: T4.2
   - 发生时间: 2026-08-14T22:00:00
   - 状态: 未解决

建议：
- 禁止继续叠加 WIP
- 提交或 stash 当前改动
- 回退 phase-2 重新迭代 plan
- 清空 A2 计数后才能恢复 phase-3
```

#### 3. resolve-plan-defect（可选）

```bash
python plan_test_gate.py resolve-plan-defect \
  --run-dir <run-dir> \
  --event-id a2-002 \
  --resolution "已修订 T2.3，补充 claim authority"
```

标记某个 A2 已解决，减少未解决计数。

#### 4. reset-plan-defects（需要用户批准）

```bash
python plan_test_gate.py reset-plan-defects \
  --run-dir <run-dir> \
  --approval-hash <用户批准消息的 sha256> \
  --reason "已回退 phase-2 并重新收敛"
```

清空 A2 计数，允许重新进入 phase-3。

### 工作量估计：0.5 天

- 上午：实现 record-plan-defect、check-plan-stability
- 下午：实现 resolve-plan-defect、reset-plan-defects，写测试用例

### 集成到 phase-3-execute.md

已经在刚才的修改中引用了这两个命令（第 42-56 行）：

```markdown
3. **处理铁律：回炉，不绕行**：
   - **立即停止受影响的执行线**（其余独立任务可继续）；
   - **记录 A2 事件（P0-4 新增，强制）**：
     ```bash
     python plan_test_gate.py record-plan-defect \
       --run-dir <run-dir> \
       --affected-tasks <任务 ID 列表，逗号分隔> \
       --defect-type <...> \
       --description "..."
     ```
   - **检查 A2 累计数（强制）**：
     ```bash
     python plan_test_gate.py check-plan-stability \
       --run-dir <run-dir>
     ```
```

现在只需要实现这两个命令即可。

## 为什么重要

H9-H16 的多次 A2 返工证明 plan 精度缺口在执行期才暴露。如果第 3 次 A2 时就强制暂停，
可以避免继续叠加 WIP 到 22,000 行。
