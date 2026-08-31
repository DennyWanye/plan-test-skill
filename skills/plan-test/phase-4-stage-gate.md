# Phase 4 — 验收门禁（测试策略路由）

**目的**：执行完成后的**统一终验关卡**（本流程走一次；plan 若含多个独立交付批次，则每批次收尾各过一次）。**便宜的门在前，贵的门在后**——别在编译都过不了时就上昂贵的真人测试。

## ① 测试策略路由（先决定怎么测）

按被测对象选择测试方式（`TEST_STRATEGY = route`）：

| 被测对象 | 测试方式 |
|----------|----------|
| 有 UI 的 Web / 桌面应用 | **MCP 真人点击/输入**（见 `checklists/manual-test-mcp.md`），`MANUAL_TEST = required`，不可省略/降级 |
| 后端 API / CLI / 数据管道 / 库 / 定时任务 | **写自动化测试脚本**（单元/集成/e2e/API），可重复运行 |
| 既有 UI 又有后端逻辑 | **两者都做**：脚本兜底逻辑，MCP 验交互 |

> 自动化脚本不是"手工测不了时的降级"，而是某些被测对象的**正确手段**。脚本必须**存盘、可复跑、纳入回归套件**（不是跑完即弃）。

## ①b 真人测试逐条兑现（防降级硬闸）

**这是本 skill 最常被偷工的一环，长任务末尾尤甚——必须机制化，不靠自觉。**

1. **产出兑现表**（不产出此表不得进入本阶段出口）：逐条列 `{ACCEPTANCE_FILE}` 的每条"必须" AC——

   | AC | 是否含 UI | 测试方式 | 驾驶者 | 真机证据（截图/log/DB 位置） | 状态 |
   |----|----------|----------|--------|------------------------------|------|
   | AC-x | 是 | MCP 真人点击 | AI 驱动 / 真人 | testcase/.../s3.png + logcat 行 | ✅/❌ |

   - **含 UI 的 AC，"真机证据"列必须是实际 MCP 点击证据**（截图/交互）。填"代码审计""逻辑等价""同类壳等价验证"的，一律记 **❌ 未完成**，不是通过。
   - 后端逻辑 AC 用可复跑脚本断言作证据。
   - **「驾驶者」列必填**：每条真机证据标注 `AI 驱动` 或 `真人`。**AI 经 adb/MCP 驱动 ≠ 真人**——系统性偏差清单与熵注入处置见 `checklists/manual-test-mcp.md`"驾驶者偏差警示"，偏差要写进表注让降级可见。**输入语义敏感功能，至少 1 个 required 场景必须真人驾驶**；确需全 AI 驾驶，须用户在 chat 中显式批准并在兑现表注明（机器门形态见 config `AI_DRIVING_APPROVAL`）。
2. **禁止静默降级**：任何 `required` 真人测试**无法执行**（环境受阻、设备缺失、数据造不出、标记删不掉等）→ **必须标 BLOCKED 升级给用户**，讲清卡点与解锁条件。**不许自行改用代码审计/等价验证替代**；确需等价方案，须用户在 chat 中**显式批准**，并在兑现表注明"用户批准降级"。
3. **"功能通过 ≠ 测试充分"**：核心链路跑通只覆盖了少数 AC。兑现表要照见**每一条**，尤其设置项、开关态、角色/权限隔离、空态、错误态——这些最容易被"主流程通过"掩盖。

## ①c 真人覆盖账本（输入语义敏感功能必做，接在兑现表之下）

深度（失败→重试→恢复）和广度（语义不等价的输入）是两回事，必须分开记账。（病根复盘见 `rationale.md`「真人覆盖为何分开记账」。）

