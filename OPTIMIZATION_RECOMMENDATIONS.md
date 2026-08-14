# plan-test Skill 优化建议

> 来源：2026-08-14 Simple Harness SDK 实际执行复盘  
> 状态：基于真实 22,000 行 WIP、34 轮挑战、空机器账本的失败案例  
> 目标：把文档规则变成工具强制执行的硬门禁

## 执行摘要

本次使用暴露了 5 个关键缺陷，导致一个应拆分为 7 个独立 slice 的 program 被当作单一 release unit 推进了约 16 小时，累积 22,000+ 行未提交 WIP 后被迫暂停：

1. **`RELEASE_UNIT_LIMITS` 只是文档规则**，phase 3 开始前不是硬门；
2. **机器账本未真正使用**（`runs=0`，`release_unit={}`），绕过了全部 gate 协议；
3. **挑战循环失控**（第 34 轮仍在继续，未触发第 15 轮 BLOCKED）；
4. **Phase 2 未收敛就进入 Phase 3**，导致执行期持续重写 plan；
5. **缺少主动暂停机制**，无法在危险信号出现时及早停止。

优化重点：**把纪律变成工具约束**，而不是依赖代理自觉或人工监督。

---

## P0：必须修复的硬门禁

### P0-1：Phase 3 开工前的 Release Unit 硬门

**问题**：`implementation-tasks.md` 2032 行、37 个任务，远超 `RELEASE_UNIT_LIMITS`（≤16 条 MUST AC / ≤4676 行），但仍进入 phase 3 实现。

**根因**：`config.md` 定义了 limits，但 `phase-3-execute.md` 只写"超限 → validator 直接 `RELEASE_UNIT_TOO_LARGE`"，实际并未调用 validator。

**修复方案**：

1. **在 phase-3-execute.md 开场增加强制检查点**：
   ```markdown
   ## 开场硬门（每次 phase 3 必做，不可跳过）
   
   1. 运行 release unit 预检：
      ```bash
      python skills/plan-test/scripts/plan_test_gate.py check-release-unit \
        --acceptance <acceptance.md> \
        --plan <plan.md> \
        --implementation-tasks <implementation-tasks.md>
      ```
   
   2. exit 0 才能继续；exit 1 输出 `RELEASE_UNIT_TOO_LARGE` → 立即 BLOCKED，
      升级给用户，附带拆分建议（按 AC 分组、风险子系统隔离）。
   
   3. 禁止删除 AC、合并任务或降级 MUST 为 SHOULD 来绕过。
   ```

2. **实现 `check-release-unit` 子命令**（加入 `plan_test_gate.py`）：
   - 统计 acceptance 的 MUST AC 数量（≤ `MAX_AC_PER_SLICE`，默认 16）；
   - 统计 implementation-tasks 总行数（≤ `MAX_PLAN_LINES`，默认 4676）；
   - 分析涉及的高风险子系统标记（如 `[HIGH_RISK: SQLite/Kernel/Recovery]`），
     要求 ≤ `MAX_HIGH_RISK_SUBSYSTEMS`（默认 3）；
   - 超限时输出诊断码 `RELEASE_UNIT_TOO_LARGE`，建议拆分方案（按功能/层次/风险分组）。

3. **测试覆盖**：
   - 16 MUST AC + 4676 行 → PASS；
   - 17 MUST AC → `RELEASE_UNIT_TOO_LARGE`；
   - 4677 行 → `RELEASE_UNIT_TOO_LARGE`；
   - 4 个 HIGH_RISK 标记 → `RELEASE_UNIT_TOO_LARGE`。

**优先级**：P0 - 单次执行最大的浪费来源，必须在工具层阻断。

---

### P0-2：Phase 4 强制 gate init 与 release_unit 声明

**问题**：机器账本 `release_unit = {}`、`runs = 0`、`evidence = 0`，说明整个执行绕过了 gate 协议。

**根因**：phase-4-stage-gate.md 文档要求 `gate init`，但代理可以跳过或假装做了。

**修复方案**：

