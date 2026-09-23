# Phase 3 — 执行

执行单位是 `references/delivery-slices.md` 的当前交付片，对片承诺与受影响保留能力负责，不能用片 PASS 代替整体完成。FULL/`MACHINE_GATE` 另读 `full/phase-3-execute.md`。

## 开场
1. 开工：核交付表/前序产物/整体风险/该片细化挑战闭环；对照 config `RELEASE_UNIT_LIMITS`。超限 → BLOCKED，升级给用户附拆分建议；禁止删 AC、合并任务或降级 MUST 绕过。
2. 执行模式（`EXECUTION_MODE = main-agent`，RULES R15）：仓库代码一律主 Agent 亲手写，逐任务实现验证到完整接线的片终点；不派执行子代理、不分兵实现。任务再多再独立也是主 Agent 按最短价值路径串行；并行只用于评测子代理和主体跑通后的测试（R16）。工作提交≠片验收完成。

## A. 执行
1. 最短价值路径：先打通价值里程碑（plan 矛盾分析节的 Task N），此前只做其直接依赖；PASS 前不做昂贵加固，也不做任何高成本测试（RULES R16：此前只跑便宜层 + 单次价值 smoke）；FAIL → 立即回炉（A2）或 BLOCKED（RULES R4）。
2. 里程碑 PASS 后：
   - demo：把跑起来的实物给用户看一眼（URL/截图/命令），配一句用户语言的进度汇报；有可操作入口即交接，发出前按 R10 `MODE: full` 评估（H2 证据对准本片能力，写明未做）。异步不等确认，待拍板事项攒成一批、附默认建议一次问完（RULES R11）。
   - 矛盾转化再分析：重答 phase-A 三问，重排剩余任务，一段话进 plan 文件夹。
3. oracle 先于实现（主 Agent 写实现前先写验证栏/testcase 草稿）；冻结 testcase 测试失败只有两条路：改实现或上报疑似行为变更（RULES R3）。
4. 主 Agent 在既有边界内自决技术方案（RULES R11）；评测子代理发现 plan 缺陷只上报，无权自行绕过或改代码，回炉由主 Agent 执行。
5. 不静默减少已批准行为（RULES R13）；删无必要任务 → 复用已有实现/标准库 → 最小自定义实现；主 Agent 实现前读 `policies/acceptance-preserving-ponytail.md`。
6. 片提交：片终点完整/可测/可追溯（片内可多 commit）；接入用户入口的改动（路由/index 挂载/入参透传/运行时白名单）与服务层实现同 commit；合并 worktree 后 `git status --porcelain` 为空再继续（RULES R6）。
7. hook：同任务同文件改动一次编辑；报错当场修；拦截视为用户意图，不许绕过。

## A2. 计划失效即回炉
补丁能让任务完成、不能让 AC 真达成 → 掩盖 plan 层缺陷，禁止打。判定：做完 AC 不过/关键假设实环境崩/漏决定成败问题/靠 hack/特例/绕行才做完。
- 停受影响执行线（独立任务可继续）；记 `a2-events.md`（任务/缺陷类型/描述）；累计 ≥ 3 → plan 不稳定，禁叠加 WIP，回退 phase-2。
- 范围内回炉主 Agent 自主：保存自己的 WIP（不丢/不覆盖用户工作）→ phase-2 重迭代该部分 → 回写恢复。
- 需改目标/行为、缩 AC、突破边界或超 `{MAX_ROUNDS}` → 附定向调研与决策简报升级，不能只问"要不要继续"（RULES R9）。

## A3. diff minimality（便宜检查绿后、审计前，只跑一次）
子代理读 `prompts/minimality-reviewer.md`（`MODE: diff-review`），只附基线 diff/acceptance/Ponytail policy；子代理只出 findings，主 Agent 只应用不改 AC/行为、不降 assurance 的简化，再跑编译/类型/最小单测；`ALREADY_MINIMAL` 正常，不循环、不凑 finding。

## A4. 代码 review（`CODE_REVIEW`）
适用 delivery 含非平凡代码（OPS/纯文档不适用，理由一句留痕）。A3 后、便宜检查绿、B 前，review 基线累计 `git diff`：优先 harness 自带能力（此时 B 照旧单独派）；否则与 B 合并派发：一个 `{AUDITOR_ENGINE}` 子代理先按 `CODE_REVIEW` 审正确性、再按 `prompts/completion-auditor.md` `MODE: code-audit` 审 AC→任务→代码，两段各出独立 verdict 与 findings（附 diff/相关 AC/行为契约）；复审只跑 audit 段，review 的 P0/P1 修复后由主 Agent 按 R8 分层复验。深度与 findings 处理 RULES R7，修复由主 Agent 亲手做（R15）。用户可见 P2 交用户验收前按 交接单 H2.4 清零；补丁关 finding 但 AC 仍不达成 → A2。修复后分层复验（RULES R8）；结论一行进 journal；复验红再修（`{MAX_ROUNDS}` 兜底）。

## B. 完成度审计（`AUDIT_RETRY = until-100`）
`{AUDITOR_ENGINE}` 用 `prompts/completion-auditor.md`，`MODE: code-audit`（审 AC→任务→代码 + plan 层缺陷），复审只核上轮缺口与新改动；先审决定性 AC 真达成，否则直接 FAIL；锚点是 AC 达成非任务打勾，任务全 ✅ 而必须 AC 不达成 → FAIL 标 plan 层缺陷走 A2；按可追溯矩阵核对 AC↔任务↔代码。FAIL → 补缺口再审；缺结论行按 FAIL 处理；超 `{MAX_ROUNDS}` → BLOCKED 升级。

## C. 回归门
构建/测试/lint/类型不低于 `baseline.md`，新引入的红必修。

## 出口
里程碑 PASS（含 demo/再分析）+ A4 闭环（适用时）+ 审计闭环 + 无新增回归 → 进 phase-4 验收该片。该片验收与提交身份核对后，异步展示并自主细化下一片；整体收尾等全部 MUST 与跨片组合验证。
