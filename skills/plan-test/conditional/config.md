# config — 条件命中才读的细则

键名索引在 `config.md`；本文件按条件分节，命中哪节读哪节。项目 `.claude/plan-test.config.md` 同名键覆盖。

## OPS
`TASK_TYPE=ops`（交付物是让服务/环境处于目标状态：部署、安装、升级、基础设施迁移、配置变更）→ 走 OPS 路径，不按软件交付分档。
- 跑：acceptance（含一句话主要矛盾 + 最小验证动作）；1 轮 primary 挑战（只读实测取向，specialist 仅在真发现结构性风险时追加）。
- 回滚出口先行：动任何共享状态前先验证快照/回滚可用。
- 多任务共享机器时用串行部署锁。
- 价值里程碑硬门（phase-3 A 节，RULES R4）；分级冒烟。
- 完成记录 = 一页 journal：目标服务在生产入口活着 + 冒烟 PASS + 回滚出口已验证 + 用户明确要求时的人工验收。
- 不跑：oracle 冻结、提交态硬门、testcase inventory/场景矩阵、Stage A/B manifest 编译、finalize receipt（机器门对 OPS 为 opt-in，不作完成权威）。
- 铁律不变：BLOCKED 升级纪律（RULES R9）、`SELF_BUILT_DEFENSE: forbidden`（R14）、复验粒度跟随变更粒度（R8）。

## DIRECT
- DIRECT 是"不启动 plan-test"的决定（条件见 `config.md`）。
- 流程：一句 AC → Ponytail 最小实现 → 最小决定性测试 → 变更入口 smoke → 提交态硬门（RULES R6）→ 交接前按 `HANDOFF_CHECK` 四问自查（`checklists/handoff.md`）。
- 不建 run-dir/plan/contract；除交接评估外不派子代理；不做 ledger/receipt/full-audit。

## 保障等级
- `ASSURANCE_PROFILE`: standard — 信任当前开发者账户、OS/kernel 与系统绝对路径程序；防错误目标、误操作、非预期网络/持久化、敏感信息泄漏和产品状态污染。
- `hardened`：额外不信任项目输入、远程目标和运行数据，仍信任开发者账户与 gate。
- `hostile-host`：宿主环境也可能被篡改，必须声明独立信任锚；仅可由用户显式批准启用。
- 保障等级或可信边界变化属于 scope/cost 变化：challenger 只能提 proposal，不能自行升级。

## testcase 迭代
（phase-4：决定性 AC 覆盖存疑或 FULL 时派 `prompts/testcase-iterator.md`）
- `TESTCASE_ITERATIONS`: 2
- 第一轮：MUST AC 覆盖完整性 + 关键风险覆盖 + 目标绑定审查。
- 第二轮：只审新增 diff 和未闭环的 AC/risk obligation。
- 收敛：所有 MUST AC 都有 required testcase 覆盖；所有 required testcase 都有明确 AC 或 risk 绑定；没有新增 required obligation。按边际收益收敛，不固定"至少两轮必须加内容"。
- 只能新增 exploratory testcase 时不阻断 plan 定稿。最大轮次受 `MAX_ROUNDS` 兜底，优先按收敛条件判断。

## UI
- 有 UI 的被测对象：MCP 真人点击/输入（判据 RULES R5，细则 `checklists/handoff.md` H2）。
- `MCP_DRIVER`: auto — 按平台与被测对象自动选：Web → harness 内置浏览器优先，其次 Claude-in-Chrome MCP；原生桌面 → computer-use/macos-mcp（细则 `checklists/manual-test-mcp.md`）。

