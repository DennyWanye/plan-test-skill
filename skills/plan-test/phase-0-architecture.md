# Phase 0 — 架构基线

**目的**：确保 `{ARCH_DIR}/ARCHITECTURE.md` 反映当前代码的真实架构，作为写 plan 的依据。陈旧的架构图会让后续 plan 全盘错位。

## 步骤

1. **判断是否最新**
   - 若 `{ARCH_DIR}/ARCHITECTURE.md` 不存在 → 直接进入"重建"。
   - 若存在 → 对比近期 git 改动与当前代码现状，判断文档是否过期（模块是否已增删、依赖是否变化、关键流程是否改动）。

2. **重建 / 更新 ARCHITECTURE.md**（仅在过期或缺失时）
   - 调研当前代码架构：模块划分、调用链、数据流、外部依赖、关键约束。
   - 对每个架构单元做体检：职责是否单一、边界是否清晰、有无明显技术债。
   - 写出 `{ARCH_DIR}/ARCHITECTURE.md`。

3. **建立目录说明与索引**
   - 生成/更新 `{ARCH_DIR}/index.md`，说明该文件夹的作用与内含文档清单。
   - 检查根 `README`：若未引用 `{ARCH_DIR}/index.md`，把该文件夹的作用补进 README。

4. **子代理挑战**
   - 派 `{CHALLENGER_ENGINE}` 子代理，用 `prompts/architecture-challenger.md` 作为提示词，挑战 ARCHITECTURE.md 的准确性与完整性。
   - 根据挑战结果回填修正。

## 出口

- ARCHITECTURE.md 通过子代理挑战、index.md 与 README 已同步 → 进入 phase-1。
- 架构调研发现与 `{ACCEPTANCE_FILE}` 范围严重冲突（需求技术上不可行）→ 标记 BLOCKED 升级。