1. **账本由 `render` 自动生成**（W6-20，2026-08-29）：`{GATE_SCRIPT} render --run-dir <run-dir>`
   在 report.md 输出「真人覆盖账本」表（scenario / gate_type / input_class /
   root / retry / continuation / 业务终态 / 状态）与汇总计数——**不再人肉手抄**，
   Markdown 是视图不是 authority。人只补两样机器推不出的，并经 `record-run
   --business-terminal` / testcase 结论回填入账：
   - **业务终态判定**（engine 终态 ≠ 业务成功）；
   - **quality_bar 人工检查结论**。

   **必须按业务终态判定**（正向价值下限见 config `MANUAL_MIN_POSITIVE_SAMPLES`）：
   - `positive-value` 场景：业务终态必须是"非空有效结果 + 达 quality_bar（人工检查过）"才算 ✅；engine completed 但业务 insufficient/空结果 → **安全行为 PASS、产品质量 FAIL**，场景记 ❌。
   - `negative-safety` 场景：insufficient/诚实失败才是预期 ✅；**insufficient_evidence 不得被拿来证明任何正向 AC**。
   - **fallback 成功 ≠ 功能正确**：fallback 不崩只是可靠性 PASS；fallback 后的**语义是否仍然正确**（没把专业意图退化成 generic 查询）是独立判定项，语义错了场景记 ❌。

2. **计数纪律（不许自行解释，定义见 config `MANUAL_MIN_DISTINCT_CLASSES` 与 phase-A 场景矩阵）**：
   retry/重放/同意图改写只证可靠性、continuation 只证 lineage/补研，均不增加 distinct scenario 数；
   每个 required distinct scenario **至少 1 次真实 UI root run**（含证据）。

2b. **llm_variant 维度**（LLM 载荷驱动的功能必做，判定见 config"LLM 载荷对抗门禁"）：
   - **场景矩阵的 distinct 只按用户输入分类，会漏掉 LLM 输出形态这条变异轴**——对"LLM 生成结构化载荷驱动 UI"的功能，账本额外按 `载荷形态（题型/卡片类型 × 长短文本等） × 场景` 记账，加一列 `llm_variant`：

     | scenario_id | llm_variant | root runs | 状态 |
     |-------------|-------------|-----------|------|
     | S-x | fill_blank | 1 | ✅ |
     | S-x | choice-短选项 | 1 | ✅ |
     | S-x | choice-整句选项 | 0 | ❌ PENDING |

   - 声明为 required 的载荷形态**未覆盖即 PENDING**，按 `{MANUAL_REQUIRED_PENDING_POLICY}` 处理——"这轮 LLM 恰好没出这种题型"不是覆盖，是采样缺口，须构造/诱导该形态或明确记 PENDING 升级。
   - **随机性采样**：见 config `STOCHASTIC_MIN_RUNS`（root run ≥2 次独立完整跑、≥1 次长上下文；单次跑过不得记 PASS）。

3. **门禁规则**：
   - distinct 已执行数 < 矩阵 required 数，或 < `{MANUAL_MIN_DISTINCT_CLASSES}` → **Gate FAIL**；
   - 任何 required 场景 PENDING/PARTIAL/NOT RUN → **Gate FAIL/BLOCKED**（`{MANUAL_REQUIRED_PENDING_POLICY} = block`），不得以"核心交付 PASS"表述掩盖；
   - **修复后的复测广度**：修好某场景后，除复测该场景外，**至少再复测 1 个未受影响的类别**（防修复引入回归）。
   - 确定性 UI（判定见 config）不适用本节，不许反向强套。

## ② 门的顺序（红则先修，不进下一层；主要矛盾优先于昂贵收尾）

> **冷路径必须排在最前**（`COLD_START_SCENARIO` 适用时；病根见 rationale.md「冷路径为何必须排最前」）。
> **正确顺序**：**第 0 步 gate init 开账（见本节末"昂贵层前置 2"，冷路径适用时必须提前到这里做，
> 否则 `record-run` 会因账本不存在而报错）→ ③ 冷路径场景实跑并 `record-run` 入账 → 本节 1–8**。
> 冷路径不适用时，init 仍按"昂贵层前置 2"的位置执行即可。

