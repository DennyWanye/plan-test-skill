# Phase 2 — 迭代 plan + 锁定绿色基线

**目的**：把 plan 迭代到"100% 代码可执行"，并在动手前记录一份绿色基线，供执行后回归比对。

## A. 迭代 plan

循环（最少 `{PLAN_ITERATIONS}` 轮，受 `{MAX_ROUNDS}` 兜底）：派 `{CHALLENGER_ENGINE}` 子代理，用 `prompts/plan-challenger.md` 挑战 plan → 我据结果优化。

**收敛按边际收益判定，不设固定轮数上限**（DeskPet 2026-08-03 复盘校准：那次 7 轮挑战
第 1–6 轮**每轮**都抓到新的 P0 级问题（迁移原子性、signal 被吞、双窗口 lost update……），
第 7 轮才干净 PASS——"默认最多 3 轮"式的硬顶会把真问题挡在门外，错的不是轮数是停止条件）：

- 挑战者每轮输出结构化发现（`[P0|去重键]` 前缀 + 末尾 `NEW_CRITICAL_FINDINGS: <n>` 行，
  见 prompts/plan-challenger.md）；派发时附上**已闭环问题清单（含去重键）**，重提已闭环项不算新增。
- **续轮条件**：`NEW_CRITICAL_FINDINGS > 0`（本轮有新 P0/P1）或 VERDICT: FAIL → 修订后继续。
- **收敛条件**：VERDICT: PASS 且 `NEW_CRITICAL_FINDINGS = 0` → 定稿进入用户 review；
  连续两轮 `NEW_CRITICAL_FINDINGS = 0` 而 VERDICT 仍 FAIL（只剩措辞级分歧）→ 也收敛，
  把剩余 P2 项列给用户随 review 一并裁决。
- 超过 `{MAX_ROUNDS}` 仍有新增关键发现 → BLOCKED 升级（问题域可能大于一份 plan 能承载的范围）。

**每轮派发规矩**（见 SKILL.md"上下文包"）：

- 附上 acceptance.md 相关条款原文、plan 原文、**上一轮已闭环的问题清单（含去重键）**——声明不必重复挑战已闭环项，只挑战新增与未闭环部分。
- 以挑战者输出末行 `VERDICT` + `NEW_CRITICAL_FINDINGS` 行判定（见上）。缺结论行按 FAIL 处理，缺 `NEW_CRITICAL_FINDINGS` 行按"有新增"处理（不许自行脑补为收敛）。
- 迭代中的补充调研遵循 `methods/research-method.md`：读代码读不出来的不确定项（运行时行为、三方库真实表现），用可丢弃的 spike 跑一下闭环，结论写回 plan——这就是"实践—认识—再实践"，不许用措辞把洞圆过去。

### 收敛判据（全部满足才定稿）

1. **100% 代码可执行** —— 即：
   - 已**认真调研过当前代码层**：相关文件、函数、调用链、依赖、现有实现方式都已读过并写进 plan；
   - 已**确认代码级别的修改方式**：每个改动点明确到"改哪个文件/哪段/怎么改/改成什么样"，不是假设；
   - 若调研中发现问题/不确定项（接口不清、改动牵连别处、最佳实践存疑），**不允许带着模糊收尾**——必须**继续调研该如何解决**，把结论补回 plan，直到该问题闭环。
2. 功能可达预期，且 `FEATURE_POLICY = only-add`（只增不减）。
3. plan 含实现细节调研结论（"怎么做、为什么这样做"）。
4. **无"绕过真架构问题的补丁式收尾"**（见下方强约束）。
5. **关键技术假设已用真代码验证**：凡"决定方案成败、静态阅读无法确认"的假设（三方库/API 真实能力、LLM 输出契约、性能可达性、关键链路运行时行为），必须有**可运行 spike 真跑过的证据**（命令 + 实际输出）回写在 plan 里。"读过源码应该支持 / 理论上可行"不算闭环——这类假设留到执行期才发现不成立，返工代价最大。spike 代码即弃，不滚成实现。

> 收敛不是"迭代满 N 轮就停"，而是"代码层已吃透、所有不确定项都已闭环"。只要还有一处"到时候再看 / 可能要改别处但没查"，就**不算 100% 可执行**，继续迭代+调研。
> 超过 `{MAX_ROUNDS}` 仍无法收敛 → 标记 BLOCKED，列出无法闭环的具体不确定项，升级给用户。

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
