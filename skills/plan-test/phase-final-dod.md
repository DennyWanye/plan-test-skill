# Phase 收尾 — Definition of Done + 文档回写 + 自我批评

**目的**：合上闭环。全部勾选才宣布完成；文档回写让下次从最新基线起步；一行自我批评让流程自身持续瘦身。

## 片交付与整体收尾

先按 `references/delivery-slices.md` 明确此次是片交付还是整体完成，以及 run 对应关系。同一整体 run 内片里程碑只核该片能力、review/回归与提交身份，保持整体未完成，不执行本节整个 run 的终态/receipt 收尾。各片独立 run 使用本清单核该片完整冻结范围，receipt 不能扩大为整体 PASS。整体收尾必须覆盖原始全部 MUST、跨片组合能力和必要累计回归；若任一缺证据，整体仍未完成。片交付后按现有授权自主推进，生产发布不由切片自动授权。

## 收尾顺序

1. **文档回写**：README / changelog / `{TESTCASE_DIR}/index.md`；项目自己维护架构文档的顺手更新
   （本 skill 不再强制维护独立架构文档）。
2. **DoD 清单逐条核对**（下节）。
3. **journal 终态行**（`JOURNAL_VERDICT = required`，语义与登记见 config；**格式的唯一
   出处是本节**）：在 `journal.md` 末尾写一行——

   ```text
   VERDICT: SHIPPED | BLOCKED — <TESTED SCOPE> — <日期> — <被测 HEAD sha>
   ```

   被测 HEAD = 验证针对的代码提交（收尾文档提交尚未发生，不写它）。BLOCKED 时同行附
   一句卡点——结论定不了 SHIPPED 就如实写 BLOCKED，这是本门的合法出口，不存在堵死态。
   终态行必须与 DoD 结论一致。
4. **自我批评一行**（`SELF_CRITICISM = required`）：回答"本次哪些门空转了、哪里被仪式拖慢了、
   哪个环节真拦住了问题"，一两行写进 `{PLANS_DIR}/<feature>/retro.md`。这是门禁退休评审
   （config `GATE_REGISTRY_DISCIPLINE`）的数据源——规则集只进不出是本套流程的病，
   数据从这里来。
5. **提交**：全部改动提交，工作树干净。
6. **push 前 code review 硬门**（`CODE_REVIEW`，适用判定同 phase-3 A4；仅在本次交付要推送
   远程时做，不推送则跳过并留一句理由）：对将要推送的 diff 再过一遍 code review——A4 之后
   新增的改动（审计补漏、收尾期的代码修补）都在此照见。**P0/P1 修完再推**；修复动了代码 →
   按 phase-3 A4 第 4 步分层复验，且触及 UI/用户可见行为时按 phase-4 ③4 广度规则重跑
   受影响场景 + 至少 1 个未受影响类别（FULL 路径由 `re-attest` 的 behavioral 判定机器强制）。
   review 结论与处理入 journal。
