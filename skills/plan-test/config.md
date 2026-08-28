# plan-test 配置

本文件是 skill 的**默认配置**。运行时，若项目根存在 `.claude/plan-test.config.md`，其中出现的同名键**覆盖**这里的默认值（只需写要改的键）。

所有 `{大写变量}` 在各阶段文档里被引用，运行时替换为下面的值。

## 子代理引擎

- `EXECUTOR_ENGINE`: current
  - 执行阶段并行实现用。`current` = **跟随用户当前会话使用的大模型**（派发子代理时不指定
    model，自动继承当前模型——用户用 DeepSeek V4 Pro 执行子代理就是 DeepSeek V4 Pro，
    用 Claude 就是 Claude），不再默认绑定某个固定模型（如 GPT 系）。
  - 需要固定引擎时，在项目根 `.claude/plan-test.config.md` 里覆盖本键（如 `claude`）。
- `CHALLENGER_ENGINE`: claude
  - 挑战 plan / 挑战架构文档 / 迭代 testcase 的子代理。
- `AUDITOR_ENGINE`: opus-4.8
  - 完成度终审、测试覆盖最终确认。

## 路径

- `ARCH_DIR`: ./ARCHITECTURE
- `PLANS_DIR`: ./plans
- `TESTCASE_DIR`: ./testcase
- `ACCEPTANCE_FILE`: ./acceptance.md

## 流程路径（`FLOW_TIER`，默认 auto）

> **病根**：此前只有二元选择——要么全套 8 阶段（一轮 15–25 万 token），要么"别用本 skill"。
> 中等改动被迫走全套，代理跑到一半开始自行省略；**一旦学会"这条规则在我这个情况下可以变通"，
> 其余规则的权威一起塌掉**。分档是为了让裁剪变成明示的、有边界的选择，而不是偷偷跳步。

- `FLOW_TIER`: auto
  - `auto` = 按下表自动判路径并在开场明确依据；用户可指定 `DIRECT`/`LEAN`/`FULL`。
  - 自动判定优先选择满足条件的最低成本路径：全部 DIRECT 条件满足才 DIRECT；命中任一 FULL
    条件即 FULL；其余有用户可见交付的单切面默认 LEAN。

| 路径 | 触发条件（取最高风险） | 跑什么 | 不跑什么 |
|------|----------------------|--------|----------|
| **DIRECT** | 同时满足：可快速回滚；不涉权限/资金/身份/迁移；无新持久化状态；不改公共协议；不跨信任边界；不引新依赖 | 不启动 plan-test：一句 AC → Ponytail 最小实现 → 最小决定性测试 → 变更入口 smoke → 提交态硬门 | 不建 run-dir/plan/architecture/contract，不派子代理，不做 ledger/receipt/full-audit |
| **LEAN** | 单个明确业务切面；用户可见变化；风险可局部隔离；有自动化出口；无高风险迁移或共享基础设施 | phase-A/1/2-lite/3/4/final + 机器门；2-lite 仍按“primary 主挑战 → 必要 cluster 专项挑战 → synthesis → 必要时一次 closure → minimality”执行 | 不做 phase-0 架构 challenger、无 open P0/P1 时不进入多轮 closure、不做 testcase 多轮挑战 |
| **FULL** | 权限/身份/支付/数据完整性、schema/迁移、多阶段状态机、公共 Provider/API、跨服务、LLM 驱动状态机、不可逆副作用、共享基础设施或 `input_sensitive=true` | 全套 8 阶段 | —— |

- DIRECT 是“不启动本 skill”的决定；一句 AC 和提交态硬门是项目级 invariant。
- LEAN 的 2-lite 只压缩轮数，不改变挑战顺序；primary 之前不得先平铺专项子代理。
- LEAN/FULL 不可裁剪：acceptance 唯一真相、提交态硬门、按路径分级 smoke、
  `BEHAVIOR_POLICY: preserve-approved`、BLOCKED 升级纪律。
- DIRECT 无 run-dir、LEAN 无 full-audit 时不得使用 receipt/SHIP/全部完成措辞，只报告范围与证据。
- 路径有疑义 → 往高风险路径判。裁剪的代价是漏测，判高的代价只是慢。

## 轮次与出口