1. **在 phase-4 开场增加强制初始化**：
   ```markdown
   ## 昂贵层前置（强制，不可省略）
   
   1. 若 run-dir 不存在，运行：
      ```bash
      python skills/plan-test/scripts/plan_test_gate.py init \
        --run-dir <plan>/verification/<run-id> \
        --manifest manifest.json
      ```
   
   2. 检查 `plan-test-run.json` 必须存在，且 `release_unit` 必须非空：
      ```bash
      python skills/plan-test/scripts/plan_test_gate.py validate-release-unit \
        --run-dir <run-dir>
      ```
      
      exit 1 → 立即 BLOCKED："机器账本缺少 release_unit 声明，禁止空账本执行"。
   
   3. manifest.json 必须声明：
      - `release_unit.slice_id`（本次 slice 标识符，如 "T4.1-A"）
      - `release_unit.parent_program`（所属 program，如 "SDK-extraction"）
      - `release_unit.scope_hash`（acceptance + plan 的内容 hash）
   ```

2. **实现 `validate-release-unit` 子命令**：
   - 读取 `plan-test-run.json`，检查 `release_unit` 字段；
   - 必须包含 `slice_id`、`parent_program`、`scope_hash`；
   - 缺失任一字段 → exit 1，输出 `RELEASE_UNIT_UNDECLARED`。

3. **修改 phase-final-dod.md 交付措辞模板**：
   ```markdown
   RELEASE UNIT: <slice_id>
   PARENT PROGRAM: <parent_program>
   SCOPE HASH: <前 8 位>
   REQUIRED GATES: PASS
   ...
   ```

**优先级**：P0 - 没有这个，机器门禁等于不存在。

---

### P0-3：挑战循环的硬轮次上限与去重

**问题**：T4.2 挑战推进到第 34 轮，远超 `MAX_ROUNDS=15`，说明循环控制失效。

**根因**：
1. phase-2-iterate-plan.md 只写"超限 → BLOCKED"，但代理可以重命名文件、开新 plan 或声称"这是新问题"继续；
2. 没有记录 `loop_id`、dedupe key 和重置原因，无法机器检测"换汤不换药"。

**修复方案**：

1. **在 phase-2 开场建立循环账本**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py start-challenge-loop \
     --run-dir <run-dir> \
     --loop-type plan-iteration \
     --target-file <plan.md> \
     --baseline-hash <plan 内容 SHA-256>
   ```

2. **每轮挑战开始前必须调用**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py check-loop-limit \
     --run-dir <run-dir> \
     --loop-type plan-iteration
   ```
   
   - 读取账本，当前轮次 >= `MAX_ROUNDS` → exit 1，输出 `LOOP_LIMIT_EXCEEDED`；
   - 同时输出已执行轮次、每轮的 finding 数量、plan hash 变化历史。