1. 类型检查（tsc --noEmit / dart analyze 等）
2. lint
3. **服务层-路由接线断言（`WIRING_CHECK = required`）**：本次在 services/、prompts 等处新 `export` 的函数/枚举/新增入参，routes/ 入口层必须有**真实引用**。轻量机检：`grep -rL "<新导出名>" <routes目录>` 命中"无任何路由引用" → 人工确认是否漏接，漏接即 FAIL。运行时白名单数组（如路由里的 `PERSONAS = ['friend','roast','quiet']`）必须与对应类型全集同步：用 `satisfies readonly <Type>[]` **且**加一条 exhaustiveness 断言测试——"数组少一个枚举值"tsc 完全不报错，必须让它变红。**类型检查绿 ≠ 运行时白名单同步。**
4. 单元 / 集成测试脚本
5. **核心价值 smoke（语义与适用范围见 config `VALUE_SMOKE_GATE`）**：执行 acceptance 声明的最小
   验证动作（输入敏感功能为 2–5 个自然语言正向问题，走真实入口 + 真实 provider）验证主要矛盾。
   **失败 → 立即 BLOCKED 早停**，不进入昂贵步骤——别在核心价值未证实前先烧几 GB 的构建。
6. **分级冒烟（分级策略与范围权威见 config `FULL_SURFACE_SMOKE`）**：声明范围内每个入口各打
   一枪，任一 404/500/未接通即 FAIL；枚举参数逐值验证。脚本存盘、可复跑、纳入回归套件。
   > 排查口诀：功能点了没反应/报错 → 先 `grep -rn <端点或路由名> <routes目录>` 看路由文件在不在、index 挂没挂、路由有没有真的取用服务层的新入参。
7. **真实 provider 契约门（含 LLM 结构化输出的功能必做）**：用**当前真实 provider 的实际输出**过一遍生产 validator，确认 schema 兼容（字段、枚举值、大小写不漂移）。手工构造的合法/非法 payload 只能测 validator 本身，**不能证明真实输出能通过**。
8. （以上全绿后）→ 昂贵层：MCP 真人完整矩阵测试

**昂贵层前置：testcase 冻结**。进入昂贵层（末层 MCP 真人完整矩阵）前，本阶段要执行的 testcase 必须已**编写完成并通过 challenger 挑战**（正常已在 phase-3 D 并行验证准备轨完成，此刻只做核对与**冻结**；准备轨没做完就在这里补完再冻结，如实记为串行返工）。不许拿临时、未经挑战的 testcase 跑昂贵验收，测完再补定义。phase-5 收尾时只做实际结果回写与回归登记。

**昂贵层前置 1b：Test Obligation Matrix 验证**。testcase 冻结后验证测试义务矩阵：`acceptance.md`
必须包含该矩阵（DIRECT 不启动本流程，不适用）；每个 MUST AC 至少一个 delivery obligation；每个
required testcase 绑定至少一个 obligation（TO-xxx）；不存在无法说明必要性的 required testcase。
验证命令（见下方 gate init 后的检查步骤）会返回：
  * `AC_COVERAGE_MISSING`: MUST AC 没有 delivery testcase
  * `ORPHAN_REQUIRED_SCENARIO`: required 场景既不绑定 AC，也不绑定 in-scope risk
  * `UNJUSTIFIED_TEST_SCOPE`: 测试超出 acceptance/assurance 范围却被标为 required
  * `OBLIGATION_NOT_SATISFIED`: 定义的 obligation 没有对应的 testcase
任何错误 → 立即 BLOCKED，返回修正 testcase 或 obligation 定义。

**昂贵层前置 2：编译 manifest 并 init（机器账本开账）**。testcase 冻结完成后、执行任何昂贵测试前，先从结构化 verification spec 编译 manifest，再用 canonical gate 开账。字段、示例与编译校验语义见 `references/evidence-audit-lifecycle.md` §1（不手写 `full` case 子集、不让 gate 猜 Markdown；旧项目可继续读旧 manifest，新 run 用编译产物）：

