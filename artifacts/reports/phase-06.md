# 阶段 06 验收报告：完整界面与审阅交互

日期：2026-09-14  
环境：Windows 11 x64；Vue 3 + TypeScript；Chromium 浏览器集成验证；本地 FastAPI/SQLite

## 结论

阶段 06 的前端组件、真实 API 页面和浏览器工作流 **PASS**；阶段总体标记 **BLOCKED_EXTERNAL**，因为浏览器验证不能替代 pywebview 桌面窗口、WebView2 和高 DPI 原生验收。整个验证仅操作 `artifacts/test-workspaces`，没有执行文件移动或复制。

已实现六步任务流程、三栏审阅、真实计划双路径、证据抽屉、执行 hash 确认、真实报告、模板／规则／历史／模型／设置页面，并补齐 `AppShell`、`SourcePicker`、`ScopeBoundaryPreview`、`TemplatePicker`、`PolicyEditor`、`PrivacyPreview`、`CapabilityBadges`、`TaxonomyTree`、`FileMappingTable`、`EvidenceDrawer`、`ExecutionBar`、`ConflictDialog`、`TaskTimeline` 和 `UndoPreview` 等可复用组件。页面不使用假成功数据，能力缺失显示 unavailable／blocked。

## UI01～UI10

| 编号 | 结果 | 证据 |
|---|---|---|
| UI01 | PASS | 新建任务从 `/settings`、`/templates`、`/models` 获取默认值和可用连接 |
| UI02 | PASS | preview_move 流程展示后端计划中的原路径和确定性目标路径；计划 hash `2974e4…` |
| UI03 | PASS | 审阅页区分“全选当前页”与“全选筛选结果”，选择集合随筛选更新 |
| UI04 | PASS | TaskStepper 提供可访问阶段名；执行页的确认、忙碌与禁用状态明确 |
| UI05 | PASS | 页面显示等待、空态、失败、模型 unavailable 与预算／连接降级说明 |
| UI06 | PASS_BROWSER | 1024、1280、1440 三种逻辑宽度完成实际截图；高 DPI pywebview 仍待桌面补证 |
| UI07 | PASS | Tab 可达，`aria-current`／dialog 语义存在，Esc 可关闭证据抽屉；危险操作无全局快捷键 |
| UI08 | PASS | 所有要求路由均连接真实 API；report_only 的 executed_count 为 0 |
| UI09 | PASS | 文件名和证据使用 Vue 文本插值；含 `<script>` 的真实测试文件按字面显示 |
| UI10 | PASS | 执行按钮在勾选确认前禁用；批准与执行均绑定 plan_id、完整 plan_hash 和 revision |

## 实际浏览器流程

1. 报告模式任务 `743a92f4-12fe-4291-8711-43922aeb3b85`：扫描 2 个文件，解析、批准分类树、分类、审阅、生成报告；2 个高可信建议，实际执行 0，撤销不可用。
2. 预览移动任务 `fbb17dd1-3147-4792-b39d-97f4ef343f7e`：完成扫描、分类树批准和计划编译，目标为项目测试目录内 `文本/contract.txt`；打开最终确认页后保持确认框未选、执行按钮禁用。
3. 原文件 SHA-256 保持 `20A87…`，批准目标不存在，证明本阶段浏览器验收没有改变文件。

最终截图：

- `output/playwright/phase-06-review-1024.png`
- `output/playwright/phase-06-review-1280.png`
- `output/playwright/phase-06-review-1440.png`
- `output/playwright/phase-06-report.png`
- `output/playwright/phase-06-plan-preview.png`
- `output/playwright/phase-06-execution-confirmation.png`

浏览器首轮暴露 report_only 错误进入计划编译而得到 `TASK_NOT_READY`，已改为分类完成后直接进入报告；最终流程 console 无 warning/error。组件收尾时又由 `vue-tsc` 发现 12 个单行 SFC 的脚本结束符解析错误，已全部格式化修复并复测，未把 Vitest 的局部通过误记为阶段通过。

## 命令与结果

| 命令 | 退出结果 |
|---|---:|
| `python scripts/verify.py ui` | 0；typecheck 通过，8 tests passed，production build 1710 modules |
| `uv run --all-extras pytest -q`（backend） | 0；108 passed，2 个已知 warning |
| Playwright 报告模式与预览移动流程 | 0；最终 console 0 error、0 warning |

## 外部阻塞与恢复点

- DT01、DT03、DT06 与高 DPI：仍需在 pywebview/EdgeChromium 原生窗口中人工验证；浏览器截图不冒充桌面集成证据。
- 阶段 07 将实现统一 TaskCoordinator、暂停／恢复／取消、崩溃恢复、缓存边界、同伴组、报告导出与端到端故障测试。
