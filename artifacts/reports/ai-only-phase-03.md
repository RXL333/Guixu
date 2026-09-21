# AI-only PHASE 3：统一 FileProfile

日期：2026-09-15  
状态：PASSED

## 完成

- FileProfile 增加 `source_path`、`name`、`extension`、`mime_type`、`parser_status`、`parser_warnings`。
- ParserRegistry、独立 worker、内存/磁盘缓存命中均重新绑定当前文件上下文，避免内容缓存泄漏首个文件的 path/file ID。
- 路径和格式字段仅作为本地上下文；现有 outbound envelope 不发送 source path/name/extension/MIME。
- FileProfile JSON Schema 与前端类型同步。
- Parser 测试新增字段完整性、状态一致性与 schema 断言。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q tests/parsers tests/models/test_models.py`：退出 0，19 passed，1 个 Pillow 解压炸弹阈值 warning。
- `npm run test:run -- --reporter=dot`：退出 0，12 passed。
- `npm run typecheck`：首次因前端测试 fixture 缺新字段退出 1；修复 fixture 后退出 0。

## 未完成 / 后续

- 视觉描述 evidence 仍需由 vision-capable AI 产生；本阶段没有把 OCR/尺寸冒充视觉理解。
- FileProfile schema 仍保持 v1 以兼容旧缓存，新增字段已成为当前序列化必填字段。
