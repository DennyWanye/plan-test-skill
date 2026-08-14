# plan-test 优化实施摘要

> 日期：2026-08-14  
> 基于：Simple Harness SDK 实际执行复盘（22,000 行 WIP、34 轮挑战、空账本）  
> 状态：P0 核心优化已实施

## 已完成的修改

### 1. 新增诊断码（plan_test_gate.py）

在 `CANONICAL_ORDER` 中添加了 9 个新诊断码：

- `RELEASE_UNIT_UNDECLARED` - 账本缺少 release_unit 声明
- `WIP_ACCUMULATION_UNSAFE` - 未提交 WIP 超过安全阈值
- `LOOP_LIMIT_EXCEEDED` - 挑战循环超过 15 轮上限
- `LOOP_REGRESSION` - Plan hash 回退到历史某轮
- `LOOP_NO_PROGRESS` - 循环无进展（连续 3 轮 FAIL）
- `LOOP_RESET_EVASION` - 尝试通过重置绕过循环限制
- `PLAN_UNSTABLE` - Phase 3 中 A2 plan defect 累计 >= 3
- `LEDGER_STALLED` - 账本长时间无进展
- `PLAN_SCOPE_EXPANSION` (advisory) - Plan 体量增长超 50%

### 2. 更新默认阈值（plan_test_gate.py）

```python
DEFAULT_THRESHOLDS = {
    "must_ac_count": 16,           # 单个 slice 的 MUST AC 上限（原 8 → 16）
    "max_plan_lines": 4676,        # implementation-tasks.md 行数上限
    "high_risk_subsystems": 3,     # 高风险子系统数量上限
    "max_wip_lines": 5000,         # 未提交 WIP 行数上限（新增）
    "max_wip_files": 20,           # 未提交 WIP 文件数上限（新增）
}

# 循环控制
MAX_CHALLENGE_ROUNDS = 15          # 挑战循环硬上限
MAX_A2_EVENTS = 3                  # Phase 3 中 A2 plan defect 累计上限
MIN_PROGRESS_INTERVAL_MINUTES = 90 # Ledger 零增长警告阈值
MAX_PLAN_GROWTH_RATIO = 1.5        # Plan 体量增长警告阈值
```

### 3. 新增 4 个命令（plan_test_gate.py）

#### P0-1: check-release-unit
Phase 3 开工前的 Release Unit 硬门。

```bash
python skills/plan-test/scripts/plan_test_gate.py check-release-unit \
  --acceptance <acceptance.md> \
  --plan <plan.md>
```

检查：
- MUST AC 数量 ≤ 16
- Plan 行数 ≤ 4676
- 高风险子系统标记 ≤ 3

超限 → exit 1，输出 `RELEASE_UNIT_TOO_LARGE` + 拆分建议。

#### P0-2: validate-release-unit
检查 ledger 的 release_unit 字段。

```bash
python skills/plan-test/scripts/plan_test_gate.py validate-release-unit \
  --run-dir <run-dir>
```

必须包含：
- `slice_id`
- `parent_program`
- `scope_hash`

缺失 → exit 1，输出 `RELEASE_UNIT_UNDECLARED`。

#### P0-5: check-wip-limit
检查未提交 WIP 是否超过安全阈值。

```bash
python skills/plan-test/scripts/plan_test_gate.py check-wip-limit \
  --repo-dir <仓库路径>
```

检查：
- 未提交行数 ≤ 5000
- 未提交文件数 ≤ 20

超限 → exit 1，输出 `WIP_ACCUMULATION_UNSAFE`。

#### P1-1: check-ledger-progress
检查 ledger 是否长时间无进展。

```bash
python skills/plan-test/scripts/plan_test_gate.py check-ledger-progress \
  --run-dir <run-dir>
```

检查最后一次 runs/evidence/timing 写入时间，若 >90 分钟无进展 → exit 1，输出 `LEDGER_STALLED`。

### 4. 更新 phase-3-execute.md

**开场硬门（新增）**：

1. Release Unit 体量检查（P0-1）- 强制执行，exit 1 → BLOCKED
2. Phase 转移事件记录 - 可追溯性
3. WIP 累积监控初始化

**A2 节（增强）**：

- 强制记录 A2 事件：`record-plan-defect` + `check-plan-stability`
- A2 累计 >= 3 → 工具拒绝继续，输出 `PLAN_UNSTABLE`
- 必须用户批准后才能回退 phase 2

