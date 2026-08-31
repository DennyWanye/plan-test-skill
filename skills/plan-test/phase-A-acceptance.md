# Phase A — 需求澄清 & 验收标准

**目的**：产出唯一真相来源 `{ACCEPTANCE_FILE}`。之后所有阶段（plan 收敛、完成度审计、testcase 覆盖）都引用它。没有它，"100% 完成"是没有定义的。

## 输入

- 用户在斜杠命令后给的需求文字，或指向的需求文件。
- 若需求是 `1.**** 2.****` 这类占位 / 模糊，**必须先澄清**——这是少数允许打断用户的时刻。

## 步骤

1. **抽取需求条目**：把需求拆成可独立验收的功能点列表。
1a. **写主要矛盾（必做，一等公民字段）**：一句话回答"这个需求决定成败的核心价值是什么"，
   并写出它的**最小验证动作**（用最小代价证明它成立的那一步）。格式硬约束见 phase-1"主要矛盾"节：
   单一矛盾、价值在前防御在后、复合句打包视为未写。用户确认 acceptance 时同时确认这句话——
   它决定后续全部任务排序与审计优先级（phase-1 排序 / phase-3 审计 / phase-4 价值 smoke 都以它为锚）。
1b. **Ponytail lite**：发现更简单的方案可能满足需求时，按
   `policies/acceptance-preserving-ponytail.md` 作为选项提给用户，不得自行删减需求或将条目标为 OUT。
2. **为每条写验收条件**：每条必须**可验证**（能被一次手工操作或一段脚本断言判定通过/失败）。
   - 反例："登录要好用"。
   - 正例："用 OAuth 登录成功后跳转到 /dashboard，且旧短信验证码入口仍可用"。
3. **标注边界与非功能要求**：错误态、空态、并发、幂等、性能阈值、兼容性。
3b. **冻结 assurance contract**：在 acceptance 同目录生成 `assurance-contract.json`，作为
   challenge gate 的结构化输入。所有任务都声明 failure/assumption/impact；只有安全敏感任务才需要
   adversary/asset/trust-boundary 细化。
   - 默认 `profile=standard`；不得因为 challenger 想到更强攻击者而自行升级。
   - 每条 asset、assumption、failure、adversary、out-of-scope condition 使用稳定 ID。
   - `hardened` / `hostile-host`、可信边界变化或扩大最大影响必须由用户明确确认。
   - assurance contract 的 scope/threat hash 在 challenge loop 启动时冻结；变化走
     `scope-change-proposal → user approval`，不能静默覆盖。
4. **测试场景矩阵**（输入语义敏感功能必做，判定见 config"真人测试广度门禁"）：
   - 为真人测试预先定义**语义不等价的输入类别**，至少 `{MANUAL_MIN_DISTINCT_CLASSES}` 个代表类别；适用时额外含 1 个错误态/低证据/对抗场景（`{MANUAL_REQUIRE_NEGATIVE_CLASS}`）。
   - **门分两类，缺一不可**：每个场景标注 `gate_type`——
     - `positive-value`（正向价值门）：普通高证据问题确实能接纳证据、生成**非空有效业务结果**且达到本表声明的最低质量线。required 场景中至少 `{MANUAL_MIN_POSITIVE_SAMPLES}` 个。
     - `negative-safety`（负向安全门）：没有证据/异常输入时诚实失败、不编造。
     - **只有负向安全门通过，不能宣布功能完成**（见 config `MANUAL_MIN_POSITIVE_SAMPLES`）。
   - **正向价值场景必须声明最低质量线**（terminal_expectation 之外再写一行"quality_bar"：什么样的结果算可用，人工按它 review）。
   - **exact_input 用自然用户语言**：写真实用户会打的话（口语、简写、中英混合、"最强/前10/优缺点"这类表达），**禁止照实现关键词写"容易通过"的 prompt**（latest/compare/benchmark 这类贴 fixture 的措辞）。
   - **计数纪律**：重试、重放、同一意图的改写、continuation 都**不增加** distinct scenario 数——换领域/难度/风险形态才算新类别。
   - 确定性 UI（设置页/开关/CRUD/导航）不适用此矩阵，常规 AC 覆盖即可。
   - **冷路径场景**（`COLD_START_SCENARIO` 适用时必含，判定与场景定义见 config）：矩阵中加 1 条"全新安装（或清数据）→ 首次登录 → 直达功能页"场景，断言功能在该路径可用；暖重启不算冷路径。
4b. **LLM 行为变异清单**（`LLM_PAYLOAD_ADVERSARIAL` 适用时必做，判定与门禁待遇见 config"LLM 载荷对抗门禁"——缺失此清单 → plan-task 开工即 BLOCKED）：
   - 在 acceptance 中列出五类 LLM 行为变异，每类至少一条**可验证的端侧容错断言**（容错/自救/降级出口）：
     ① 乱序响应（出题/推进顺序 ≠ 注入顺序）；② 重复输出同一项；③ schema 违约（必填字段缺失、内容写错位置、字段值与枚举不符）；④ 超长文本/极端载荷（整句选项、超长题干的 UI 边界）；⑤ 拒不调用工具/跳过注入指令。