```bash
python {GATE_SCRIPT} compile-manifest --spec verification-spec.json --output manifest.json
python {GATE_SCRIPT} init --run-dir <plan-folder>/verification/<run-id> --manifest manifest.json
```

**P0-2 新增（2026-08-14）：强制检查 release_unit 声明**

init 完成后，立即验证账本的 release_unit 字段：

```bash
python {GATE_SCRIPT} validate-release-unit --run-dir <plan-folder>/verification/<run-id>
```

- exit 0 → 继续；
- exit 1 → 立即 BLOCKED，输出 `RELEASE_UNIT_UNDECLARED`。

manifest.json 必须包含：
- `release_unit.slice_id`：本次 slice 标识符（如 "T4.1-A"）
- `release_unit.parent_program`：所属 program（如 "SDK-extraction"）
- `release_unit.scope_hash`：acceptance + plan 的内容 SHA-256

**禁止空 release_unit 执行**——这是本次失败案例的核心问题之一。

manifest 冻结：原始需求、acceptance、black-box testcase 文件 hash、场景矩阵（含 required/ui/gate_type/expected_run_created/required_lanes/min_root_runs/**input_class**/**cold_start** 和 required 场景必填的 **evidence_contract**）、**适用性判定 `applicability`**、`executor_engine`（以及可选的 `auditor_engine`/`challenger_engine` 声明——实际引擎偏离会被 advisory 曝光）、release_unit 体量指标、baseline HEAD。init 自动把全部 required 场景建为 `NOT_RUN`——**此后状态只能靠 `record-run` + `attach-evidence` 记录的事实由 validator 重算**，任何手写 PASS 不作数。

启用 active-run 绑定时（语义见 config `ACTIVE_RUN_BINDING` 与 `references/evidence-audit-lifecycle.md` §4），init 后执行一次 `python {GATE_SCRIPT} activate-run --run-dir <run-dir>`；每次 `re-attest` 后重新 activate。

**适用性判定必须写进 manifest（`APPLICABILITY_UNDECLARED` 会拦截）**：三维各一条
`{value, rationale(≥10 字), decided_by}`——

```json
"applicability": {
  "input_sensitive":    {"value": true,  "decided_by": "user",
                         "rationale": "LLM 调研 agent，输出质量随输入语义变化"},
  "llm_payload_driven": {"value": false, "decided_by": "agent",
                         "rationale": "LLM 只做文本展示，不驱动端侧状态机"},
  "stateful_init":      {"value": true,  "decided_by": "agent",
                         "rationale": "依赖登录态与异步注册的检索服务"}
}
```

判「不适用」合法不拦截但留痕可追责；判「适用」则矩阵必须真的兑现，否则
`APPLICABILITY_GATE_UNSATISFIED`——完整语义与兑现阈值见 config `APPLICABILITY_DECLARATION`。

**Blocker 早停铁律**：一旦"主要矛盾"对应的必须 AC 判 FAIL，**立即停止一切完成收尾**（打包、发布、DoD 推进、"接近完成"的表述），状态只能是 BLOCKED；可以继续做诊断与修复，修复后从本门序重新过。**已知 BLOCKER 还继续收尾 = 谎报进度**。

## ③ 测试环境就绪（真人测试前必做）

- 起服务（dev server / 后端 / 依赖服务）。
- 准备测试数据 / fixtures / 种子数据。
- 测完清理或隔离测试数据，避免污染。
- **冷路径反向条款**（`COLD_START_SCENARIO` 适用时，判定与场景定义见 config）：环境准备天然使系统处于**暖状态**，会遮蔽冷启动缺陷——若矩阵含冷路径场景，**必须先跑冷路径**再进入暖态循环测试；暖重启不算冷路径，不得用它冒充。

## 执行测试与修复

