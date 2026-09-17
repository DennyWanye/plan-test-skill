# plan-test 配置

键=默认值→细则(Rn=RULES.md，full=full/config.md，cond§X=conditional/config.md §X)。项目 `.claude/plan-test.config.md` 同名键覆盖，不得视沉默为批准、扩大授权或降 required 证据。(交接)=按 checklists/handoff.md 评估。

## 引擎与路径
- `EXECUTOR_ENGINE`: current — 继承当前会话模型(不指定 model)
- `CHALLENGER_ENGINE`: claude；`AUDITOR_ENGINE`: opus-4.8
- `PLANS_DIR`: ./plans；`TESTCASE_DIR`: ./testcase；`ACCEPTANCE_FILE`: ./acceptance.md
- 已撤销：ARCH_DIR、PARALLEL_TRACKS

## 流程分档
裁剪须明示有边界，不偷偷跳步；疑义往高判。
- `TASK_TYPE`: auto — 先判。`delivery`=交付代码/功能→`FLOW_TIER`；`ops`=让服务/环境到目标状态(部署/安装/升级/迁移/配置变更)→ cond§OPS
- `FLOW_TIER`: auto — 仅 delivery，开场写依据，用户可指定；DIRECT 条件全满足才 DIRECT；中任一 FULL 硬条件即 FULL；其余单切面 LEAN
  - DIRECT：可快速回滚、不涉权限/资金/身份/迁移、无新持久化状态、不改公共协议、不跨信任边界、不引新依赖 → 不启动本 skill，cond§DIRECT
  - LEAN(默认)：单个业务切面、用户可见、风险可局部隔离、有自动化出口、无高风险迁移/共享基础设施 → A…final；主要矛盾挑战四阶段、其余一轮；不跑机器账本、assurance-contract.json(摘要节代替)、次要 AC 多轮挑战/testcase 迭代
  - FULL：全套 + `MACHINE_GATE` 判定；挑战路由与增量补丁减轮见 phase-2，待决不挂起 R11
- **判定对象**：本片上线时首次进生产的全部改动(含同时首次上线的前序片、合并分支)。每片重判，沿用上片档位不是理由。事实未知(行数/写入频率/外键引用)先查，查不到按命中，写明未知项。
- **FULL 硬条件**(任一)：
  - 改鉴权机制；改已有角色对已有数据的可见/可写范围(能写此前写不了的行/列也算)；新增读写生产凭据(含第三方 token/密钥)。为本次新建数据按既有角色配访问不算，写次要 AC 并测
  - 批量改写已有生产数据(更新/回填/删除/合并)；唯一例外：可从源头全量重算的派生列且回退已实测
  - ≥10 万行或热表(≤1 小时周期批量写/用户实时写，频率未知算热)上跑需元数据锁的 DDL(含 `CREATE TABLE … LIKE`、加外键)
  - 多阶段状态机；LLM 结论决定落库状态或对外内容
  - 公共 Provider / 对外 API / 跨服务契约
  - 新增不可逆外部副作用(发消息、上架/下单、写第三方)；改已运行外部副作用的时机/次数/重试/授权来源("用户动作→外部写请求"链任一环节)；写非本服务 owner 系统的生产数据(已有写入加列也算)
  - 共享基础设施；`input_sensitive = true`
- 不设降档表。DIRECT 仍须一句 AC + 提交态硬门。LEAN 收窄不改 primary 先行，不先平铺专项。LEAN/FULL 不可裁剪 R1/R3/R5/R6/R8/R9/R13。
- `MACHINE_GATE`: full-high-externality-only — 仅 FULL 且命中权限/身份/支付、schema/迁移、公共 Provider/API、共享基础设施、不可逆副作用才启用 → full；否则记录=一页 journal(每条附实测证据)，措辞 R12(交接)
- 切片见 references/delivery-slices.md；每片继承全局风险，不靠分片降适用门
- `RELEASE_UNIT_LIMITS`: MUST AC ≤ 8 / Task ≤ 10 / plan ≤ 2000 行 / 高风险子系统 ≤ 3 / 同改 UI、Session、Harness、Provider、权限 ≤ 3 类 → full

