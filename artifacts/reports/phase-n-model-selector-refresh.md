# 会话模型列表刷新（2026-09-27）

## 原因与改动

聊天页独立缓存模型列表。此前仅在缓存为空时请求 `/api/v1/models`；先打开会话、后在设置页新增本地模型，再返回会话时，旧缓存仍只含 DeepSeek。模型菜单本身也不触发刷新。后端模型列表及会话切换接口已有实现。

现在每次载入会话及打开模型菜单都会重新读取模型。并发请求只应用最后发起的结果；网络刷新失败时保留上次成功的列表。回归测试从“已缓存 DeepSeek”开始，验证菜单读到新增的本地千问，并向会话切换接口提交本地模型 ID。

## 验证

| 命令 | 结果 |
| --- | --- |
| `npm run test:run -- tests/model-selector.test.ts`（frontend） | 1 passed，exit 0 |
| `npm run test:run`（frontend） | 50 passed，exit 0；旧 ModelsPage 测试有 RouterLink 注册警告 |
| `npm run build`（frontend） | TypeScript 检查和 Vite 生产构建成功，exit 0 |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/package-windows.ps1 -SkipTests -SkipInstaller -ReleaseDirectory 'artifacts\build\model-selector-stage'` | exit 0；冻结诊断、worker 冒烟、便携 ZIP 和元数据成功 |

用户关闭旧程序后，已将新包覆盖到 `artifacts/release-agent-chat/Guixu-0.1.0/Guixu.exe` 和同目录 ZIP。覆盖后哈希与暂存包一致：EXE SHA-256 `3161EA3391B7B26FAA9B5C3A8039E5CE2637F81E18DF2E9FF1846DED77211165`；ZIP SHA-256 `A4157D9962289633A0D13A970A107121020BCC524041C38838632BA8E8B6A995`。旧版 onedir 临时备份在 `artifacts/build/model-selector-stage/previous-Guixu-0.1.0`；自动审查阻止本轮直接递归删除，尚未清理该备份。

未在用户照片目录执行整理或调用本地模型；真实本地模型对话尚未验证。发布判定沿用 NOT RELEASE READY。
