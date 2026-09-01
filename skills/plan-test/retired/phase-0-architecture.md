# Phase 0 — 架构基线

**目的**：确保 `{ARCH_DIR}/ARCHITECTURE.md` 反映当前代码的真实架构，作为写 plan 的依据。陈旧的架构图会让后续 plan 全盘错位。

## 步骤

1. **判断是否最新（用校准锚点，别通读全仓）**
   - 若 `{ARCH_DIR}/ARCHITECTURE.md` 不存在 → 直接进入"全量重建"。
   - 若存在 → 读文档头部的校准锚点 `<!-- last-calibrated: <commit-hash> -->`：
     - 有锚点 → `git diff --stat <hash>..HEAD` 圈出自上次校准以来改动过的目录/模块，**只有这些章节需要核对与更新**；无改动则文档即最新，跳到步骤 3。
     - 无锚点（旧版文档）→ 按近期 git 改动抽查判断是否过期，本次更新时补上锚点。

2. **重建 / 增量更新 ARCHITECTURE.md**（仅在过期或缺失时）
   - **增量更新（默认）**：文档按模块分节维护；只重写 diff 涉及的章节，未受影响的章节不动。
   - **全量重建（仅两种情况）**：文档缺失，或 diff 显示结构性变化（模块增删、依赖方向反转）波及大半章节。
   - 调研纪律遵循 `methods/research-method.md`：论断附代码证据；对本次需求最相关的模块解剖麻雀（挖穿一条典型调用链），其余模块保持概览深度即可。
   - 对本次更新涉及的架构单元做体检：职责是否单一、边界是否清晰、有无明显技术债。
   - 写出/更新 `{ARCH_DIR}/ARCHITECTURE.md`，**头部写入 `<!-- last-calibrated: <当前 commit-hash> -->`**。

3. **建立目录说明与索引**
   - 生成/更新 `{ARCH_DIR}/index.md`，说明该文件夹的作用与内含文档清单。
   - 检查根 `README`：若未引用 `{ARCH_DIR}/index.md`，把该文件夹的作用补进 README。

4. **子代理挑战**
   - 派 `{CHALLENGER_ENGINE}` 子代理，用 `prompts/architecture-challenger.md` 作为提示词，挑战 ARCHITECTURE.md 的准确性与完整性。
   - 按 SKILL.md"上下文包"规则派发：附上本次更新的章节清单与 diff 涉及的文件列表，声明挑战重点是**本次更新的章节**（增量更新时未动的章节抽查即可，不必全文重审）。
   - 以输出末行 `VERDICT` 判定：FAIL → 回填修正后复审；PASS → 通过。

## 出口

- ARCHITECTURE.md 通过子代理挑战、index.md 与 README 已同步 → 进入 phase-1。
- 架构调研发现与 `{ACCEPTANCE_FILE}` 范围严重冲突（需求技术上不可行）→ 标记 BLOCKED 升级。
