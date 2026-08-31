# plan-test 设计背景（冷路径）

> 本文件解释“为什么”，不属于执行热路径。日常运行只读 `SKILL.md`、`config.md` 和当前 phase；
> 修改规则或做门禁退休评审时再读本文件，节省上下文与 token。

## 风险路径而非文件数

文件数不是风险：一个鉴权中间件可能比二十个文案文件更危险。DIRECT / LEAN / FULL 以可逆性、
信任边界、状态、公共契约和副作用判定，避免小改被全流程成本压垮，也避免单文件高风险改动被低估。

## 流程分档（FLOW_TIER）的由来

此前只有二元选择——要么全套 8 阶段（一轮 15–25 万 token），要么“别用本 skill”。
中等改动被迫走全套，代理跑到一半开始自行省略；**一旦学会“这条规则在我这个情况下可以变通”，
其余规则的权威一起塌掉**。分档是为了让裁剪变成明示的、有边界的选择，而不是偷偷跳步。

## 全局串行的代价（DeskPet 2026-08-03 复盘 P1-6）

testcase/fixture/gate 准备耗时 3h27m，几乎全部本可与 2h30m 的实现段重叠；全局串行是那次
10h20m 里最大的可压缩项。这些准备工作几乎不依赖实现代码——依赖的是 acceptance 与行为契约，
phase-2 定稿时就齐了。由此立 SKILL.md“推进规则：依赖图，不是全局串行”与 phase-3 D 并行验证准备轨。

## Acceptance-preserving Ponytail

“只增不减”会把内部实现也误当成不可删除，最终鼓励重复 helper、wrapper 和防御性流程膨胀。
正确下限是已批准外部行为、assurance 和 required oracle；下限之上应尽量复用、删除和简化。
统一规则见 `policies/acceptance-preserving-ponytail.md`。

## 提交态与内容身份

脏工作树上的 PASS 不能证明交付提交。Gate 使用被测内容 digest，并把 run-dir 排除在 digest 外，
使“不改字节的提交”不使 receipt 失效，同时仍能拦截漏提交的代码和接线文件。

**半截提交的病根**（config“交付一致性门禁”各门的由来）：多代理 + git worktree 工作法下，验证
可以在一棵脏工作树上全绿，而关键文件（尤其“把服务层接到端点上”的路由接线层）未提交，随后被
worktree 清理 / `git clean` / 硬 reset 抹掉——git 里留下**能编译、能过类型检查、单测也绿**的
“半截健康”状态，但用户路径根本没接通。

**收尾顺序的死结**（phase-final ⓪ 的由来）：先 `finalize` 拿 receipt，再做“文档回写”必然改文件
——提交则 `RECEIPT_STALE`（tested HEAD 变了），不提交则违反 `COMMIT_STATE_GATE`（工作树不干净），
两边都堵死。真正的修法在 validator 里（schema 1.2.0）：阻塞判据从“提交身份（HEAD + dirty patch）”
改成“**被测内容**指纹”——`git add`/`git commit` 一个字节都不改，指纹就不变，门照样绿；改一个
字节则照拦不误。仅靠调整文档顺序解不开这个死结，那只是把它挪到下一步。

## Markdown 不是状态 authority（机器门禁的病根）

此前所有严格规则只是 Markdown——代理仍可以在详细 testcase 写着 `PARTIAL/BLOCKED/NOT RUN` 时
手工写出 `100% COMPLETE / SHIP`。Markdown 从此只是给人读的视图；状态 authority 是结构化账本 +
deterministic validator。

## 适用性判定为何必须入账

判一句“这是确定性 UI”，场景矩阵、正向价值门、随机采样、冷启动四道门就合法消失，
而 validator 完全不知道发生过这件事——这是本 skill 此前最大的一个洞。

## full-audit 为何移到 phase-5 末尾

此前 full-audit 在 phase-4、而结果回写与状态一致性修正在 phase-5，审计后输入仍可变化却继续
沿用旧 PASS。现在顺序是：phase-4 只执行测试并写账本 → phase-5 校验证据、回写状态、冻结
artifact → phase-5 末尾才跑独立 full-audit → final DoD 只跑机器 validator 生成 receipt。

## 冷路径为何必须排最前

phase-4 ② 的服务启动、数据准备、全端点冒烟跑完后系统必然是暖的，此后再“补跑冷路径”只是
暖态重放。此前 ③ 排在 ② 之后却要求“必须先跑冷路径”，是自相矛盾的死结；现在 gate init 开账
与冷路径实跑提前到门序最前。

## Fanout 证据深度

一次 pytest/smoke 被复制登记到多条 AC，不等于多个场景都获得了独立断言。required 场景在 fanout
组中必须各有 primary evidence；使用 `record-run --exec` 或逐场景 attach 独立日志。

