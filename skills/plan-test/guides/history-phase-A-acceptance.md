# phase-A-acceptance.md 瘦身移出的说明性文字（SL-3 W2a）

- 目的原文补充：acceptance 被 plan 收敛、执行排序、完成度审计、测试力度分配共同引用；没有它，"100% 完成"没有定义。
- 矛盾原因为何要挖：原因判断错了，解法方向必然错（防解错题）。
- 主要方面举例：在"用户能否在线完成下单"这个矛盾里，主要方面是"下单业务链路能否跑通"而非"页面观感"。
- AC 可验证正例："用 OAuth 登录成功后跳转到 /dashboard，且旧短信验证码入口仍可用"；反例"登录要好用"。
- 两点论兜底（次要 AC 下限一轮挑战、一遍测试）正文已归入 RULES R2。
- 交互边界（真实意图缺失才问最小问题；重要行为差异以人话说明随 plan review；已有授权覆盖且无重要未决取舍不重复批准）正文已归入 RULES R11。
- 质量类要求（简洁明了、看得懂、说明原因）截图对照正文在 `checklists/handoff.md` H1。
- FULL 的 assurance-contract 与条件矩阵分别移到 `full/phase-A-acceptance.md`、`conditional/phase-A-acceptance.md`。
