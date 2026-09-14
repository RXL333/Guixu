# 维护验收报告：计划批准重试与模型连接删除

日期：2026-09-14  
范围：截图中的 `PLAN_STALE` 执行错误、模型连接删除入口、Windows 便携包重建。

## 结论

两项修改均已完成并通过受影响测试与全量回归。测试仅使用 pytest 临时目录、jsdom 和项目 `artifacts/test-workspaces`，未访问或移动截图中的真实个人文件。

## 根因与修复

- 计划错误：批准接口只接受 `validated` 状态。若批准已成功但后续请求中断或发生重复点击，再次批准同一 plan/hash 会返回 `PLAN_STALE`，导致安全执行无法恢复。
- 修复：同一 plan ID、同一 hash 且状态为 `approved/executing/finished` 时，批准成为幂等成功；错误 hash、`superseded` 等状态仍拒绝。前端执行前刷新 task revision，并用同步 busy 门阻止重复点击。撤销执行采用相同处理。
- 模型删除：后端已有 DELETE 停用语义，但前端未接入，且模型列表会继续返回已停用行。
- 修复：新增带 revision 的 DELETE 调用和二次确认；列表只显示 enabled 连接。数据库保留 disabled 行和历史引用，符合审计规则，不做破坏性物理删除。

## 测试与结果

| 命令 | 结果 |
|---|---|
| `pytest backend/tests/integration/test_safe_operations_api.py backend/tests/models/test_models.py -q` | 0；9 passed |
| 首次新增模型 DELETE API 用例 | 1；测试应用未开启显式 testserver 门，创建请求被 `HOST_REJECTED`，删除逻辑未执行 |
| 修正测试夹具后相关后端用例 | 0；13 passed |
| `npm run typecheck` | 0 |
| `npm run test:run` | 0；11 passed（含真实组件确认/删除交互） |
| `npm run build` | 0；1714 modules transformed |
| `python scripts/verify.py all` | 0；所有范围通过 |
| `pytest backend/tests -q` | 0；121 passed，2 个已知 warning |
| `scripts/package-windows.ps1 -SkipTests` | 0；onedir、冻结诊断、中文 worker、portable ZIP、SBOM/hash 生成通过；Inno Setup 仍为外部阻塞 |
| `python tools/validate_blueprint.py` | 1；Windows 默认 GBK 无法读取 UTF-8 schema |
| `python -X utf8 tools/validate_blueprint.py` | 1；该旧设计包检查器递归扫描已安装的 `node_modules`、`.venv` 与打包副本，报告 178 个第三方 JSONC/文档链接等非应用检查失败；未作为本次代码验收通过项 |

## 产物

- `artifacts/release/Guixu-0.1.0/`：434 文件，301,371,902 bytes。
- `artifacts/release/Guixu-0.1.0/Guixu.exe`：SHA-256 `A9C412C780DC65A569B738D5B6A1A7439F0C848400A385C9280047BFD4D45FC2`。
- `artifacts/release/Guixu-portable-x64-0.1.0.zip`：144,071,149 bytes；SHA-256 `77E6216B64294E048ED927C9E997CC7428259B9284A7BFD10FB39FC19D2EC393`。

## 保留阻塞

没有 Inno Setup 6，因此未生成安装器；签名、干净 Windows 矩阵、真实 DeepSeek/Qwen 与外部媒体组件状态不变，不能标为公共发布版。
