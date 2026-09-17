# acceptance-preserving-ponytail 瘦身移出的叙述（SL-3；存档非规范）

- 单一权威的理由：各阶段文档只引用本文件、不复制正文，是为了避免规则漂移。
- phase-2 挑战循环关闭最小化：避免 challenger 与最小化互相制造 finding。
- Final gate off 原表述："只按账本事实判定"（现并入"权威分离：Final 门禁只按确定性事实判定"）。
- 行为策略原文（正文已并入 RULES R13）：本 policy 取代 `FEATURE_POLICY = only-add` 中与重构冲突的部分；行为策略统一为 `BEHAVIOR_POLICY = preserve-approved`——不静默减少已批准外部行为，但允许删除、替换或重构内部实现，以及删除 acceptance 明确批准删除的旧行为。