4c. **测试义务矩阵（Test Obligation Matrix）**（所有任务必做）：
   - 在 acceptance 中定义测试义务矩阵，明确每个 required testcase 的必要性。字段见下方模板表
     （obligation_id / type / ac_id / risk / min_decisive_test / required_reason，其中 ac_id 为
     delivery 类型必填、risk 为 change-risk 类型必填）；类型定义、目标导向原则与适用性判断
     见 `checklists/test-obligation-matrix.md`。
   - 缺失此矩阵或 required testcase 无法说明必要性 → gate 返回 `ORPHAN_REQUIRED_SCENARIO` 或 `UNJUSTIFIED_TEST_SCOPE`。
5. **和用户确认**：把 `{ACCEPTANCE_FILE}` 草稿（**含场景矩阵和测试义务矩阵**）给用户过一遍，确认后才进 phase-0。用户确认 acceptance 即同时确认了场景矩阵的范围和测试义务的必要性。

## `acceptance.md` 模板

```markdown
# 验收标准：<需求名>

## 主要矛盾（必填，单一矛盾）
- 核心价值：……（一句话，一个问题；价值在前，防御在后）
- 最小验证动作：……（一条命令/一次请求/一个最短调用链）

## 范围
- 包含：……
- 明确不包含：……

## 功能验收条款
| ID | 功能点 | 验收条件（可验证） | 优先级 |
|----|--------|-------------------|--------|
| AC-1 | …… | 当 …… 时，应 …… | 必须 |
| AC-2 | …… | …… | 必须 |

## 非功能 / 边界
- 错误态：……
- 幂等：……
- 性能：……
- 兼容：……

## Assurance contract 摘要
- Profile：standard（默认）/ hardened / hostile-host
- 受保护资产：……
- 可信假设：……
- 范围内失败/对手：……
- 明确范围外条件：……
- 最大可接受影响：……

## 测试场景矩阵（输入语义敏感功能必填；确定性 UI 删除本节）
| scenario_id | input_class（语义类别） | exact_input（自然用户语言） | primary_risk（验证什么） | gate_type | required | manual_required | terminal_expectation | quality_bar（正向门必填） |
|-------------|------------------------|------------------------------|--------------------------|-----------|----------|-----------------|----------------------|---------------------------|
| S-1 | 例：教育知识类 | …… | 常规链路正确性 | positive-value | 是 | 是 | completed + 非空有效报告 | 例：≥N 条有效证据、结论人工可用 |
| S-2 | 例：时效新闻类 | …… | 搜索链路时效性 | positive-value | 是 | 是 | completed + 非空有效报告 | …… |
| S-3 | 例：跨域比较决策类（口语表达） | 例："这几个哪个最强？优缺点呢" | 多源综合 + 自然表达路由 | positive-value | 是 | 是 | completed + 非空有效报告 | …… |
| S-N | 例：冷门低证据类 | …… | 诚实降级不编造 | negative-safety | 是 | 是 | insufficient_evidence 是预期 | 不适用 |

## 测试义务矩阵（Test Obligation Matrix）（所有任务必填）
| obligation_id | type | ac_id | risk | min_decisive_test | required_reason |
|---------------|------|-------|------|-------------------|-----------------|
| TO-A1 | delivery | AC-1 | — | 正常路径执行一次 | 直接证明 AC-1 的主要功能 |
| TO-A2 | delivery | AC-1 | — | 错误输入返回预期错误 | 证明 AC-1 的错误处理 |
| TO-R1 | change-risk | AC-1 | FAIL-ROUTE | 新增路由可达性 | 本次改动涉及入口层 |
| TO-R2 | change-risk | — | FAIL-REGRESSION | 受影响的既有功能 smoke | 修改共享序列化层 |
| TO-E1 | exploratory | — | 潜在性能问题 | 高并发压测 | 未来风险探索（不阻断交付） |

**类型说明**：
- `delivery`：直接证明 MUST AC，required
- `change-risk`：防范本次改动的受影响范围内风险，有明确风险时 required
- `exploratory`：探索性测试，不 required

**风险适用性判断**：
- 并发/幂等：仅当有共享可变状态/副作用时
- 边界值：仅当在 AC 声明的边界内时
- LLM 对抗：仅当 `llm_payload_driven=true` 时
- 冷启动：仅当 `stateful_init=true` 时
- 性能/恢复/迁移：仅当 AC 明确要求时

## 完成的定义（DoD 摘要）
- 全部"必须"条款通过测试
- 所有 delivery 类型的 test obligation 都有对应的 PASS testcase
- 所有 change-risk 类型的 test obligation 都有对应的 PASS testcase
- 无回归
- 文档已同步
```

同目录 `assurance-contract.json` 使用机器可读结构：

```json
{
  "profile": "standard",
  "acceptance_ids": ["AC-1"],
  "protected_assets": [{"id": "ASSET-1", "description": "..."}],
  "trusted_assumptions": [{"id": "TRUST-1", "description": "..."}],
  "in_scope_failures": [{"id": "FAIL-1", "description": "..."}],
  "in_scope_adversaries": [],
  "out_of_scope_conditions": [{"id": "OOS-1", "description": "..."}],
  "maximum_acceptable_impact": "..."
}
```

## 出口

- `{ACCEPTANCE_FILE}` 与 `assurance-contract.json` 已生成且用户确认 → 进入 phase-0。
- 用户无法澄清关键条款 → 标记 BLOCKED，说明缺哪条信息。
