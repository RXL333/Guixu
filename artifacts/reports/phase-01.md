# 阶段 01 验收报告：基础、桌面骨架与只读扫描

日期：2026-09-13  
环境：Windows 11 x64；Python 3.12.10；Node.js 24.11.1；npm 11.6.2；uv 0.12.1

## 结论

阶段 01 的源码与自动化出口已完成：FastAPI/SQLite/Alembic 后端、pywebview EdgeChromium 桌面入口、Vue 3 工作台、内存会话令牌、目录 grant、三种只读扫描模式、T24 纯类型模板、report_only 报告和真实 API 页面均已落地。文件移动、复制、真实模型和解析器按阶段边界保持 unavailable / not_implemented。

自动化状态为 **PASSED_WITH_EXTERNAL_GAP**。DT01 原生目录选择器尚缺可自动操控 Windows 原生弹窗的测试通道，故不宣称该项通过；浏览器开发路径只验证了同一授权注册逻辑，不能替代 pywebview 原生选择器实测。该外部缺口不阻塞阶段 02 的临时目录安全执行器开发。

## 已完成与证据

- FS01：current_only、recursive、preserve_top_level 的精确集合测试通过。
- FS02/FS03：保护一级区域与 root_loose 隔离测试通过。
- FS04：区域下 1/2/3 级设置边界测试通过；路径编译在阶段 02 验收。
- FS05：输出目录排除测试通过。
- FS06：中文、Unicode、大小写扩展名与保留名片段测试通过。
- FS07：Windows junction/reparse 不跟随测试通过。
- FS08：疑似项目目录整棵跳过测试通过。
- OP01：扫描前后测试目录文件 SHA-256 清单不变，且未创建分类目录。
- UI01：前端不维护独立默认对象；新建表单从 GET /settings 读取 `seed/default-settings.json`，浏览器真实流程通过。
- DT02：单实例锁、Host/Origin/会话令牌限制通过自动测试；服务只绑定 127.0.0.1 随机端口的实现已落地。
- SQLite 使用 foreign_keys=ON、WAL、busy_timeout=5000、synchronous=FULL；初始 Alembic 迁移在独立临时库创建契约表成功。
- 浏览器流程实际授权并扫描 `artifacts/test-workspaces/phase-01-sample`，显示 3 个真实文件、3 个可识别、0 个执行。

## 执行命令与结果

| 命令 | 退出结果 |
|---|---:|
| `uv run pytest -q`（backend） | 0；22 passed |
| `python scripts/verify.py unit` | 0；6 passed |
| `python scripts/verify.py ui` | 0；typecheck、1 Vitest、Vite build 全部通过 |
| `npm run build` | 0；1686 modules transformed |
| Playwright CLI：空态 → 新建 → grant → 扫描 → 报告 | 成功；网络请求 200/201/202 |

唯一仍存在的测试告警来自 Starlette TestClient 对 anyio 旧别名的依赖告警，不影响运行结果。npm 安装报告当前 Node 24.11.1 低于少数间接工具声明的 24.15.0 下限；实际 typecheck/test/build 均成功。发布基线仍按设计要求使用 Node 22.12+ 的 22.x 线复验。

## 产物

- Python 锁：`backend/uv.lock`
- npm 锁：`frontend/package-lock.json`
- 初始迁移：`backend/migrations/versions/0001_initial.py`
- 验证入口：`scripts/verify.py`
- 启动入口：`scripts/run-dev.ps1`、`scripts/run-desktop.ps1`
- 样本生成：`scripts/create-sample-data.ps1`
- UI 截图：
  - `output/playwright/phase-01-scan-1024.png`
  - `output/playwright/phase-01-scan-1280.png`
  - `output/playwright/phase-01-scan-1440.png`

## 外部阻塞与未实现项

- DT01：缺少可操控 pywebview 原生文件夹弹窗的自动化通道，标记 BLOCKED_EXTERNAL；需要人工桌面冒烟或 Windows UI 自动化环境补证。
- Windows EXE、干净机、WebView2 缺失路径均属于阶段 09，不在本阶段宣称通过。
- 文件操作、解析器、模型连接和后续完整页面均明确未实现，按阶段 02～09 推进。

## 下一恢复点

读取 `prompts/codex/02_SAFE_OPERATIONS.md`、`docs/08_SAFETY.md` 和执行契约，开始 PlanCompiler、plan_hash、no-clobber、持久日志、恢复与撤销；全部文件操作仍只使用临时目录或 `artifacts/test-workspaces`。