- `ASSURANCE_PROFILE`: standard
  - `standard`：信任当前开发者账户、OS/kernel 与系统绝对路径程序；防错误目标、误操作、
    非预期网络/持久化、敏感信息泄漏和产品状态污染。
  - `hardened`：额外不信任项目输入、远程目标和运行数据，但仍信任开发者账户与 gate。
  - `hostile-host`：宿主环境也可能被篡改，必须声明独立信任锚；仅可由用户显式批准启用。
  - 保障等级或可信边界变化属于 scope/cost 变化，challenger 只能提出 proposal，不能自行升级。
- `PLAN_ITERATIONS`: 1
  - 第一轮建立 breadth baseline；后续只审 open findings + diff + 有证据证明第一轮不可知的
    新事实。无 open in-scope P0/P1 即收敛，不凑轮数。
- `PLAN_CHALLENGE_SOFT_LIMIT`: 3
  - 第 3 轮仍有新增 in-scope P0/P1 → `SCOPE_AUDIT_REQUIRED`；记录控制事件后才能续轮。
- `PLAN_CHALLENGE_USER_REVIEW_ROUND`: 5
  - 第 5 轮仍有新增问题 → `USER_REVIEW_REQUIRED`，不得静默继续。
- `PLAN_CHALLENGE_HARD_LIMIT`: 8
  - 第 8 轮仍有 open in-scope P0/P1 → 当前 plan loop `BLOCKED`；architecture reset 不清零历史。
- `TESTCASE_ITERATIONS`: 2
  - testcase 迭代策略：
    - **第一轮**：检查 MUST AC 覆盖完整性 + 关键风险覆盖 + 目标绑定审查
    - **第二轮**：只审新增 diff 和未闭环的 AC/risk obligation
    - **收敛条件**：
      * 所有 MUST AC 都有 required testcase 覆盖
      * 所有 required testcase 都有明确的 AC 或 risk 绑定
      * 没有新增 required obligation
    - **继续条件**：只能新增 exploratory testcase 时，不阻断 plan 定稿
    - **最大轮次**：受 MAX_ROUNDS 兜底，但优先按收敛条件判断
    
    注意：不再固定"至少两轮必须继续加内容"，而是按边际收益收敛。
- `AUDIT_RETRY`: until-100
  - 完成度未达 100% 就循环补完（受 `MAX_ROUNDS` 兜底）。
- `MAX_ROUNDS`: 15
  - 其他执行/审计循环的全局兜底；不再充当 plan challenge 的日常预算。

## 测试

- `MANUAL_TEST`: required
  - MCP 真人点击/输入测试。对有 UI 的被测对象不可省略、不可降级。
- `MCP_DRIVER`: auto
  - auto = 按平台与被测对象自动选：Web→Claude-in-Chrome MCP，原生桌面→computer-use/macos-mcp。
- `TEST_STRATEGY`: route
  - route = 按被测对象路由（见 phase-4）：UI→手工；API/CLI/库/管道→脚本；两者皆有→都做。

## 真人测试广度门禁（只对"输入语义敏感"功能生效）

> **输入语义敏感的判定**：功能的输出质量随输入语义变化——LLM 对话/生成、搜索、调研/agent、推荐、分类等。反之，设置页、开关、单按钮、CRUD 表单、导航等**确定性 UI 不适用**，一个场景即可，不许把多问题门槛错误套给它们。

- `MANUAL_SCENARIO_MATRIX`: required-for-input-sensitive
  - 输入敏感功能必须在 acceptance 里有"测试场景矩阵"（见 phase-A）；没有 → plan-task 开工即 BLOCKED。
- `MANUAL_MIN_DISTINCT_CLASSES`: 3
  - 真人测试最少覆盖的**语义不等价输入类别**数。重试、重放、同意图改写、continuation 都不增加此计数。
- `MANUAL_REQUIRE_NEGATIVE_CLASS`: when-applicable
  - 适用时额外包含 1 个错误态/低证据/对抗场景（验证诚实降级），计入类别数之外。
- `MANUAL_REQUIRED_PENDING_POLICY`: block
  - 任何 required 场景处于 PENDING/PARTIAL/NOT RUN 时，门禁与 DoD 一律 FAIL/BLOCKED，不得用"核心 PASS"掩盖。
