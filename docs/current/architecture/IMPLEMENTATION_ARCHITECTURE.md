# 实现架构快照（0.1.0 dev）

本文件是早期实现快照；当前阶段、数据库版本和已删除功能以 `PROJECT_STATUS.md` 与代码为准。历史设计基线见 `docs/archive/historical-designs/blueprint/`。

```text
Guixu.exe (pywebview / EdgeChromium)
  ├─ FastAPI 127.0.0.1:随机端口 + 随机会话 token
  ├─ Vue 3 静态资源（冻结包 _internal/frontend/dist）
  ├─ TaskCoordinator（单文件执行锁、检查点、暂停/恢复/取消）
  ├─ Scanner / ParserRunner / AI Planner / ModelGateway
  │    └─ 冻结时 Guixu.exe --worker（不启动 GUI）
  ├─ Safe executor（计划 hash、no-clobber、跨卷 copy-verify-publish-delete）
  └─ %LOCALAPPDATA%\Guixu
       ├─ app.sqlite3 + WAL / backups
       ├─ cache/profiles
       └─ components（用户显式导入、manifest/hash 校验）
```

AI 适配器只能返回结构化 category ID、证据 ID、置信度与弃判；taxonomy、路径规划和文件执行分别由确定性域层完成。用户授权根只在进程内注册，REST 不能用任意字符串扩大文件访问。

数据库当前 schema version 为 11，参考 DDL 在 `contracts/database.sql`，迁移位于 `backend/migrations/versions/`。新于程序的版本阻止启动，旧库升级必须先生成 SQLite backup。

`contracts/openapi.json` 是原设计初始契约，未覆盖它；`contracts/openapi-runtime.json` 由当前 FastAPI 应用生成，是已实现路由和 schema 的机器可读快照。路由使用 `/api/v1` 前缀。
