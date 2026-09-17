# testcase 资产与复用生命周期
选用/新建/维护 testcase 时读。
- 事实源＝testcase Markdown frontmatter；`index.json`/`index.md` 是生成视图，仅导航，绝非 PASS/FAIL 依据。
- 无 frontmatter 的旧用例：以 `LEGACY-*` + `needs-review` 入索引，补元数据前不可选用。
- frontmatter 最少含 `id purpose status surface type obligations tags entrypoint revision`。
- status 仅 `active|needs-review|retired|superseded`；后两者留仓、须指向有效 `replacement`，新 run 不可选。

1. 设计前 `testcase_inventory.py build --testcase-dir <dir>` 重建两份索引。
2. 按 obligation/surface/entrypoint/tags 查 active 候选，决定前读完其步骤与预期。
3. 每条 required obligation 恰记一个决定：`reuse-as-is|reuse-with-extension|supersede|create-new`；后三者写具体理由；新用例须先入索引，reuse report 才能过校验。
4. 冻结所选 revision 并在当前 run 执行，实际结果存 oracle 文件之外；历史 PASS 永不替代本次执行。
5. 执行后更新生命周期元数据并重建索引。
6. `testcase_inventory.py validate` 校验路径、ID、替换链、复用决定、required obligation 覆盖、testcase lock。
