# Phase 收尾 — Definition of Done + 文档回写

**目的**：合上闭环。全部勾选才宣布完成；并把文档回写，让下次从最新基线起步。

## DoD 清单（全绿才算完成——每条必须附证据，不许口头打勾）

> **逐条列出并在每条后附证据位置**（文件路径 / 截图 / log 行 / 命令输出）。任何一条附不上证据 → 标 BLOCKED 升级，**不得宣布完成**。"我确认过了""逻辑上没问题""同类已验证"都不算证据。
>
> **验证必须针对 git 已提交状态；对未提交工作树的任何 PASS 一律不作数。**"验证通过"和"交付物通过"是两回事——脏工作树上全绿、关键文件却没提交，回退后 git 里只剩能编译的半截状态，当时的 PASS 全部作废。

- [ ] **主要矛盾对应 AC 已单独确认真达成**（业务上可用，非任务打勾）—— 证据：auditor"主要矛盾判定"栏 + 实测记录。此条 FAIL 时其余任何 PASS 都不能救场
- [ ] **整体可用性实测通过**：按原始需求的核心使用路径整机走通 —— 证据：auditor"整体可用性"栏
- [ ] **执行期的 plan 层回炉已全部闭环**：回炉的部分重过了 phase-2 收敛判据并回写 plan，无"用补丁掩盖 plan 缺陷"的遗留 —— 证据：auditor"plan 层缺陷清单"为空
- [ ] `{ACCEPTANCE_FILE}` 全部"必须"条款都有测试证据通过 —— 证据：phase-4 ①b **兑现表**（每条 AC 一行；含 UI 的须有真机 MCP 证据）
- [ ] **工作树干净且已提交（`COMMIT_STATE_GATE`）**：本轮全部改动已提交，验证针对的就是 HEAD 的代码 —— 证据：`git status --porcelain` 空输出 + `git log -1` 的 hash。**非空即 DoD FAIL**，尤其警惕未跟踪的路由/接线文件（服务层提交了、接线层没提交的"半截提交"正是这样漏的）
- [ ] **干净态复验**（多代理/worktree 参与实现时必做）：提交后在干净态（`git stash -u` 之后，或临时 `git worktree add` 出的干净 checkout）重启服务，重跑核心价值 smoke + 全表面冒烟 —— 证据：复验命令输出。目的：证明**通过的代码 == HEAD 的代码**
- [ ] **全表面冒烟通过（`FULL_SURFACE_SMOKE`）**：每一个用户可达端点/入口各打一枪，无 404/500/未接通降级 —— 证据：phase-4 ② 冒烟脚本输出
- [ ] 无回归：构建/测试/lint/类型检查不低于 phase-2 绿色基线 —— 证据：命令输出对比
- [ ] 测试已按策略路由完成：UI 走 MCP 真人测试，逻辑走脚本，两者皆有则都做 —— 证据：兑现表**无 ❌、无未经用户批准的降级**
- [ ] 幂等性审查清单已逐条过 —— 证据：`checklists/idempotency-review.md` 逐条结论
- [ ] 可追溯矩阵无断点：AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 场景 ↔ root run ↔ 证据 ↔ 终态 —— 证据：终审 auditor VERDICT（含场景计数摘要）
- [ ] testcase 已存盘、index.md 与 README 已同步、脚本已纳入回归套件 —— 证据：文件路径

**正向价值硬门**（输入语义敏感功能，任一不满足 → DoD FAIL）：

- [ ] 至少 `{MANUAL_MIN_POSITIVE_SAMPLES}` 个 positive-value 场景达成：自然语言输入 + 真实入口 + 真实 provider + **非空有效业务结果** + 人工检查达 quality_bar —— 证据：①c 账本业务终态列 + 人工 review 记录
- [ ] 没有任何正向 AC 是靠负向安全行为（诚实降级/fail-closed/durable）作证的 —— 证据：auditor 不合格证据清单核查结论
- [ ] engine 终态与业务终态已分别核对，无"workflow completed 即算成功"的判定 —— 证据：账本双终态列
- [ ] acceptance 要求的人工报告 review 已对真实生成的报告执行；生成不出报告的正向场景已判 BLOCKED 而非"不适用" —— 证据：review 记录

**真人测试广度硬门**（输入语义敏感功能，任一不满足 → DoD FAIL；确定性 UI 不适用）：

- [ ] 场景矩阵中全部 required 场景 100% 执行，每个至少 1 次真实 UI root run —— 证据：phase-4 ①c **覆盖账本** + 截图/log
- [ ] distinct scenario 执行数 ≥ 矩阵 required 数，且 ≥ `{MANUAL_MIN_DISTINCT_CLASSES}` —— 证据：账本汇总计数行
- [ ] retry/重放/改写/continuation 未被计入 distinct 数 —— 证据：账本分列计数（auditor 已复核）
- [ ] required 行无 PENDING/PARTIAL/NOT RUN —— 证据：账本状态列全 ✅
- [ ] 状态一致：README / 详细 testcase 头 / RESULTS / 可追溯矩阵 / Gate 报告五处口径相同 —— 证据：phase-5 状态一致性审查结论
- [ ] 未执行项仅有两种合法来源：acceptance 预标 optional/out-of-scope，或用户 chat 显式批准缩减（已回写 acceptance；交付结论按**缩减后范围**表述，不得写成原范围全绿）—— 证据：acceptance 范围节 + 用户批准记录

> **末尾自检（长任务尤其做）**：宣布完成前回看 phase-4 兑现表——有没有把 required UI 测试悄悄换成代码审计？有没有"环境受阻就找了个等价替代而没升级"？有没有把同一个问题的多次重跑写成"多场景验收充分"？**验证通过的代码是不是就是已提交的 HEAD（`git status --porcelain` 为空）？** 只要有一条这样，就不是 100%，回去补或标 BLOCKED。

## 文档回写（闭环回到 phase-0）

- 代码改完后，`{ARCH_DIR}/ARCHITECTURE.md` 可能又过期：更新它，使其反映新架构。
- 更新 README / changelog（若项目维护）。
- 这样下次跑本 skill 时，phase-0 从最新基线开始，闭环真正合上。

## 升级与交付

- 任何 DoD 项无法达成 → 标记 BLOCKED，说明卡点，交给用户决策，**不谎报完成**。
- **汇总措辞硬规则**：任一必须 AC 为 FAIL/PENDING/无证据 → 总体结论只能写 BLOCKED/FAIL；局部 PASS 必须标注作用域（"安装链路 PASS"）；**禁止用多个基础设施 PASS 稀释一个核心产品 FAIL**——不许写成"核心功能完成，只剩少量待办"。
- **已知失败版本的交付警告**：总体为 BLOCKED 时用户要求"启动让我测试"，必须先明确告知——①这是**已知失败版本**；②启动目的是复现/补证据，**不是修复后的验收版本**；③已知会失败的场景清单。不许只说"已启动，可以测试"。
- 全绿 → 输出最终总结：做了什么、覆盖哪些 AC、测试证据在哪、文档更新在哪、回归套件新增了什么。
