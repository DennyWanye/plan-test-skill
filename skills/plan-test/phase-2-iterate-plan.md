# Phase 2 — 迭代 plan + 锁定绿色基线

**目的**：把 plan 迭代到"100% 代码可执行"，并在动手前记录一份绿色基线，供执行后回归比对。

## A. 迭代 plan

开始前必须已有用户确认的 `acceptance.md` 与同目录 `assurance-contract.json`。启动循环时冻结
contract、scope hash、threat-model hash 和 plan baseline：

```bash
loop_id=$(python3 skills/plan-test/scripts/plan_test_gate.py start-challenge-loop \
  --run-dir <run-dir> \
  --loop-type plan-iteration \
  --orchestration clustered \
  --target-file <plan.md> \
  --assurance-contract <assurance-contract.json> \
  --baseline-hash $(sha256sum <plan.md> | cut -d' ' -f1))
```

每轮挑战前调用：

```bash
python3 skills/plan-test/scripts/plan_test_gate.py check-loop-limit \
  --run-dir <run-dir> \
  --loop-id $loop_id
```

- exit 0：允许进入下一轮；
- exit 1：按输出状态完成 specialist、synthesis、closure 或控制动作；不得跳过状态直接推进。

### 四阶段挑战编排

开始本节前完整读取 `references/challenge-orchestration.md`。派发时把该 reference、对应 role prompt
和最小上下文包一起交给子代理，不把规则复制进多份临时 prompt。

#### Stage 1：Primary breadth challenge

派一个 `{CHALLENGER_ENGINE}`，使用 `prompts/plan-primary-challenger.md`。它必须在一轮内完成固定
八维 coverage、报告当前可发现的全部范围内 P0/P1、指出主要矛盾，并按结构根因输出 clusters。
主 agent 将其唯一 JSON 输出中的 `round` 与 `clusters` 原样拆成两个文件，先后入账：

```bash
python3 skills/plan-test/scripts/plan_test_gate.py record-challenge-round \
  --run-dir <run-dir> \
  --loop-id $loop_id \
  --round 1 \
  --plan-hash $(sha256sum <plan.md> | cut -d' ' -f1) \
  --findings primary-round.json

python3 skills/plan-test/scripts/plan_test_gate.py record-challenge-clusters \
  --run-dir <run-dir> \
  --loop-id $loop_id \
  --input primary-clusters.json
```

Gate 校验 coverage、finding ID、AC/assurance binding、parent finding、plan/contract hash，并拒绝
漏聚类的范围内 P0/P1。Primary 不得把预设修法写成 cluster 问题来要求专项代理背书。

#### Stage 2：Specialist fan-out

为每个 `specialist_required=true` 的 cluster 分别派一个 `{CHALLENGER_ENGINE}`，使用
`prompts/plan-specialist-challenger.md`。每个代理只获得该 cluster、parent findings、相关 contract 原文
和 `required_evidence`；最多同时运行 4 个，超出时分批。每项完成后立即入账：

```bash
python3 skills/plan-test/scripts/plan_test_gate.py record-specialist-challenge \
  --run-dir <run-dir> \
  --loop-id $loop_id \
  --cluster-id <cluster-id> \
  --status completed \
  --output specialist-<cluster-id>.json
```

已被 primary 标成 `specialist_required=false` 的 cluster 不派子代理。不得事后自行降级 required cluster；
确需跳过时必须取得用户明确批准并记录原始消息 hash：

```bash
python3 skills/plan-test/scripts/plan_test_gate.py record-specialist-challenge \
  --run-dir <run-dir> --loop-id $loop_id \
  --cluster-id <cluster-id> --status waived \
  --waiver-reason "<reason>" --approval-hash <64-char-message-sha256>
```

#### Stage 3：Synthesis

主 agent 按 `prompts/plan-synthesis-reviewer.md` 合并 primary 与全部 specialist 结果；这一步不是再派一个
reviewer 投票。按 stable ID/结构根因去重，裁决冲突，并把结论分类为 plan 修改、补证据、required
spike 或 scope-change proposal。生成 synthesis JSON 后入账：

```bash
python3 skills/plan-test/scripts/plan_test_gate.py record-challenge-synthesis \
  --run-dir <run-dir> \
  --loop-id $loop_id \
  --input challenge-synthesis.json
```

Synthesis 入账前不得修改 plan 后直接进入 closure。入账后完成 plan 修订；关键技术假设先运行真代码
spike，并把命令与实际输出回写 plan。意见冲突未解决时 canonical finding 保持 open。

#### Stage 4：Closure diff review

修订后派一个 `{CHALLENGER_ENGINE}`，使用 `prompts/plan-closure-challenger.md`。它只复核 open findings、
当前 diff、专项冲突、patch-induced 风险和 primary 不可知的新事实；不得无理由重做全量 breadth。