## 轮次与出口
- `ASSURANCE_PROFILE`: standard → cond§保障等级
- `PLAN_ITERATIONS`: 1 — 无 open P0/P1 即收敛不凑轮 → phase-2
- → R9，细则 full：`PLAN_CHALLENGE_SOFT_LIMIT`: 3；`PLAN_CHALLENGE_USER_REVIEW_ROUND`: 5；`PLAN_CHALLENGE_HARD_LIMIT`: 8
- `MAX_ROUNDS`: 15 — 执行/审计兜底，非挑战预算 → R9
- `TESTCASE_ITERATIONS`: 2 → cond§testcase 迭代
- `AUDIT_RETRY`: until-100 — 未达 100% 循环补完

## 测试与交付一致性
- `VALUE_SMOKE_GATE`: required → R4(交接)
- `MANUAL_TEST`: required；`TEST_STRATEGY`: route → R5(交接)；`MCP_DRIVER`: auto → cond§UI
- `CODE_REVIEW`: required-for-code → R7(交接)
- `COMMIT_STATE_GATE`: required → R6
- → R8：`FULL_SURFACE_SMOKE`: required；`INCREMENTAL_AC_MODE`: on(小功能也走流程)；`REVALIDATION_SCOPE`: change-scoped
- 冒烟：脚本存盘可复跑；affected 按入口依赖/impact_paths；全量另含改启动装配/中间件、映射覆盖不全
- `WIRING_CHECK`: required → phase-4；`EXECUTION_MODE`: self-decide → phase-3
- cond§输入语义敏感：MANUAL_SCENARIO_MATRIX, MANUAL_MIN_DISTINCT_CLASSES, MANUAL_REQUIRE_NEGATIVE_CLASS, MANUAL_REQUIRED_PENDING_POLICY(交接), MANUAL_MIN_POSITIVE_SAMPLES
- cond§LLM 载荷：LLM_PAYLOAD_ADVERSARIAL, STOCHASTIC_MIN_RUNS；cond§冷启动：COLD_START_SCENARIO

## 机器门禁(启用才生效)→ full
- `ORACLE_FREEZE`: required → R3；`BLOCKED_SEMANTICS` → R9(hash 冻结/机器语义在 full)
- GATE_SCRIPT, RUN_DIR, RUN_EXIT_PATHS, APPLICABILITY_DECLARATION, AUDITOR_INDEPENDENCE, LEDGER_INTEGRITY, SELF_REPORT_EXPOSURE, TIMING_HARD_GATE, EVIDENCE_REALTIME, IMPACT_SCOPED_RETEST, EVIDENCE_CLASSES, MANIFEST_COMPILATION, EVIDENCE_CONTRACT, AUDIT_FINDINGS, ACTIVE_RUN_BINDING, ARTIFACT_DEDUPE, AI_DRIVING_APPROVAL(交接)

## 用户与行为
- → R11：`USER_ATTENTION`: protect；`EXECUTE_AUTONOMY`: high；`DECISION_BATCHING`: required；`PROGRESS_REPORTING`: user-language(交接)
- `HANDOFF_CHECK`: required → checklists/handoff.md
- `HANDOFF_EVAL_MAX_ROUNDS`: 3 — 每交接点独立计，不走 MAX_ROUNDS；两轮 open block ID 不变且无新证据即早停
- `SELF_BUILT_DEFENSE`: forbidden → R14；`BEHAVIOR_POLICY`: preserve-approved → R13
- → R12：`JOURNAL_VERDICT`: required(终态行格式唯一出处；journal 随 `{PLANS_DIR}` 进 git)；`SELF_CRITICISM`: required
- `GATE_REGISTRY_DISCIPLINE`: required → cond§规则变更