- `MANUAL_MIN_POSITIVE_SAMPLES`: 1
  - **正向价值样本**下限：自然用户语言、走真实生产入口、真实 provider、得到**非空有效业务结果**、内容经人工检查、达到 acceptance 声明的最低质量线。所有样本都是 partial/insufficient/空结果时，**即使系统没崩也不得完成**——"诚实降级成功"只是负向安全门 PASS，不等于产品质量 PASS。
- `VALUE_SMOKE_GATE`: required
  - 价值优先 smoke：输入敏感功能在进入打包、全量回归、完整真人矩阵等**昂贵步骤之前**，必须先跑 2–5 个自然语言正向 smoke 验证主要矛盾（核心价值真的可用）；失败 → 立即 BLOCKED 早停，不继续投入昂贵收尾。

## LLM 载荷对抗门禁（只对"LLM 生成结构化载荷驱动 UI/状态机"的功能生效）

> **LLM 载荷驱动的判定**：功能里存在"LLM 输出（结构化 payload / 工具调用 / 生成内容）直接驱动端侧状态机、卡片渲染或流程推进"。LLM 只做纯文本展示、不驱动端侧状态的，不适用。

- `LLM_PAYLOAD_ADVERSARIAL`: required-for-llm-driven
  - 功能含"LLM 输出驱动端侧状态机/卡片/流程推进"时，acceptance 必须含
    「LLM 行为变异清单」：乱序、重复、schema 违约（必填字段缺失/写错位置）、
    超长文本、拒不调用工具——每类至少一条端侧容错断言（容错/自救/降级出口）。
    缺失 → plan-task 开工 BLOCKED（同场景矩阵门禁待遇）。
- `STOCHASTIC_MIN_RUNS`: 2
  - LLM 驱动的多步流程（测验/多轮会话），真机 root run 至少 2 次独立完整跑，
    且至少 1 次在**长上下文会话**（≥10 轮历史）中进行；两次都完整收尾才计 PASS。
    单次跑过记 PASS = 对随机性故障采样不足，不达标。
- `COLD_START_SCENARIO`: required-for-stateful-init
  - 功能行为依赖"异步注册的服务/远程配置/登录态"时，场景矩阵必须含一条
    冷路径场景：**全新安装（或清数据）→ 首次登录 → 直达功能页**，断言功能
    在该路径可用。**暖重启（杀进程重进）不算冷路径。**

## 交付一致性门禁（防"半截提交"：验证过的代码 ≠ 提交了的代码）

> **病根**：多代理 + git worktree 工作法下，验证可以在一棵脏工作树上全绿，而关键文件（尤其"把服务层接到端点上"的路由接线层）未提交，随后被 worktree 清理 / `git clean` / 硬 reset 抹掉——git 里留下**能编译、能过类型检查、单测也绿**的"半截健康"状态，但用户路径根本没接通。以下门专堵这条路。

- `COMMIT_STATE_GATE`: required
  - 提交态硬门：宣布完成前 `git status --porcelain -- . ':(exclude)<run-dir>'` 必须为空（**排除 gate run-dir**，否则刚写入的 receipt/report 会让本门自己失败），且验证针对的是 HEAD 的代码；
    **对未提交工作树的任何 PASS 一律不作数**。多代理/worktree 参与实现时，
    额外要求"干净态复验"（见 phase-final-dod）。
- `FULL_SURFACE_SMOKE`: required
  - 冒烟按当前路径声明范围，每个范围内用户入口各打最小一枪，断言非 404/500/未接通；
    脚本存盘可复跑。会话续接时重跑同一声明范围。
    
    **分级触发策略**（防止对所有改动都全量打历史端点）：
    - **change-entry-smoke**：DIRECT 只跑本次变更入口
    - **critical-surface-smoke**：LEAN/FULL 必做少量核心历史入口
    - **affected-surface-smoke**（条件触发）：根据入口依赖和 impact_paths 运行受影响的端点
    - **full-surface-smoke**：全量历史端点，仅在以下高风险条件强制：
      * 路由层、公共基础设施、启动装配有改动
      * 共享 provider、中间件、权限系统有改动
      * 正式 release 前的完整验证
      * 无 impact_paths 映射或映射覆盖不完整时（fail-closed）
    
    LEAN 默认 critical + affected；FULL 默认 critical + affected，命中高风险条件再升级 full-surface。
