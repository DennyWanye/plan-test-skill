# config 瘦身移出的叙述（SL-3；存档非规范，正文以 config.md / RULES / full / conditional 为准）

## 撤销的键
- `ARCH_DIR`：随 phase-0 撤销，现状调查并入 phase-1，结论写进 plan，不再维护独立架构文档。
- `PARALLEL_TRACKS`：2026-09-01 由 `EXECUTION_MODE: self-decide` 替代，验证准备轨撤销；其 black-box 精髓保留为"oracle 先于实现"（RULES R3）。

## 版本注记与病根
- `EXECUTOR_ENGINE`：不再默认绑定固定模型（如 GPT 系）；用户用 DeepSeek V4 Pro 执行子代理就是 DeepSeek V4 Pro，用 Claude 就是 Claude。
- 流程分档由来见 rationale.md「流程分档（FLOW_TIER）的由来」。
- `TASK_TYPE`（2026-08-31 DGX 复盘）：DGX 双机部署被"共享基础设施→FULL"推入最重的软件交付仪式（oracle 冻结、提交态门、Stage A/B），而运维任务真实风控是快照/回滚/串行锁；错配导致 49.5h 里仪式占 22%，agent 自造平行防御系统成最大故障源。
- OPS 路径模板 = 2026-08-27 dgx-200k-model-matrix（单会话、1 轮挑战、4h 拿到 receipt）。
- 不设可降档表：2026-09-15 用带降档表的草案对 9 个历史 FULL 运行两轮盲判仍 9/9 FULL——FULL 判定基本正当，耗时来自 FULL 内部（挑战循环 20–37%、待决挂起），降耗做在内部。
- `MACHINE_GATE`（2026-09-01 毛选方法论重构，反对党八股）：DGX 复盘实测机器门 100% 荒废、仪式占 22%；砍的是记账仪式，不是证据纪律。
- `JOURNAL_VERDICT` 四样登记（2026-09-01 审计整改）：防的逃逸 = 默认路径下"算不算通过"要靠通读 journal；诊断码 = 无（FULL 同类由 `DELIVERY_VERDICT_CONTRADICTS_LEDGER` 拦）；复审 2026-12-01；合法出口 = 写 BLOCKED + 卡点。终态行格式原"唯一出处是 phase-final"，SL-3 起改为 RULES R12。默认路径按 v0.7.0 设计无 validator。
- `CODE_REVIEW` 四样登记（2026-09-01）：v0.7.1 实测执行者自写归档代码经独立 review 查出 5 个数据丢失级 bug（并发 TOCTOU / 残缺归档 / 重复归档 / utf-8 毒丸 / 读取层缺失），自审全漏；诊断码 = 无（流程门）；复审 2026-12-01；出口 = BLOCKED 或用户批准跳过。
- `VALUE_SMOKE_GATE`：2026-08-31 升级为普适——此前部署类判"不适用"使本门合法消失，价值时刻推迟到第 46 小时；总纲出处用户 08-30 原话"先试着跑起来先，先把主要任务做好，主要矛盾处理好"。2026-09-10 加"走生产接缝"：s5b smoke 走 pytest 基座，基座补上每处生产装配缺口，9 个既有缺陷留到验收一次爆出（用户原话"不应该事先调研好吗"）。
- 提交态与内容身份病根见 rationale.md「提交态与内容身份」；Markdown 不是状态 authority 见 rationale.md 同名节；适用性判定为何入账见 rationale.md「适用性判定为何必须入账」。
- `EVIDENCE_REALTIME`：防"先测三小时、账本两分半补写完"（DeskPet 实锤）。`SELF_REPORT_EXPOSURE`/`AUDITOR_INDEPENDENCE` 引擎声明自 schema 1.4.0；`TIMING_HARD_GATE`/`EVIDENCE_REALTIME`/`IMPACT_SCOPED_RETEST`/`AI_DRIVING_APPROVAL` 自 schema 1.3.0。引擎声明入账让"配置写在 Markdown、实际用了别的引擎"在 report/receipt 可见。
- `GATE_REGISTRY_DISCIPLINE`（2026-08-26；第四问 2026-08-29）：规则集只进不出是本套流程的病；每次实测事故同一形状——门堵死合法出口 → 代理换 run-dir → 前面测试全废，作废率实测 56%。
- `HANDOFF_CHECK` 四样登记（2026-09-15）：防的逃逸 = 09-11~15 用户亲自拦下 7 次（需求做少 1、UI 代点/自测不净/demo 无反馈 3、决策讲不清 3）及 08-28~09-10 留出集同类；诊断码 = 无；复审 2026-12-15。DIRECT 只在四问命中才派评估员为用户 2026-09-15 决定。
- `DECISION_BATCHING`（2026-09-10；09-15 格式并入 HANDOFF_CHECK；09-17 v0.9.0 加不挂起）：timing 账本 `user_wait` 占 s5a r2 40%（375/928 分钟）、s5b r3 47%（420/893 分钟）；acceptance 修订 A1–A15 各要一次批准；用户原话"我不知道要决策什么""能把需要和我确认的一次性和我确认好吗"。不挂起病根：exec-002 撞 `FROZEN_ORACLE_CHANGED` 后 AskUserQuestion 挂起 439 分钟未回，其余工作全停，最终无 receipt。
- `SELF_BUILT_DEFENSE`（2026-08-31 DGX）：约 15 个连环 fail-closed 全是任务内自造校验器的 bug，42 张自造 receipt 无终态，自造 receipt 两次拒绝控制器自己的失败清理。
- `REVALIDATION_SCOPE`（2026-08-31 DGX）：为修一行 Nginx 配置重跑"提交→117 项回归→重封存→NCCL 复验→冷启动"全链，同一资格动作重复 23 次；已通过资格（网络资格、镜像封存、trust 配置、冒烟）是内容寻址的。
- `SELF_CRITICISM`：2026-09-01 毛选方法论重构（批评与自我批评）。
- `PROGRESS_REPORTING`（2026-08-31；09-10 加固）：s5b 把单个 increment 汇报成 program 全貌，用户追问"你还有好多没做完，找到原始 plan 再对比"；"说人话/大白话/我看的很迷茫"同批 ≥4 次。复述确认病根：H3 用户要越狱版、计划静默换成官方版，部署完才发现。