3. **每轮挑战结束后记录**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py record-challenge-round \
     --run-dir <run-dir> \
     --loop-type plan-iteration \
     --round <N> \
     --findings <挑战输出 JSON> \
     --plan-hash <当前 plan.md SHA-256> \
     --verdict <PASS|FAIL>
   ```
   
   - 若 plan hash 回退到历史某轮 → 诊断码 `LOOP_REGRESSION`，警告"plan 退化，可能陷入循环"；
   - 若连续 3 轮 FAIL 且 critical findings 数量不减 → `LOOP_NO_PROGRESS`。

4. **禁止重置绕过**：
   - 若检测到删除账本、改 loop-type、或换 target-file，且内容 hash 相似度 > 80% 
     → 诊断码 `LOOP_RESET_EVASION`，拒绝继续。

5. **phase-2 出口条件修订**：
   - 原："有新增 P0/P1 才续轮，无新增即收敛"；
   - 改为："连续 2 轮 PASS 且 plan hash 稳定（最后两轮 hash 相同）才算收敛；
     或达到 `PLAN_ITERATIONS` 下限且最后一轮 PASS；
     或达到 `MAX_ROUNDS` 上限 → BLOCKED。"

**优先级**：P0 - 34 轮挑战是最明显的失控信号。

---

### P0-4：Phase 3 中的 A2 plan defect 强制暂停

**问题**：Handoff §7.4 指出"phase 3 中持续重写 plan"，说明 phase 2 未收敛就进入了 phase 3。

**根因**：phase-3-execute.md 的 A2 规则只说"affected line 停止，回炉 plan"，但代理可以继续其他任务。

**修复方案**：

1. **在 phase-3-execute.md A2 节增加强制流程**：
   ```markdown
   ### A2：Plan defect identified（强制全停）
   
   若执行期发现 plan 精度缺口（如缺少 owner、contract 自相矛盾、依赖未声明），
   **立即停止所有 affected implementation line**，并：
   
   1. 记录 A2 事件：
      ```bash
      python skills/plan-test/scripts/plan_test_gate.py record-plan-defect \
        --run-dir <run-dir> \
        --affected-tasks <任务 ID 列表> \
        --defect-type <owner-missing|contract-conflict|scope-drift|...> \
        --description "..."
      ```
   
   2. 检查 A2 事件累计数：
      ```bash
      python skills/plan-test/scripts/plan_test_gate.py check-plan-stability \
        --run-dir <run-dir>
      ```
      
      - A2 事件 >= `MAX_A2_EVENTS`（默认 3）→ exit 1，输出 `PLAN_UNSTABLE`；
      - 诊断："phase 2 未真正收敛，禁止继续叠加 WIP，必须回退 phase 2 重新迭代"。
   
   3. 用户明确批准后才能：
      - 提交或 stash 当前 WIP（不得丢失）；
      - 回到 phase 2，修订 plan，重新挑战至收敛；
      - 清空 A2 事件计数，重新进入 phase 3。
   ```

2. **phase-2 出口增加前瞻检查**（可选，提高准确性）：
   - 在 phase 2 最后一轮 challenger PASS 后，运行一次"实现可行性预审"：
     - 每个任务有明确 owner？
     - 所有依赖的 Port/contract 已在前序任务中定义？
     - 没有循环依赖？
   - 若预审发现问题 → 不算收敛，继续迭代。

**优先级**：P0 - 执行期重写 plan 是 WIP 累积的直接原因。

---

### P0-5：Dirty WIP 累积的硬上限

**问题**：累积 22,000+ 行未提交 WIP，失去了小 slice 的安全边界。

**根因**：没有工具监控 `git diff --stat` 或阻止继续叠加。

**修复方案**：

1. **在 phase-3-execute.md 的每个子任务完成后增加检查点**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py check-wip-limit \
     --repo-dir <SDK 仓库路径> \
     --max-lines <MAX_WIP_LINES，默认 5000> \
     --max-files <MAX_WIP_FILES，默认 20>
   ```
   
   - 运行 `git diff --stat`，统计未提交的 tracked modified 行数与文件数；
   - 超限 → exit 1，输出 `WIP_ACCUMULATION_UNSAFE`；
   - 诊断："未提交改动超过安全阈值，必须先 checkpoint：提交当前完成的独立功能，
     或拆分当前任务为更小的 slice"。

2. **phase-3 推进规则修订**：
   - 原："完成度审计通过 → 继续下一个任务"；
   - 改为："完成度审计通过 **且** WIP 未超限 → 继续；超限 → BLOCKED，要求用户决定：
     - 提交当前已完成部分（独立功能、有测试、可 revert）；
     - 或拆分当前 slice 为更小的 unit。"

3. **phase-4 昂贵层前置增加提交态检查**：
   - 在冻结 testcase 和 `gate init` 之前，强制运行：
     ```bash
     git status --porcelain -- . ':(exclude)verification/'
     ```
   - 输出非空 → 诊断码 `COMMIT_STATE_GATE_BLOCKED`："禁止在脏工作树上执行昂贵测试，
     必须先提交（或明确 stash）当前实现"。

**优先级**：P0 - 22,000 行 WIP 是本次最危险的单一状态。

---

## P1：显著提升安全性的改进

### P1-1：runs/evidence/timing 零增长的暂停信号

**问题**：机器账本 `runs=0`、`evidence=0`，说明长时间执行但账本不增长。

**修复方案**：

