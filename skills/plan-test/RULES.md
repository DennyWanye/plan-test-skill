# RULES：铁律与通用规则

正文只在此；别处写"做什么+在哪步（RULES Rn）"。

## R1 唯一真相
- **acceptance 唯一真相**（`{ACCEPTANCE_FILE}`，FULL 含 contract）— 触发时点：plan/挑战/测试/宣布完成全程；要求：一切回溯用户批准的 acceptance 与原话对照表，新 AC 先进 acceptance，challenger 不得扩大范围；防的逃逸：换措辞悄悄做少。
- 调查/挑战可基于标注待决项的草案，但不先改目标、不把待定写成已批准。批准缩减后回写范围节，只写"批准后范围全绿"。

## R2 围绕主要矛盾
- 矛盾四问（格式见 phase-A）；每条 AC 标决定性/次要，挑战、排序、review、测试深度按它路由。次要 AC 下限一轮挑战、一遍测试。

## R3 oracle 先于实现与冻结
- **oracle 先于实现**（`ORACLE_FREEZE`）— 触发时点：写任一 AC 实现前、派执行子代理时；要求：先写"什么算对"（输入、独立预期、通过条件）进验证栏/testcase 草稿与执行 prompt，选中用例冻结 revision 本 run 执行；防的逃逸：照实现补预期。
- 实现后新增测试可单列；删除/反转/放宽冻结 oracle 须批准，失败后不许把预期改成当前结果。

## R4 价值 smoke 硬门
- **价值 smoke 走生产接缝**（`VALUE_SMOKE_GATE`，所有任务类型）— 触发时点：封存/全量回归/审计/真人矩阵等昂贵步骤前；要求：跑 acceptance 的最小验证动作，从用户实际入口经真实装配/存储/provider 到业务终态（输入敏感 2–5 个自然语言正向问题），FAIL→立即 BLOCKED 或 A2，不做外围凑完成度；防的逃逸：基座串内部函数只证明组件存在。
- 入口：应用 UI、CLI 命令、API 真实请求、库真实消费者。mock/基座只算组件级证据；替身不冒充真实 provider。spike 同此。

## R5 真人测试口径
- **UI 真人测试**（`MANUAL_TEST`、`MCP_DRIVER`）— 触发时点：有 UI 的对象验收、宣布完成前；要求：MCP 真点真输入，脚本不代点（细则 `checklists/handoff.md` H2），有 UI 的被测对象不省略不降级，测不了→BLOCKED，等价方案须用户批准并表注；防的逃逸：收尾时用代码审计顶替真机测试。
- `TEST_STRATEGY`：UI→手工；API/CLI/库/管道→可复跑脚本；兼有都做。决定性深测，次要每条一场景。
- 兑现表逐条列必须 AC 的地位/方式/驾驶者/证据/状态；主流程通过≠每条 AC 测了（照见开关/权限/空态/错误态）。`MANUAL_REQUIRED_PENDING_POLICY`：required 场景 PENDING/PARTIAL/NOT RUN 不得完成。缩测试范围须用户批准。

## R6 提交态硬门
- **提交态硬门**（`COMMIT_STATE_GATE`）— 触发时点：合并 worktree 后、DoD/宣布完成前；要求：`git status --porcelain` 空（FULL 排除 run-dir：`-- . ':(exclude)<run-dir>'`，仅此一处），验证针对已提交 HEAD 并记 hash，查未跟踪接线文件，多代理做干净态复验；防的逃逸：验证过的代码≠提交的代码。
- 片终点须完整接线可测；接入口改动与服务层同 commit。增量 AC 不豁免。

## R7 代码 review
- **code review**（`CODE_REVIEW`）— 触发时点：delivery 含非平凡代码，①A4 便宜检查绿后、审计前 ②push 前审将推送 diff；要求：执行者不自审（harness review 或独立子代理），审累计 diff 正确性，深度按矛盾地位（决定性高档多角度，次要标准一遍）；P0/P1 必修且各配可复跑决定性测试进回归套件，按 R8 复验后才前进；防的逃逸：自审漏正确性 bug。
- OPS/纯文档不适用须留理由。出口：环境不可用→BLOCKED，或用户批准跳过并留痕。P2 记遗留；结论一行（工具、finding 数、P0/P1 处理、复验范围）进 journal。