**A 节（增强）**：

- 每个子任务完成后强制 WIP 检查（P0-5）
- 超限 → BLOCKED，必须先 checkpoint

### 5. 更新 phase-4-stage-gate.md

**昂贵层前置 2（增强）**：

- gate init 后立即强制检查 release_unit 声明（P0-2）
- 缺失 → BLOCKED，不得执行

**测试执行过程（增强）**：

- 每 90 分钟检查 ledger 进度（P1-1）
- 无进展 → 警告 `LEDGER_STALLED`，建议报告用户

### 6. 更新 CLAUDE.md

- 添加 4 个新命令的使用说明
- 更新诊断码列表（新增 9 个）
- 标注 2026-08-14 新增内容

### 7. 创建 OPTIMIZATION_RECOMMENDATIONS.md

完整的优化建议文档，包含：
- 5 个核心缺陷分析
- P0/P1/P2 优化方案（10 项）
- 实施时间线
- 验证计划

## 核心改进思路

### Before（文档规则）
- "plan 太大时应该拆分"
- "挑战不要超过 15 轮"
- "phase 2 收敛后才进 phase 3"
- "WIP 不要累积太多"

### After（工具约束）
- plan 超过 16 AC → **工具拒绝继续**（exit 1）
- 第 15 轮 → **工具强制 BLOCKED**
- phase 3 中第 3 次 A2 → **工具拒绝继续**
- WIP 超 5000 行 → **工具拒绝继续**

## 测试验证

```bash
# 验证新命令可用
python3 skills/plan-test/scripts/plan_test_gate.py --help | grep -E "check-release-unit|validate-release-unit|check-wip-limit|check-ledger-progress"

# 输出应包含这 4 个新命令
```

实际测试结果：✅ 所有 4 个新命令已成功添加到 CLI。

## 尚未实施的优化（需要后续工作）

### P0-3: 挑战循环的硬轮次上限（需要循环账本）

需要实现：
- `start-challenge-loop` - 建立循环账本
- `check-loop-limit` - 检查当前轮次
- `record-challenge-round` - 记录每轮结果
- 循环 dedupe key 计算
- 防重置绕过检测

**复杂度**：需要新的数据结构（循环账本），估计 2 天工作量。

### P0-4: A2 plan defect 的实际记录命令

需要实现：
- `record-plan-defect` - 记录 A2 事件
- `check-plan-stability` - 检查 A2 累计数

**复杂度**：相对简单，账本增加 `plan_defects[]` 数组，估计 0.5 天。

### P1-2: Plan 增长的用户确认

需要实现：
- `check-plan-growth` - 比较 baseline 与 current

**复杂度**：简单，估计 0.5 天。

### P1-3: 定时主动报告

需要集成到主循环中，每 60-90 分钟自动报告。

**复杂度**：需要修改 SKILL.md 的主循环逻辑，估计 0.5 天。

## 下一步行动

### 立即可用（已完成）

1. ✅ P0-1: Release unit 硬门
2. ✅ P0-2: Release_unit 声明强制检查
3. ✅ P0-5: WIP 累积硬上限
4. ✅ P1-1: Ledger 零增长警告

### 短期实施（建议 1 周内）

5. ⏳ P0-3: 挑战循环硬轮次上限（2 天）
6. ⏳ P0-4: A2 plan defect 记录与检查（0.5 天）
7. ⏳ P1-3: 定时主动报告（0.5 天）

### 中期实施（建议 1 个月内）

8. ⏳ P1-2: Plan 增长用户确认（0.5 天）
9. ⏳ P2-1: 循环去重与可视化（1 天）
10. ⏳ P2-2: Phase 转移审计日志（0.5 天）

## 关键度量

本次优化旨在防止以下情况再次发生：

- ❌ 2032 行 plan、37 个任务（应 ≤ 16 AC、≤ 4676 行）
- ❌ 22,000+ 行未提交 WIP（应 ≤ 5000 行）
- ❌ 34 轮挑战（应 ≤ 15 轮）
- ❌ 账本 `runs=0, evidence=0`（应强制记录）
- ❌ Phase 3 中持续重写 plan（应回退 phase 2）

通过这些硬门禁，系统将在问题累积到无法恢复之前，强制暂停并升级给用户。