- `WIRING_CHECK`: required
  - 服务层-路由接线断言：services / prompts 等处新 `export` 的函数/枚举/新增入参，
    routes / 入口层必须有真实引用；运行时白名单数组必须与对应类型全集同步
    （`satisfies` + exhaustiveness 断言测试，见 phase-4 ②）。
- `INCREMENTAL_AC_MODE`: on
  - 增量 AC 模式：后续会话增量加功能时，新 AC 必须先进 `{ACCEPTANCE_FILE}` 唯一真相；
    允许只跑受影响 AC 的兑现表与 DoD 对应行，但**按路径分级冒烟 + 提交态硬门不得豁免**。
    "小功能就不走流程"不被允许。

## 机器门禁（唯一状态 authority，见 `gate/PROTOCOL.md`）

> **病根**：此前所有严格规则只是 Markdown——代理仍可以在详细 testcase 写着
> `PARTIAL/BLOCKED/NOT RUN` 时手工写出 `100% COMPLETE / SHIP`。Markdown 从此只是
> 给人读的视图；状态 authority 是结构化账本 + deterministic validator。

- `GATE_SCRIPT`: `${CLAUDE_PLUGIN_ROOT}/skills/plan-test/scripts/plan_test_gate.py`
  - 路径解析：装为插件时 `${CLAUDE_PLUGIN_ROOT}` 由 harness 注入；在源码仓库内开发或
    手工复制安装（未装插件）时，依次退回仓库相对路径 `skills/plan-test/scripts/plan_test_gate.py`
    与 `~/.claude/skills/plan-test/scripts/plan_test_gate.py`。
  - canonical gate command。plan-task/plan-test 的**最终交付判定只接受**
    `python {GATE_SCRIPT} finalize --run-dir <run-dir>` 的 exit code 与结构化 stdout，
    不接受代理手写结论。没有有效 `gate-receipt.json` 的手写 SHIP/100% COMPLETE 一律视为
    `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。
- `RUN_DIR`: `<plan-folder>/verification/<run-id>/`
  - 每次验证的固定 run 目录；唯一状态账本 `plan-test-run.json` 只存原始 fact，
    所有 status/state 由 validator 重算。目录布局与稳定诊断码见 `gate/PROTOCOL.md`。
- `BLOCKED_SEMANTICS`（易踩的语义陷阱，见 `gate/PROTOCOL.md` §5.2b）
  - 流程层"标记 BLOCKED 升级给用户" = 写给人看的结论；`record-run --result blocked` = 机器事实。
    机器 `blocked` 会让该场景保持 BLOCKED **直到真的补上一条 root pass**，required 场景因此
    过不了门。**临时受阻（需要用户本人输密码/系统授权等 AI 代不了的步骤）→ 保持 NOT_RUN**，
    把阻塞原因写进证据、在报告里 BLOCKED 升级；不要拿机器 blocked 当逃生口。
- `RUN_EXIT_PATHS`（历史 run 的两条正当出口，其余一律不算）
  - `retire --superseded-by <继任轮>`：继任轮须已 SHIPPABLE、同 acceptance、覆盖前轮全部
    required 场景——**举证责任转移，不是赦免**。
  - `acknowledge --reason ... --approval-hash <用户批准原话 sha256>`：继任轮还没跑完、用户
    决定放弃这一轮时用。**放弃 ≠ 通过**：该 run 从此报 `RUN_ABANDONED`，永远拿不到 receipt，
    也不能当别人的继任轮；不可撤销，须用户显式拍板。
- `ORACLE_FREEZE`: required
  - 实现前 init 冻结 black-box testcase 逐文件 hash（`testcase_lock`）。任何 byte 变化
    默认 `FROZEN_ORACLE_CHANGED`；唯一例外是绑定 exact old/new + 用户消息 hash +
    scope/expiry 的 `behavior_changes` 批准 artifact。失败后不许把 expected result
    改成当前实现结果。
- `RELEASE_UNIT_LIMITS`: MUST AC ≤ 8 / Task ≤ 10 / plan ≤ 2000 行 / 高风险子系统 ≤ 3 /
  同时改 UI、Session、Harness、Provider、权限 ≤ 3 类
  - 超限 → validator 返回 `RELEASE_UNIT_TOO_LARGE`，要求拆 program plan + 垂直 slice，
    每个 slice 独立验收。阈值可在 manifest `thresholds` 覆盖（须用户知情），不许为卡数字压缩文字。
- `APPLICABILITY_DECLARATION`: required
  - **本节以下各条件门（输入语义敏感 / LLM 载荷驱动 / 冷启动）的适用性判定必须写进 manifest 的
    `applicability`，不再是口头自决**：三维各一条 `{value, rationale(≥10 字), decided_by}`，
    由 init 冻结、进 receipt digest、进 report.md。缺任一维 → `APPLICABILITY_UNDECLARED`。
  - 判「不适用」合法且不拦截——但理由留痕、可追责；判「适用」则场景矩阵必须真的兑现
    （input_class 去重 ≥ `MANUAL_MIN_DISTINCT_CLASSES` 且含 positive-value 场景 /
    至少一条 `min_root_runs ≥ 2` / 含 `cold_start` 场景），否则 `APPLICABILITY_GATE_UNSATISFIED`。
  - **病根**：判一句"这是确定性 UI"，场景矩阵、正向价值门、随机采样、冷启动四道门就合法消失，
    而 validator 完全不知道发生过这件事——这是本 skill 此前最大的一个洞。
- `LEDGER_INTEGRITY`: on
  - 账本每次 CLI 写入追加 integrity 链条目；手工改一行 `runs[].result` → `LEDGER_TAMPERED`。
    防的是顺手改，不是有决心的伪造（见 `gate/PROTOCOL.md` §5.13）。
- `AUDITOR_INDEPENDENCE`: expose
  - `audit --engine` 必填；与 `executor_engine` 相同或未标注 → advisory
    `AUDITOR_INDEPENDENCE_UNVERIFIED`（曝光不拦截）。审计产物里的 verdict 与命令行不一致 →
    直接拒绝（`AUDITOR_VERDICT_MISMATCH`）——以产物为准，不许命令行改判。
  - 引擎声明入账（1.4.0 起）：manifest 可声明 `executor_engine` / `auditor_engine` /
    `challenger_engine`（init 冻结）。executor 未声明 → advisory `EXECUTOR_ENGINE_UNDECLARED`；
    实际审计引擎偏离声明 → advisory `AUDITOR_ENGINE_MISMATCH`。曝光不拦截，但
    "配置写在 Markdown 里、实际用了别的引擎"从此在 report/receipt 里可见。
- `SELF_REPORT_EXPOSURE`: on（schema 1.4.0）
  - 脚本测试优先 `record-run --exec -- <cmd>`：gate 亲自执行，result 由 exit code 决定，
    输出日志自动记为 primary 证据。自报模式下：同一命令同一时间戳扇出 ≥2 个场景的
    root pass → advisory `RUN_ATTESTATION_FANOUT`；required 全 PASS 但零 primary 证据 →
    advisory `EVIDENCE_FREE_FINALIZE`；auditor 产物含 deferred findings →
    advisory `OPEN_DEFERRALS`（"留待后续"不许悬空）。均曝光不拦截、fixture 免检。
- `EVIDENCE_CLASSES`: primary / derived
  - 截图、原始日志、命令回执、DB 记录是 primary；auditor 报告与交付汇总是 derived。
    derived 只辅助审计，不能单独满足 AC/testcase；证据依赖图存在环 →
    `EVIDENCE_DEPENDENCY_CYCLE`（两份互引汇总不构成独立证据）。
- `MANIFEST_COMPILATION`: structured
  - 新 run 从 `verification-spec.json` 编译 manifest；编译器核对 assurance AC、obligation、reuse
    decision、testcase inventory 和 scenario 双向映射，并冻结 `case_sets.full`。不解析 Markdown
    猜映射。命令与格式见 `references/evidence-audit-lifecycle.md`。
- `EVIDENCE_CONTRACT`: per-scenario
  - compiled workflow 的每个 required scenario 按证明需要声明统一 `evidence_contract`。手工证据通过
    `attach-evidence/import-evidence --metadata <json>` 提供 provenance；`record-run --exec`
    自动生成 gate-exec metadata。旧场景无 contract 时保持旧语义。
- `AUDIT_FINDINGS`: structured-json
  - JSON auditor output 的 findings 由 `audit` 原子导入；open/deferred P0/P1 为硬门。整改用
    `list-audit-findings` / `resolve-audit-finding`，闭环后必须重审。
- `ACTIVE_RUN_BINDING`: compiled-default
  - `compile-manifest` 对真实交付默认设置 `active_run_required=true`；旧 raw manifest 需显式开启。
    init 不自动抢占，适合并行 slice。每次 re-attest 后重新 activate。
- `ARTIFACT_DEDUPE`: logical-sha256
  - 不移动 evidence 文件；receipt 按现有 SHA-256 区分 record、distinct artifact、distinct root
    run，并列出共享 artifact hash。
- `TIMING_HARD_GATE`: on（schema 1.3.0）
  - 真实 run 活动跨度 > 30 分钟而 timing 覆盖 < 20% → `TIMING_MISSING`；记账覆盖区间
    合并后仍有 > 120 分钟空洞 → `TIMING_GAP`。两者均 error；漏记时段用申报模式
    `record-timing --declared-start/--declared-end` 补覆盖。阶段进出必须
    `phase-start`/`phase-end` 配对（`PHASE_UNPAIRED`）。
- `EVIDENCE_REALTIME`: on（schema 1.3.0）
  - `attach-evidence` 记录证据文件 mtime，早于开账 → `EVIDENCE_PREDATES_LEDGER`
    （防"先测三小时、账本两分半补写完"，DeskPet 实锤）；历史证据必须走
    `import-evidence --from-run`（chain of custody 入账并在 report 显形）。
- `IMPACT_SCOPED_RETEST`: on（schema 1.3.0）
  - manifest 场景可声明 `impact_paths` glob；behavioral re-attest 只 stale 命中的场景。
    **fail-closed**：无映射/清单截断/变更未被覆盖 → 全量复测；未声明映射的场景永远算受影响。
- `PARALLEL_TRACKS`: on
  - 用户批准 plan 后，实现轨（phase-3 A）与验证准备轨（phase-3 D：testcase/fixture/
    冒烟脚本/gate manifest 草案）**并行**；只有昂贵真人测试等代码冻结。验证准备轨
    禁止读实现代码（black-box 纪律）。见 SKILL.md"推进规则"依赖图与
    `checklists/parallel-verification-track.md`。
- `AI_DRIVING_APPROVAL`: required-for-input-sensitive（schema 1.3.0）
  - 输入语义敏感 + required UI 场景全 AI 驾驶时，须至少 1 次 `--driver human` root run，
    或 `record-approval --kind all-ai-driving --message-hash <用户批准消息 sha256>`；
    否则 `DRIVER_APPROVAL_MISSING`。`audit --engine` 必须是引擎身份（拒绝方法名）。
- `GATE_REGISTRY_DISCIPLINE`: required（2026-08-26；第四问 2026-08-29）
  - 规则集只进不出是本套流程的病。**新增任何门（诊断码/检查项）必须在提交说明或
    `gate/PROTOCOL.md` 里声明四样：它防的诊断码是什么、防的是哪条实测逃逸、
    复审日期是哪天、以及——**代理在这道门拒绝它的那个状态下，合法出口是什么**。
    答不出第四问的门不许合入。（依据：本仓每一次实测事故都是同一形状——
    门堵死合法出口 → 代理换 run-dir → 前面测试全废，作废率实测 56%。）
  - 退休的数据来源有两个：`python {GATE_SCRIPT} stats --root <repo> [--window N]`
    统计各账本当前状态的触发情况；refusal log（`stats` 末尾的按码计数）补上
    "历史上拦过谁"这一半。连续 N 个 run 零触发的门列为退休候选。候选只是候选：
    退门是设计决定，须对照该门当初防的逃逸再拍板。

## 行为开关

- `EXECUTE_AUTONOMY`: high
  - high = 执行阶段遇分歧按最佳实践自决、不打断用户（BLOCKED 例外）。
- `BEHAVIOR_POLICY`: preserve-approved
  - 不静默减少用户已批准的外部行为；内部实现可删除、替换或重构；acceptance 明确批准删除的
    旧行为可以删除。最小化规则见 `policies/acceptance-preserving-ponytail.md`。