## R8 复验范围
- `REVALIDATION_SCOPE`：按内容身份，输入没变不过期，动过字节的 PASS 作废；只复验受影响面，禁止改一行重走全链；影响面说不清→扩大。历史/脏工作树 PASS 不替代本次。
- 修复后：便宜层全量+受影响决定性测试+价值 smoke；触及用户可见行为才回昂贵层（A4 时尚无昂贵层，不回补）。
- `FULL_SURFACE_SMOKE`：入口各一枪断言非 404/500；DIRECT 变更入口，LEAN/FULL critical+affected；改路由/基础设施/共享 provider/权限、release、无 impact_paths→全量。
- `INCREMENTAL_AC_MODE`：只跑受影响行，分级冒烟与 R6 不豁免。

## R9 BLOCKED 与出口
- **BLOCKED 纪律**（`BLOCKED_SEMANTICS`、`MAX_ROUNDS`=15）— 触发时点：决定性 AC/价值 smoke FAIL、required 测不了、DoD 缺证据、循环超限；要求：立即停收尾（可诊断修复），任一必须 AC 未过→总体只能 BLOCKED，局部 PASS 标作用域；防的逃逸：拿外围 PASS 稀释核心 FAIL。
- BLOCKED≠求助：能修就修，不借它结束任务或要求重复批准；真外部阻塞或达出口阈值才升级，附已试/结果/推荐出口/最小用户动作，保持未通过。
- plan challenge 3/5/8：`SCOPE_AUDIT_REQUIRED`/`USER_REVIEW_REQUIRED`/loop BLOCKED。reset 不清零历史。
- plan 缺陷禁打补丁→A2，A2≥3 次回 phase-2。

## R10 交接检查与独立评估
- **交接检查与独立评估**（`HANDOFF_CHECK`）— 触发时点：结束本轮回复前四问任一为是；要求：按 `checklists/handoff.md` 过档并派评估员，PASS 才发（文字类/DISPUTED 按该文件）；防的逃逸：做少、自测不净、决策讲不清。

## R11 用户注意力
- `USER_ATTENTION`/`EXECUTE_AUTONOMY`：授权覆盖且无重要未决取舍→自主执行，技术选择自决；只在意图缺失、可感知行为变化或缩 AC、增成本扩范围、无授权、需用户动作、用户要求确认时问；沉默不算批准。
- `DECISION_BATCHING`：攒批编号，`checklists/handoff.md` H3；不挂起，继续不依赖它的工作。
- `PROGRESS_REPORTING`：先总进度表，用户语言，格式按 `checklists/handoff.md` H3；demo 异步不等待（事先约定或用户要求先验收除外）。提问/汇报/续接细则见 `references/user-attention.md`。

## R12 终态行与自我批评
- **终态行**（`JOURNAL_VERDICT`）— 触发时点：final DoD 后、提交前；要求：journal 末行 `VERDICT: SHIPPED | BLOCKED — <TESTED SCOPE> — <日期> — <被测 HEAD sha>`，HEAD 写被验证的代码提交，与 DoD 一致；定不了 SHIPPED 写 BLOCKED+一句卡点（合法终态），无终态行=未闭环；防的逃逸：通读 journal 才知是否通过。
- 默认完成 authority=DoD 逐条附证据；无 `MACHINE_GATE` 写"无机器 receipt"，不用 receipt/SHIP 措辞。
- `SELF_CRITICISM`：retro.md 一两行：哪些门空转/被仪式拖慢/真拦住问题；供 `GATE_REGISTRY_DISCIPLINE`（见 config）退休评审。

## R13 已批准行为不缩水与最小化
- `BEHAVIOR_POLICY`=preserve-approved：不静默减少已批准外部行为，内部可删改；acceptance 批准删的可删。最小化见 ponytail policy。

## R14 禁止自造防御、语言
- `SELF_BUILT_DEFENSE`：acceptance 未要求时不自造 receipt/锁/校验器，用现成工具。
- 用用户的语言回复；子代理 prompt 与结果转述同语言。