## 真人覆盖为何分开记账（phase-4 ①c 的病根）

同一个问题重复跑 4 次 + 一次 continuation，很容易被写成"真人验收充分"。深度（失败→重试→
恢复）证的是可靠性，广度（语义不等价的输入）证的是覆盖，两者混记就会用深度冒充广度。
W6-20 起账本表由 `render` 自动生成，人只补业务终态与 quality_bar 结论。

## 判档与遥测为何入账（W6-22/23 的病根）

FLOW_TIER 判 LEAN 使 phase-0 架构挑战、多轮 closure、testcase 多轮挑战合法消失，
却不留痕——enforcement-anchors run-001 实测判档理由失实（声称"无删改 hunk"实有 40 行
删除跨 9 文件），只靠人肉 auditor 事后发现。phase 遥测自愿制下 18 本真实账本仅 9 本有
阶段事件（user_wait declared 896.9min / measured 0），档位压缩效果永远无法评估，
"实践—认识—再实践"的循环是断的。两者与 applicability 同一待遇：判定是 fact，入账可追责。

## 2026-08-31 DGX 双机部署复盘：为什么这轮优化是净删减 + 降出口成本

两次真实部署（DeepSeek V4 Flash 57h 未完成、MiniMax H3 51.8h 成功但真实工作仅 1.5h）给出裁决：

1. **机器门被实践整体绕开**：三份账本执行半区（runs/evidence/delivery/finalize）全空，
   "唯一完成 authority"零调用；唯一成功交付用手写 receipt。前史：08-28 收集已知 receipt
   仅 4/18、复验 0/18、run 目录作废率 73%、56% 测试事实随换目录报废。历次优化对
   "门不被用"的回应全是加强制（hook）加监测（遥测）加门（SIBLING 等），从未降低
   finalize 出口成本——于是行为三段进化：糊弄门 → 换 run-dir 绕门 → 整体不进门。
   **教训：出口的边际成本必须低于"作废重开"，否则一切侦测都是下游打捞。**
2. **门禁文化外溢成最大故障源**：任务内自造 receipt/锁/校验器约 15 个连环 fail-closed
   全是自家 bug、42 张 receipt 无终态、自造锁仪式 494 文件（243 个周期持锁中位 7.4 秒）。
   由此立 `SELF_BUILT_DEFENSE: forbidden`。
3. **任务类型错配**："共享基础设施→FULL"把运维任务推入最重的软件交付仪式；对照组
   dgx-200k-model-matrix（08-27，旧版 skill）单会话 4h 拿 receipt。由此立 `TASK_TYPE` 维度
   与 OPS 路径。
4. **主要矛盾三处皆虚**：plan 模板只要求写一句（DeepSeek 写成八目标复合句、MiniMax 把防御
   排第一优先，均无人发现）；审计"主要矛盾优先"在 phase-3 末尾是事后验尸；VALUE_SMOKE_GATE
   因"非输入敏感"合法消失——价值时刻被依赖拓扑排到第 46 小时，用户被迫人工纠偏
   "先试着跑起来先，先把主要任务做好，主要矛盾处理好"（08-30 15:13，成为总纲出处）。
   由此把主要矛盾升为一等公民：acceptance 必填 + challenger 固定质询 + 最短价值路径排序 +
   价值里程碑硬门 + 矛盾转化。
5. **修一行重验全链**：同一资格动作重复 23 次。由此立 `REVALIDATION_SCOPE: change-scoped`。
6. **保留的精华**（同一批实践证明有正回报）：challenger→只读实测→真代码 spike 链条
   （NRestarts=108 端口竞争、121.7GiB 内存预算、NCCL retrans 复核、被挑战强化的 fallback
   救了 4 次回滚）；workflow 1.5 挑战编排（7 轮 closure 压到 1–3 轮）；acceptance AC 编号
   体系（全链条公共语言）；跨任务串行锁的最小形态（真兑现过一次 9.5h 互斥）。
7. **给下次优化的告诫**：当实践给出"规则不被用"的证据时，先怀疑规则成本，再怀疑执行纪律；
   把单一项目的教训普遍化成硬规则前，先在不同类型任务上检验（本套规则源自 App 项目复盘，
   却被套在运维任务上）。规则集的健康标准是"只出不进的整风轮"真的发生过。

## 门禁退休评审

真实复盘容易形成“发现绕过 → 再加一道门”的累积。每道门单看合理，整体可能成本过高。定期运行：

```bash
python skills/plan-test/scripts/gate_usage_report.py --repo-dir <repo>
```

真实 run 从未触发、只在 fixture 触发的门，应优先评估合并、降级或删除；时效性诊断单独看，避免
把随代码前进自然出现的 stale 当成门禁价值。