7. **FULL（`MACHINE_GATE` 启用）额外**，固定顺序（顺序错了会死锁）：文档回写 →
   `re-attest --reason "收尾文档回写"`（`kind=behavioral` 时 required 场景须重跑入账）→
   启用 active-run 绑定时重新 `activate-run` → 重跑独立 full-audit 并 `audit` 入账
   （re-attest 改变了 fact，旧审计已 stale）→ `finalize` exit 0 拿 receipt → `render`。
   **最终交付判定只接受 `finalize` 的 exit code**（exit 3 = fixture-only 不是完成）；
   没有有效 receipt 的手写 SHIP/100% = `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。
   FAIL 后又改了代码 → 回第 1 步重来。run-dir 产物不参与内容指纹与提交态检查。

## DoD 清单（全绿才算完成——每条附证据位置，不许口头打勾）

> "我确认过了""逻辑上没问题""同类已验证"都不算证据。任何一条附不上证据 → BLOCKED 升级，不得宣布完成。
> **验证必须针对 git 已提交状态；对未提交工作树的任何 PASS 一律不作数。**

- [ ] **主要矛盾对应的决定性 AC 已实测达成**（业务上可用，非任务打勾）—— 证据：核心价值 smoke
  输出 + 审计结论。**此条 FAIL 时其余任何 PASS 都不能救场**
- [ ] **整体可用性实测通过**：按原始需求的核心使用路径整机走通 —— 证据：journal / 审计记录
- [ ] 全部"必须" AC 有测试证据通过 —— 证据：phase-4 兑现表（含 UI 的须真机 MCP 证据；
  无 ❌、无未经用户批准的降级）
- [ ] **执行期 plan 层回炉已全部闭环**：无"用补丁掩盖 plan 缺陷"的遗留 —— 证据：`a2-events.md`
  全部标记已回炉闭环
- [ ] **工作树干净且已提交（`COMMIT_STATE_GATE`）** —— 证据：`git status --porcelain`
  （FULL 排除 run-dir）空输出 + `git log -1` hash。尤其警惕未跟踪的路由/接线文件
- [ ] **干净态复验**（多代理/worktree 参与实现时必做）：提交后干净态重启服务，重跑核心价值
  smoke + 声明范围分级冒烟——证明**通过的代码 == HEAD 的代码**
- [ ] 分级冒烟通过 —— 证据：冒烟脚本输出（范围与升级判断已记录）
- [ ] 无回归：构建/测试/lint/类型检查不低于 phase-2 绿色基线 —— 证据：命令输出对比
- [ ] 幂等性审查已逐条过 —— 证据：审查结论
- [ ] 可追溯矩阵无断点：AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 证据 —— 证据：审计 VERDICT
- [ ] testcase 已存盘、index 已同步、脚本已纳入回归套件 —— 证据：文件路径
- [ ] journal 终态行已写且与 DoD 结论一致（`JOURNAL_VERDICT`）—— 证据：journal.md 末行
- [ ] code review 已按适用判定执行（phase-3 A4 + 要推送时的 push 前硬门），P0/P1 findings
  全部闭环且各有决定性测试 —— 证据：journal 的 review 记录行（不适用时留一句理由）
- [ ] retro.md 已写自我批评一行 —— 证据：文件路径

**输入语义敏感功能追加硬门**（任一不满足 → DoD FAIL；确定性 UI 不适用）：

- [ ] 至少 `{MANUAL_MIN_POSITIVE_SAMPLES}` 个 positive-value 场景达成（自然语言 + 真实入口 +
  真实 provider + 非空有效结果 + 人工检查达 quality_bar）—— 证据：广度账本业务终态列
- [ ] 没有任何正向 AC 是靠负向安全行为（诚实降级/fail-closed）作证的
- [ ] required 场景无 PENDING/PARTIAL/NOT RUN；distinct 计数达标且 retry/改写未混入
- [ ] 未执行项仅两种合法来源：acceptance 预标 optional/out-of-scope，或用户 chat 显式批准缩减
  （已回写 acceptance；结论按缩减后范围表述）

**FULL 追加**：

- [ ] `finalize` exit 0 + `GATE RECEIPT: <digest>` —— 证据：`gate-receipt.json`
- [ ] auditor open/deferred P0/P1 为零 —— 证据：`list-audit-findings`

> **末尾自检（长任务尤其做）**：宣布完成前回看兑现表——required UI 测试有没有被悄悄换成代码
> 审计？受阻场景有没有未经升级的等价替代？同一问题多次重跑有没有被写成"多场景验收充分"？
> 验证通过的内容是不是就是要交付的内容？任一命中就不是 100%，回去补或标 BLOCKED。

## 升级与交付措辞（硬规则）

升级时按 `references/user-attention.md` 说明已调查事实、已尝试方法、推荐出口和需要的最小用户动作。范围内仍能修复就继续；不得把 BLOCKED 自动作结束任务或要求重复批准的理由。

- 任一必须 AC 为 FAIL/PENDING/无证据 → 总体结论只能写 BLOCKED/FAIL；局部 PASS 必须标注作用域
  （"安装链路 PASS"）；**禁止用多个基础设施 PASS 稀释一个核心产品 FAIL**。
- 总体 BLOCKED 时用户要求"启动让我测试"→ 必须先告知：这是已知失败版本、启动目的是复现/补证据、
  已知会失败的场景清单。不许只说"已启动"。
- 默认路径交付措辞：如实写明"完成判定依据 journal 与 DoD 清单（无机器 receipt）"+ 测试范围 +
  证据位置 + KNOWN GAPS。FULL 路径用 receipt 模板（TESTED HEAD/SCOPE/各 lane/KNOWN GAPS/
  GATE RECEIPT，见 `gate/PROTOCOL.md`）。"100%" 只表示声明范围内 required 门全绿。
- 全绿 → 最终总结：做了什么、主要矛盾如何被验证、覆盖哪些 AC、证据在哪、文档更新在哪、
  回归套件新增了什么。

## 存储卫生

- `du` 检查 plans/testcase 下的大体积证据；超保留策略的截图/录屏/重复日志只留可追溯指针或摘要。
  不删除 active run、唯一证据或用户要求留存的产物。
- 清理已完成且无未提交改动的临时 worktree；不动用户正在使用或来源不明的 worktree。
