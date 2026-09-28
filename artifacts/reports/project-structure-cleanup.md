# 仓库目录整理（2026-09-25）

源文件、测试样本和技术文档已按仓库骨架归类。历史蓝图、提示词、设计稿及旧验证工具保存在 `docs/archive/`；当前文档位于 `docs/current/`、`docs/product/`、`docs/development/`；评测样本位于 `backend/tests/fixtures/evaluation/`，阶段截图位于 `artifacts/reports/ui/`。运行时必需的 `seed/` 保留根目录。

逐文件盘点见 [project-file-inventory.tsv](project-file-inventory.tsv)。其中 20 个生成缩略图和 4 个旧阶段 profile 缓存属于可重建清理候选；此前自动审批拒绝递归删除，现仍保留。发行包、测试依赖、评测原样本和操作证据均未清理。

验证：维护文档链接 0 断链，120 个评测样本哈希一致，`python scripts/verify.py all` exit 0。Windows 包在后续“最近删除清空”修复中已覆盖构建，见 [phase-n-trash-clear.md](phase-n-trash-clear.md)。
