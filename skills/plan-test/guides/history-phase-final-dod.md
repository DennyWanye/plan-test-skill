# phase-final-dod 瘦身移出的叙述（SL-3；存档非规范，正文以 RULES 与阶段文档为准）

- 文档回写：本 skill 不再强制维护独立架构文档（项目自有的顺手更新）。
- 自我批评（`SELF_CRITICISM`）是门禁退休评审（config `GATE_REGISTRY_DISCIPLINE`）的数据源——规则集只进不出是本套流程的病，数据从 retro.md 来。
- push 前 code review 存在的理由：A4 之后新增的改动（审计补漏、收尾期代码修补）要在推送前再被照见一次。
- 终态行格式原先"唯一出处是 phase-final 本节"；SL-3 起唯一出处改为 RULES R12。
- DoD 反例："我确认过了""逻辑上没问题""同类已验证"都不算证据。
- 升级措辞原文要点（正文已并入 RULES R9/R11）：说明已调查事实、已尝试方法、推荐出口、需要的最小用户动作；范围内仍能修复就继续，不得把 BLOCKED 当结束任务或要求重复批准的理由；任一必须 AC FAIL/PENDING/无证据 → 总体只能 BLOCKED/FAIL，局部 PASS 标作用域（如"安装链路 PASS"），禁止用多个基础设施 PASS 稀释一个核心产品 FAIL；总体 BLOCKED 时用户要求"启动让我测试" → 先告知这是已知失败版本、启动目的是复现/补证据、已知会失败的场景清单，不许只说"已启动"；"100%"只表示声明范围内 required 门全绿。
- 终态行原文要点（正文已并入 RULES R12）：`VERDICT: SHIPPED | BLOCKED — <TESTED SCOPE> — <日期> — <被测 HEAD sha>`；被测 HEAD = 验证针对的代码提交（收尾文档提交尚未发生，不写它）；BLOCKED 同行附一句卡点，是合法出口；终态行须与 DoD 结论一致。