## 输入语义敏感
判定：功能输出质量随输入语义变化（LLM 对话/生成、搜索、调研/agent、推荐、分类等）。设置页、开关、单按钮、CRUD 表单、导航等确定性 UI 不适用，一个场景即可，不许套多问题门槛。
- `MANUAL_SCENARIO_MATRIX`: required-for-input-sensitive — acceptance 必须有"测试场景矩阵"（phase-A）；没有 → 暂停依赖任务，按 plan-task 输入校验第 4 项补齐或提交真实待决项；不把缺矩阵自动当作重复授权理由。
- `MANUAL_MIN_DISTINCT_CLASSES`: 3 — 真人测试最少覆盖的语义不等价输入类别数；重试、重放、同意图改写、continuation 都不增加计数。
- `MANUAL_REQUIRE_NEGATIVE_CLASS`: when-applicable — 适用时额外含 1 个错误态/低证据/对抗场景（验证诚实降级），计入类别数之外。
- `MANUAL_REQUIRED_PENDING_POLICY`: block — 任何 required 场景 PENDING/PARTIAL/NOT RUN → 门禁与 DoD 一律 FAIL/BLOCKED，不得用"核心 PASS"掩盖（RULES R5；宣布完成前按 `checklists/handoff.md` 完整评估）。
- `MANUAL_MIN_POSITIVE_SAMPLES`: 1 — 正向价值样本：自然用户语言、真实生产入口、真实 provider、得到非空有效业务结果、内容经人工检查、达到 acceptance 声明的最低质量线。样本全是 partial/insufficient/空结果时，即使系统没崩也不得完成——"诚实降级成功"只是负向安全门 PASS，不等于产品质量 PASS。
- 价值 smoke 为 2–5 个自然语言正向 smoke（RULES R4）。

## LLM 载荷
判定：LLM 输出（结构化 payload / 工具调用 / 生成内容）直接驱动端侧状态机、卡片渲染或流程推进。LLM 只做纯文本展示、不驱动端侧状态的，不适用。
- `LLM_PAYLOAD_ADVERSARIAL`: required-for-llm-driven — acceptance 必须含「LLM 行为变异清单」：乱序、重复、schema 违约（必填字段缺失/写错位置）、超长文本、拒不调用工具，每类至少一条端侧容错断言（容错/自救/降级出口）。缺失 → plan-task 开工 BLOCKED（同场景矩阵门禁待遇）。
- `STOCHASTIC_MIN_RUNS`: 2 — LLM 驱动的多步流程（测验/多轮会话）真机 root run 至少 2 次独立完整跑，且至少 1 次在长上下文会话（≥10 轮历史）中；两次都完整收尾才计 PASS，单次跑过记 PASS 不达标。

## 冷启动
- `COLD_START_SCENARIO`: required-for-stateful-init — 功能行为依赖异步注册的服务/远程配置/登录态时，场景矩阵必须含冷路径：全新安装（或清数据）→ 首次登录 → 直达功能页，断言功能可用。暖重启（杀进程重进）不算冷路径。

## 会话续接
- 会话续接时，冒烟（`FULL_SURFACE_SMOKE`）重跑同一声明范围；续接细则 `references/user-attention.md`。

## hook/CI 锚点
- 启用强制锚点的项目可在 hook/CI 里用一行 `grep -q '^VERDICT: ' <journal>` 兜底（`JOURNAL_VERDICT` 本身是纪律不是机器门，默认路径无 validator）。

## 规则变更
新增/退休门（诊断码、检查项）时读。
- `GATE_REGISTRY_DISCIPLINE`: required — 新增任何门必须在提交说明或 `gate/PROTOCOL.md` 声明四样：防的诊断码、防的哪条实测逃逸、复审日期、代理在这道门被拒的那个状态下的合法出口。答不出第四问的门不许合入。
- 退休数据：`python {GATE_SCRIPT} stats --root <repo> [--window N]` 统计各账本当前触发；refusal log（`stats` 末尾按码计数）补"历史上拦过谁"。连续 N 个 run 零触发的门列为退休候选；候选只是候选，退门是设计决定，须对照该门当初防的逃逸再拍板。数据源之一是 retro.md 自我批评（RULES R12）。
