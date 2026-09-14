# 阶段01｜基础与只读闭环

```text
/goal 完成归序Guixu的阶段01：建立真实可运行的Windows桌面/本地Web开发骨架、授权目录扫描与纯规则只读预览，不实现真实移动，不调用真实云模型。

先读AGENTS.md、PROJECT_STATUS.md、docs/00_BLUEPRINT.md、01_PRODUCT_SPEC.md、02_ARCHITECTURE.md、06_UI_SPEC.md、07_API.md、09_TESTING.md及contracts、seed中本阶段需要的契约。查看既有工程，保护已有改动。

创建Python3.12工程、Vue3/TypeScript/Vite工程、依赖锁文件、FastAPI本地API、pywebview桌面入口、SQLite/Alembic初始迁移和数据目录。按设计分domain/application/infrastructure/interfaces，不把所有逻辑堆在app.py。阶段01即可建立完整表结构，但未实现的功能明确不可用。

实现loopback端口与会话鉴权、原生目录grant、单实例、退出流程、worker入口预留；建立任务状态机与只读文件扫描：当前目录、递归、保留顶层目录。正确处理root_loose、输出排除、项目/系统/重解析点保护。扫描不全量hash巨型文件，不修改任何源文件。

导入默认设置和T24类型模板，实现无需Key的真实元数据列表与report_only分类预览。页面完成主题壳、工作台、新建任务、扫描列表、空态和错误态；扫描数据必须来自真实测试目录，不能内置静态文件数组假装功能完成。其余页面可显示明确“尚未实现”，不可伪成功。

建立scripts/verify.py分范围验证入口与前端typecheck/test/build。运行FS01～FS08、OP01、UI01；有Windows时运行DT01/DT02，缺失则记录BLOCKED_EXTERNAL。API无会话请求被拒绝，grant之外的路径不可访问；刷新列表不改变磁盘。

输出artifacts/reports/phase-01.md，包含运行命令、结果、截图和外部阻塞；更新PROJECT_STATUS.md。完成条件是能从UI选测试目录、扫描、看到可解释类型建议与报告，源文件清单和hash保持不变。不要提前实现AI或绕过安全的移动功能。
```
