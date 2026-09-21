# AI-only PHASE 9：全量回归与完整闭环

日期：2026-09-19  
状态：PASSED

## 完成

- 旧的 `universal.types`、无模型任务和规则 API 集成测试已迁移为 AI-only 契约；没有删除安全、执行、解析或可靠性核心测试。
- 新增 10 文件完整临时目录闭环：scan → parse → AI planner → taxonomy approve → AI batch classify → review → compile → approve → execute。
- 十个同为 `.txt` 的文件依据正文课程语义分别进入“计算机网络”和“操作系统”，磁盘目标、plan、journal 与 task history 一致。
- 新增批准后外部修改源文件测试：执行返回 operation `SOURCE_CHANGED`，保留源文件且不生成目标文件。
- 模板 UI 自动化实际点击 `image.scene`、打开详情、点击“使用此模板”，验证路由携带准确 `template_key`。
- 运行时 OpenAPI 快照已重新生成，包含 taxonomy 编辑和分类重试接口。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q`：退出 0，133 passed，2 warnings。
- warnings：Starlette TestClient 弃用提示；Pillow 解压炸弹边界测试的预期 warning。测试结束另有 Windows pytest 临时 reparse-point 清理 warning，不影响断言结果。
- `npm run test:run -- --reporter=dot`：退出 0，14 passed。
- `npm run typecheck`：退出 0。
- 10 文件完整闭环定向测试及安全执行 API：5 passed（1 个第三方 warning）。

## 真实性说明

- Planner/Classifier 完整闭环使用明确标识的测试 fake AI，仅证明编排、契约、安全执行与审计链路，不代表真实 DeepSeek/Qwen 的语义质量。
- 所有磁盘操作仅发生在 pytest 临时目录。