1. **在 phase-4/phase-5 的循环中增加进度监控**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py check-ledger-progress \
     --run-dir <run-dir> \
     --min-interval-minutes <MIN_PROGRESS_INTERVAL，默认 90>
   ```
   
   - 读取账本最后一次 `runs[]`、`evidence[]`、`timing[]` 写入的时间戳；
   - 若距离当前时间 > `MIN_PROGRESS_INTERVAL` 且三者都未增长 
     → exit 1，输出 `LEDGER_STALLED`；
   - 诊断："机器账本长时间无进展，可能正在绕过 gate 或陷入空转，建议暂停检查"。

2. **phase-4/5 每 60-90 分钟自动调用一次**（在主循环中嵌入）。

**优先级**：P1 - 早期发现绕过行为的信号。

---

### P1-2：显著 plan 增长的用户确认

**问题**：`implementation-tasks.md` 从初始版本增长到 2032 行，用户可能不知情。

**修复方案**：

1. **在 phase-2 每轮迭代后比较 plan 体量**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py check-plan-growth \
     --baseline <baseline-plan.md> \
     --current <plan.md> \
     --max-growth-ratio <MAX_PLAN_GROWTH，默认 1.5>
   ```
   
   - 若当前 plan 行数 > baseline × `MAX_PLAN_GROWTH` 
     → 输出 `PLAN_SCOPE_EXPANSION`（advisory，不拦截）；
   - 主动向用户报告："plan 体量从 X 行增长到 Y 行（+Z%），范围可能扩张，
     建议确认是否需要拆分 program 或调整 scope"。

2. **用户可选择**：
   - 确认扩张合理 → 更新 baseline，继续；
   - 拆分 program → 当前 plan 冻结为 Slice 1，新增部分移到 Slice 2；
   - 缩减范围 → 回到 phase-A 或 phase-1 重新定义。

**优先级**：P1 - 防止"温水煮青蛙"式的范围膨胀。

---

### P1-3：每 60-90 分钟的主动报告

**问题**：长时间执行（本次约 16 小时）期间用户无感知，直到 WIP 已无法安全回退。

**修复方案**：

1. **在 phase-3/4/5 的主循环中设置定时报告**（每 60-90 分钟）：
   - 当前所在阶段、任务进度（X/Y 完成）；
   - 最近一次成功的里程碑（如"T3.1 已提交并通过测试"）；
   - 当前 WIP 状态（X 行未提交、Y 个文件）；
   - 机器账本状态（runs/evidence/timing 数量）；
   - 挑战循环状态（当前第 N 轮、距离上限还有 M 轮）。

2. **触发报告的条件**：
   - 墙钟时间每过 60-90 分钟；
   - 或完成一个独立里程碑（如一个任务通过测试）；
   - 或发生 A2 plan defect；
   - 或任何 advisory 诊断码出现。

3. **报告格式**（简洁，不打断工作流）：
   ```
   [PROGRESS CHECKPOINT]
   - Elapsed: 2h 15m
   - Phase: 3 (Execute)
   - Completed: 5/12 tasks
   - Last milestone: T3.1 committed (abc1234)
   - WIP: +1247 lines, 8 files
   - Ledger: 12 runs, 5 evidence, 3 timing events
   - Challenge loop: N/A (not in iteration phase)
   ```

**优先级**：P1 - 提高透明度，让用户有机会在中途介入。

---

## P2：提升可观测性的改进

### P2-1：循环 dedupe key 与历史可视化

**问题**：无法追溯挑战循环的历史、去重或收敛趋势。

**修复方案**：

1. **每轮挑战记录时计算 dedupe key**：
   - `dedupe_key = sha256(target_file_content + challenge_prompt_template)`；
   - 若 dedupe key 与历史某轮相同 → 警告 `LOOP_DUPLICATE`。

