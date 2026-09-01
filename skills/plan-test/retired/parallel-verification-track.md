# 并行验证准备轨清单（phase-3 D 节）

与实现轨（phase-3 A）并行执行；全部勾完才到汇合闸。**black-box 纪律**（只准读 acceptance /
plan / 行为契约 / 既有公开接口文档，禁止读实现代码、diff、执行子代理中间产物）全文见 phase-3 D 节。

## 必做项

- [ ] **项目 testcase 目录已发现**：先读 `{TESTCASE_DIR}/index.md` 和 `index.json`；缺失时用
      `scripts/testcase_inventory.py build --testcase-dir {TESTCASE_DIR}` 从现有文件生成，legacy
      用例先登记为 `needs-review`，不得假装不存在
- [ ] **候选原文已审查**：按 obligation 查询 inventory，并逐个阅读候选 testcase 全文，确认
      当前入口、fixture、步骤、预期与 revision 有效；不能只凭 index 摘要决定复用
- [ ] **reuse report 已通过校验**：每条 obligation 是 `reuse-as-is / reuse-with-extension /
      supersede / create-new` 之一；`create-new` 写明增量价值，复用不继承历史 PASS
- [ ] **black-box testcase 编写完成**：每条 required AC 至少一个分步用例，每步含预期结果；
      优先复用/扩展已有资产，仅必要的新用例存放 `{TESTCASE_DIR}/<组>/`，同步 index.md/index.json
- [ ] **testcase challenger 迭代定稿**：`prompts/testcase-iterator.md`，最少
      `{TESTCASE_ITERATIONS}` 轮，末行 VERDICT: PASS
- [ ] **verification spec 可编译**：acceptance → obligation → selected testcase → scenario 双向
      覆盖完整，`compile-manifest` 成功并冻结 `case_sets.full`
- [ ] **场景矩阵草案**：scenario_id / testcase_ids / evidence_contract / required / ui / gate_type / required_lanes /
      min_root_runs / input_class / cold_start / expected_run_created
- [ ] **impact_paths 映射草案**：每个场景关联的代码路径 glob（宁缺勿滥——声明不了就留空，
      fail-closed 会退回全量复测，错误的映射比没有映射更危险）
- [ ] **applicability 三维判定草案**：input_sensitive / llm_payload_driven / stateful_init
      各附 ≥10 字理由与 decided_by
- [ ] **fixture / 种子数据 / 环境准备脚本**：起服务、造数据、隔离 user-data 目录、
      测后清理；冷路径场景的"全新安装→首次登录"准备物
- [ ] **分级冒烟脚本**（`FULL_SURFACE_SMOKE`）：按 config 的当前路径圈定范围；范围内每个入口
      各一枪，存盘可复跑
- [ ] **核心价值 smoke 输入清单**（输入敏感功能）：2–5 个自然语言正向问题
- [ ] **大仓分片清单**（适用时）：`baseline-shards.json` 已建/已更新，供回归比对复用

## 汇合闸（与实现轨对齐后才过）

- [ ] 实现轨 A/A2/B/C 全部收尾（完成度审计 100% + 无新增回归）
- [ ] 本清单全勾
- [ ] → phase-4：核对 + `testcase_lock` 冻结 + gate init（manifest 用本轨草案填充），
      然后便宜门序 → 昂贵真人测试

## 时间入账

- 本轨自身的工作用 `record-timing`（gate init 前的时段在 init 后用申报模式补记，
  或先在 plan 文件夹记 markdown 时间线、init 后统一申报入账）；两轨并行的墙钟收益
  要能在 report 的耗时分解里看得见，否则下次没人知道并行有没有真的发生。
