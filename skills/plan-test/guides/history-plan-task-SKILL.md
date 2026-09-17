# plan-task/SKILL.md 病根与历史（SL-3 W2f 瘦身挪出，冷路径）

- 防跳步硬闸的病根：本 skill 的漏测几乎都源于没读阶段文档就动手（示例：phase-4 ⑤ 必做项 = 分步 testcase / 结果回写 / 幂等审查 / 语义等价审查 / index 同步，现以 phase-4 ⑤ 与 conditional 为准）。
- 末尾警戒（原标"最重要"）：长任务越接近收尾，越容易用便宜的代码审计替昂贵的真机测试来"尽快合上"。
- finalized 标记按包含匹配的原因：plan-bs 产出的标记带 `(plan-bs)` 来源后缀。
- 执行模式原表述"集中兵力当前 session 串行打歼灭战"；判据正文在 phase-3 开场。
- FULL 收尾跳过 re-attest 会报 `TESTED_RUNTIME_MISMATCH`、跳过重新 audit 会报 `AUDITOR_INPUT_STALE`（码义见 gate/PROTOCOL.md，顺序见 full/phase-final-dod.md）。
- 原 SKILL.md 各处复述的 code review / 价值 smoke / BLOCKED / 真人测试口径细节，SL-3 起只在 RULES.md 保留正文。