2. **提供可视化命令**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py show-loop-history \
     --run-dir <run-dir> \
     --loop-type plan-iteration
   ```
   
   输出：
   ```
   Round | Verdict | Critical | Major | Plan Hash (first 8) | Dedupe Key (first 8)
   ------|---------|----------|-------|----------------------|---------------------
   1     | FAIL    | 3        | 5     | a1b2c3d4             | e5f6g7h8
   2     | FAIL    | 2        | 3     | b2c3d4e5             | f6g7h8i9
   3     | PASS    | 0        | 1     | c3d4e5f6             | g7h8i9j0
   ```

**优先级**：P2 - 帮助诊断，但不直接阻止失控。

---

### P2-2：Phase 转移的审计日志

**问题**：无法追溯"何时从 phase 2 进入 phase 3"、"phase 2 是否真正收敛"。

**修复方案**：

1. **每次 phase 转移时记录事件**：
   ```bash
   python skills/plan-test/scripts/plan_test_gate.py record-phase-transition \
     --run-dir <run-dir> \
     --from-phase <phase-2> \
     --to-phase <phase-3> \
     --convergence-evidence <最后一轮 challenge PASS 的输出 hash> \
     --plan-hash <冻结的 plan.md SHA-256>
   ```

2. **phase-final DoD 中增加审计项**：
   - 检查 phase-2 → phase-3 转移时是否有 convergence-evidence；
   - 检查 phase-3 期间是否发生过 A2 plan defect；
   - 若有 A2 且未回退 phase-2 → 警告 `PHASE_TRANSITION_PREMATURE`。

**优先级**：P2 - 事后审计，防止下次重复。

---

## 实施优先级与时间线

### 立即实施（本周内）

1. **P0-1**: Release unit 硬门（1 天）
2. **P0-2**: Gate init 与 release_unit 声明（1 天）
3. **P0-3**: 挑战循环硬轮次上限（2 天）

### 短期实施（两周内）

4. **P0-4**: A2 plan defect 强制暂停（1 天）
5. **P0-5**: Dirty WIP 累积硬上限（1 天）
6. **P1-3**: 定时主动报告（0.5 天）

### 中期实施（一个月内）

7. **P1-1**: Ledger 零增长暂停信号（1 天）
8. **P1-2**: Plan 增长用户确认（1 天）
9. **P2-1**: 循环去重与可视化（1 天）
10. **P2-2**: Phase 转移审计日志（0.5 天）

---

## 验证计划

### 回归测试

1. **重现本次失败场景**（在沙盒中）：
   - 构造一个 20 MUST AC、3000 行 plan 的 mock program；
   - 尝试进入 phase 3 → 应被 P0-1 拦截；
   - 绕过 gate init → 应被 P0-2 拦截；
   - 挑战 16 轮 → 应被 P0-3 拦截。

2. **正常流程仍可通过**：
   - 8 MUST AC、1500 行 plan → 正常进入 phase 3；
   - 按时记录 runs/evidence → 不触发 P1-1；
   - 3 轮挑战收敛 → 正常进入 phase 3。

### 文档更新

1. 修订 `gate/PROTOCOL.md` §4，新增诊断码：
   - `RELEASE_UNIT_TOO_LARGE`
   - `RELEASE_UNIT_UNDECLARED`
   - `LOOP_LIMIT_EXCEEDED`
   - `LOOP_REGRESSION`
   - `LOOP_NO_PROGRESS`
   - `LOOP_RESET_EVASION`
   - `PLAN_UNSTABLE`
   - `WIP_ACCUMULATION_UNSAFE`
   - `LEDGER_STALLED`
   - `PLAN_SCOPE_EXPANSION`（advisory）

2. 修订 `SKILL.md`、`phase-2-iterate-plan.md`、`phase-3-execute.md`、`phase-4-stage-gate.md`，
   把"应该"改为"必须"，并标注对应的工具命令。

3. 更新 `CLAUDE.md`，增加"常见失败模式"章节。

---

## 总结

本次优化的核心思路是：**把纪律变成工具约束**。

- **Before**: "plan 太大时应该拆分"（文档建议）  
- **After**: "plan 超过 16 AC 时工具拒绝继续"（硬门禁）

- **Before**: "挑战不要超过 15 轮"（MAX_ROUNDS 配置）  
- **After**: "第 15 轮工具强制 BLOCKED，禁止重命名绕过"（循环账本 + dedupe）

- **Before**: "phase 2 收敛后才进 phase 3"（流程规定）  
- **After**: "phase 3 中第 3 次 A2 → 工具拒绝继续，要求回退 phase 2"（A2 计数器）

这些改进不是为了限制灵活性，而是为了**在代理或用户意识到问题之前，由工具及早发出警报**。