```bash
python3 skills/plan-test/scripts/plan_test_gate.py record-challenge-round \
  --run-dir <run-dir> \
  --loop-id $loop_id \
  --round $N \
  --plan-hash $(sha256sum <plan.md> | cut -d' ' -f1) \
  --based-on-plan-hash <上一轮-plan-hash> \
  --findings closure-round-$N.json
```

通常使用 `review_mode=diff`。architecture/scope/trust-boundary/high-risk-entry 重大变化并已记录对应
control 后使用 `consolidated`；仍保留历史 finding ID 与轮次。Closure 仍有 open P0/P1 时修订 plan
并继续 closure round，不重跑无关 specialist；若暴露新的主要结构根因，按 gate 状态做 scope audit 或
architecture reset，不用局部补丁强行收敛。

### 控制状态

- `CONTINUE`：修订 plan 后进入下一轮；
- `CONVERGED`：无 open in-scope P0/P1，进入用户 review；
- `SPECIALIST_CHALLENGE_REQUIRED`：完成所有 required cluster 的专项挑战；
- `SYNTHESIS_REQUIRED`：完成并记录统一 synthesis；
- `CLOSURE_REVIEW_REQUIRED`：修订 plan 后执行统一 closure diff review；
- `SCOPE_AUDIT_REQUIRED`：第 3 轮仍有新增关键问题，先审计范围/根因；
- `ARCHITECTURE_RESET_REQUIRED`：连续两轮 patch-induced P0 或 scope audit 判定结构重置；
- `USER_REVIEW_REQUIRED`：第 5 轮仍有新增问题，向用户报告原因；
- `USER_SCOPE_APPROVAL_REQUIRED`：需要改变 profile/scope/trusted boundary；
- `BLOCKED`：第 8 轮仍有 open in-scope P0/P1。

控制动作必须入账，例如：

```bash
python3 skills/plan-test/scripts/plan_test_gate.py record-challenge-control \
  --run-dir <run-dir> --loop-id $loop_id \
  --action scope-audit --outcome <continue|architecture-reset|scope-change> \
  --evidence "<审计证据>"
```

用户批准 scope change 时使用 `--action scope-change-approved --approval-hash <消息 SHA-256>`；
如 acceptance/contract 变化，同时提供 `--acceptance <新文件>` / `--assurance-contract <新文件>`。
Gate 每轮复验两者 hash；未经批准的静默改写直接拒绝。Architecture reset 留在同一 loop，
随后做 consolidated review，不得重开 loop 规避轮次。

### 收敛判据（全部满足才定稿）

1. Primary breadth coverage 完整，且其所有范围内 P0/P1 已进入 root-cause cluster。
2. 所有 required cluster 已完成专项挑战，或有理由与用户批准 hash 的显式 waiver。
3. Synthesis 已记录，冲突已裁决，required spike 已成为显式动作。
4. **关键技术假设已用真代码验证**：凡“决定方案成败、静态阅读无法确认”的假设（三方库/API
   真实能力、LLM 输出契约、性能可达性、关键链路运行时行为），必须有**可运行 spike 真跑过的证据**
   （命令 + 实际输出）回写在 plan 里。“读过源码应该支持 / 理论上可行”不算闭环；spike 代码即弃，
   不滚成实现。
5. Closure review 已完成，且 open in-scope P0/P1 为零。
6. **相对于已批准范围的 100% 代码可执行** —— 即：
   - 已**认真调研过当前代码层**：相关文件、函数、调用链、依赖、现有实现方式都已读过并写进 plan；
   - 已**确认代码级别的修改方式**：每个改动点明确到"改哪个文件/哪段/怎么改/改成什么样"，不是假设；
   - 若调研中发现问题/不确定项（接口不清、改动牵连别处、最佳实践存疑），**不允许带着模糊收尾**——必须**继续调研该如何解决**，把结论补回 plan，直到该问题闭环。
7. 功能可达预期，且 `FEATURE_POLICY = only-add`（只增不减）。
8. plan 含实现细节调研结论（"怎么做、为什么这样做"）。
9. **无"绕过真架构问题的补丁式收尾"**（见下方强约束）。
10. acceptance/assurance contract 没有未经批准的变化。

> 收敛不是 reviewer 写 PASS，也不是迭代满 N 轮；它是 gate 从 finding ledger 推导出的
> `CONVERGED`。第 8 轮仍有范围内阻断项则当前 plan loop `BLOCKED`。

### 强约束：真架构问题优先重构，不许小修小补

迭代中挑战者暴露出问题时，先判定它是**真架构问题**还是局部实现问题：

**真架构问题的判定（须有证据，全部命中才算，防止把一切都当架构问题去过度重写）：**

- 问题的**根因在结构层**：职责错位、模块边界穿透、循环依赖、抽象缺失/错位、扩展点不存在，而非某个函数写错；
- **补丁会制造技术债**：为绕过它要加 hack、加特例分支、复制粘贴、埋下"下次还得再绕"的坑；
- **同类问题会复发**：不从结构上解决，后续同类需求会反复撞同一堵墙（对照 `methods/research-method.md` 的"主要矛盾"——它常常就是主要矛盾本身）。