- 严格按已冻结的 testcase 逐条测：UI 用 MCP 真人点击，逻辑用脚本断言。
- **每条测试当场入账**：每次执行 `record-run`（scenario / kind=root|retry|continuation / lane / driver / engine 终态 / 业务终态 / Session ID / Run ID），每份截图/日志/命令回执 `attach-evidence --kind primary`（UI 场景加 `--ui-action`，负向断言加 `--negative-assertion`）。声明了 `evidence_contract` 的场景，手工 attach/import 必须加 `--metadata evidence-metadata.json`——只写 `--kind primary` 不足以满足 contract，格式与要求见 `references/evidence-audit-lifecycle.md` §2。**脚本测试优先用 `record-run --exec -- <cmd>`**：gate 亲自执行，result 由 exit code 决定（与 `--result` 互斥），输出日志自动成为 primary evidence；自报模式的曝光项见 config `SELF_REPORT_EXPOSURE`。
- **时间同步入账**：机器测试用 `record-timing --exec -- <cmd>` 包裹执行（monotonic 实测），真人测试用 `--declared-start/--declared-end` 申报（自动标 measured=false）；连续工作每 90–120 分钟跑一次 `checkpoint`；进入/离开阶段用 `phase-start`/`phase-end`（finalize 查配对）。**事后凭印象补账 = 无账**——阈值与诊断见 config `TIMING_HARD_GATE`、`EVIDENCE_REALTIME`（历史证据只能走 `import-evidence --from-run`）。
- **全 AI 驾驶须批准**（见 config `AI_DRIVING_APPROVAL`）。多阶段场景必须断言**状态序列与身份**，不只终点回答。
- **P1-1 新增（2026-08-14）：每 90 分钟检查 ledger 进度**：
  ```bash
  python {GATE_SCRIPT} check-ledger-progress --run-dir <run-dir>
  ```
  - exit 0 → 继续测试；exit 1 → 警告 `LEDGER_STALLED`，账本长时间无进展（runs/evidence/timing 都未增长；可能在绕过 gate、空转、或执行暂停未标记）。**建议主动向用户报告当前进度**，让用户决定是否继续。
- 报错 → 修复 → **复测**（含"至少复测 1 个未受影响类别"的广度要求，见 ①c）。修复动过代码 → tested HEAD 已变，相关场景须重跑入账（旧 run 记录保留为历史事实）。
- **临时测不了的场景：保持 NOT_RUN，不要记 `--result blocked`**——两种 BLOCKED 的语义区别与正确做法（阻塞原因写进证据、报告里 BLOCKED 升级）见 config `BLOCKED_SEMANTICS`。
- 全部执行完 → 进入 ④ 机器预检。

## ④ 机器预检（finalize --check-only）

> **时序**：full-audit 不在本阶段执行——phase-4 只执行测试并写账本 → phase-5 校验证据、回写状态、冻结 artifact → **phase-5 末尾才跑独立 full-audit** → final DoD 只跑机器 validator 生成 receipt（病根见 rationale.md「full-audit 为何移到 phase-5 末尾」）。full-audit 后代码、配置、testcase 或结果有任何变化，旧 auditor PASS 与 receipt 自动失效（`AUDITOR_INPUT_STALE` / `RECEIPT_STALE`）。

```bash
python {GATE_SCRIPT} finalize --run-dir <run-dir> --check-only
```

- 输出 `READY_FOR_AUDIT` 才能进入 phase-5；任何 DIAG（`REQUIRED_SCENARIO_NOT_RUN` / `UI_EVIDENCE_MISSING` / `RISK_CLOSURE_MISSING` / `APPLICABILITY_*` 等）→ 回去补测或补证据，不许"先进下一阶段再补"。
- **关于 `STATUS_CONFLICT` 的时序**：本阶段**尚未** `declare-status`（登记发生在 phase-5 3c 回写时，那里的重跑预检才是 STATUS_CONFLICT 的真实检查点），所以此处的 check-only 只可能因别的诊断 FAIL。
- 预检**不要求** auditor 已执行（否则永远无法进入审计阶段）；它检查的是除 auditor/receipt 外的全部输入与测试完整性。

## 出口

- 所有测试通过 + `finalize --check-only` 输出 `READY_FOR_AUDIT` → 进入 phase-5（full-audit 在 phase-5 末尾执行）。