**判定为真架构问题 → 铁律：**

1. **按最佳实践重构，不许小修小补**。plan 里对这一处不能写"临时绕过 / 先 hack 一下 / TODO 以后再重构"——必须写出**符合最佳实践的结构改法**（怎么调整边界/抽象/依赖方向），并附本项目适配分析（反对本本主义，见 research-method 第 3 条）。
2. **不受 `FEATURE_POLICY = only-add` 阻挡**：only-add 约束的是"功能不许缩水"，不是"结构不许改"。重构可以改动/删除既有实现，只要对外功能只增不减、且有回归测试兜底。
3. **范围闸（防过度重构 + 尊重用户知情权）**：若重构显著超出原需求范围（大面积改动、影响 plan 之外的模块、明显拉长工期），**不自决**——列出"补丁方案 vs 重构方案"的代价对比，标记 BLOCKED 升级给用户拍板（plan-bs 里则直接和用户讨论）。范围可控的重构按铁律 1 直接纳入 plan。

**判定为局部实现问题** → 正常在 plan 里改对即可，不必上纲上线到重构。

> 挑战者提示词已加入"这是真架构问题吗、plan 是不是在用补丁绕过它"的质疑项；我据其结论按上面判定。

### 行为契约冻结（P0：防"单入口"被扩张成"单 Session"式语义跳跃）

需求触及**易混实体**（Session、Run、Task、话题、窗口、Profile、Driver 等）或会改变既有行为时，定稿前必须：

1. 产出**结构化行为契约**并让用户逐行确认——不能用"用户已经说认可"代替具体行为确认：
   - 术语表与实体关系（一个入口 ≠ 一个 Session；一个 Session 可有多个 Run……）；
   - **before / after 行为表**：现有行为 vs 目标行为逐行对照；
   - 明确**保留、删除、改变**的旧行为清单。
2. 把原始用户消息 hash、行为契约、用户批准事件写进 gate 账本（init manifest 的
   `behavior_contract` / `source_request`，见 `gate/PROTOCOL.md`）。acceptance 的每个行为
   断言都要能回溯到这张表——**acceptance 事实源写错，后面 100% 只会更稳定地做错**。
3. 可选派 `prompts/acceptance-challenger.md`（qualitative reviewer）挑战语义遗漏；它只产出
   风险与建议，**不能替代**上述结构化批准与 deterministic gate。

### black-box oracle 冻结（P0：防测试被反转成验证错误行为）

- 定稿后、实现前，把外部 black-box testcase 的逐文件 hash 冻结进 gate 账本
  （init manifest 的 `testcase_files` → `testcase_lock`）。
- **frozen oracle 任何 byte 变化默认 FAIL**（`FROZEN_ORACLE_CHANGED`），不能以"看起来只是
  重写文案"自动放行。唯一例外：`behavior_changes` 批准 artifact——绑定 exact old/new、
  原始用户消息 hash、acceptance revision、scope 与 expiry。
- 实现后**新增**测试可单独记录；**删除、反转、放宽** frozen oracle 必须走上述批准。
  失败后不许把 expected result 改成当前实现结果。repo 内部 unit/integration test 的
  mutation report 只能作审计信号，不能替代冻结的 black-box oracle，也不能单独证明行为
  变更获得授权。

定稿后**和用户 review**；通过后在 `plan.md` 头部写入标记 `<!-- plan-status: finalized -->`（plan-task 开工前会校验此标记）。

## B. 锁定绿色基线（执行前必做）

在改任何代码前，记录当前"绿色"状态，供 phase-3/4 回归比对：

1. 跑现有构建（build）、现有测试套件、lint/类型检查，记录结果。
   - **大型仓库（测试文件 ≥ 200 或单套件预计 > 5 分钟）必须用 `scripts/baseline_runner.py`**，
     不许用单条全量命令裸跑（DeskPet 实测：15 分钟静默无终态、手工找 PID 精确终止）。
     仓库根维护 `baseline-shards.json` 分片清单（没有就本次建好留给下次）；runner 提供
     每片心跳/超时精确杀进程树/既有失败签名（`baseline-known-failures.json`）/新红即停/
     `--resume` 跳过已绿分片。
2. 若基线本身就是红的，**先如实告知用户**当前哪些已经是坏的，区分"本次引入的回归"与"既有问题"
   （既有红用 `--accept-current-failures` 记入签名文件，新红永远阻断）。
3. 把基线快照（命令 + 结果摘要 + runner 的 state/known-failures 文件路径）记进 plan 文件夹，
   命名 `baseline.md`。

## 出口

- plan 定稿且用户 review 通过 + 绿色基线已记录 → 进入 phase-3。
