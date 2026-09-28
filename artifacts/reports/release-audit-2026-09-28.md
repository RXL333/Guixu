# 正式上线前全方位验收（2026-09-27 至 09-28）

## 判定

**NOT RELEASE READY。** 当前源码和本机便携包的基本回归通过，真实 DeepSeek 在隔离文件上完成首次整理完整链，打包版的本地千问连续两轮纯聊天及图片预览可用。但打包版本地千问对三张合成 JPG 的首次整理在分类阶段返回 `VISION_DESCRIPTION_MISSING`，没有产生预览方案；此外发行包真实模型整理与恢复全链、干净 Windows、安装器、多 DPI/大列表桌面验收以及签名和许可证发布决策仍缺证据。

本轮没有把用户主动选择测试目录的行为记为异常关闭。个人照片目录未参与模型分析或文件操作；所有涉及模型分类和执行的文件均为隔离样本。

## 基线与环境

- Git HEAD：`f4b9a551233e1eb08d7d79b37e90ee29a7821dd6`；工作树已有大量未提交修改，验收对象是当前工作树与现有 `0.1.0` 包，并非干净提交的 1.0 RC。
- 打包 EXE：`artifacts/release-agent-chat/Guixu-0.1.0/Guixu.exe`，SHA-256 `9C1BD28BFE2A09D0323263CDBCD75D3EA8A282E313D39A6E3B304B47BF045158`。
- 便携 ZIP：`artifacts/release-agent-chat/Guixu-portable-x64-0.1.0.zip`，SHA-256 `B928DC58475284798FDEACCEA7624C11CC0D89E73E91348F24857857F63AC97C`。
- Windows 本机 WebView2 `154.0.4258.37`；Ollama `/api/tags` HTTP 200，已安装 `qwen3-vl:4b-instruct`。本轮未使用干净 Windows VM。

## 实际运行结果

| 检查 | 命令/操作 | 结果 |
|---|---|---|
| 后端完整回归 | `backend\.venv\Scripts\python.exe -m pytest -q` | exit 0，**222 passed**，2 warnings，120.22 s |
| 前端完整回归 | `frontend\npm run test:run` | exit 0，**52 passed / 7 files**；ModelsPage 有 RouterLink 测试环境警告 |
| 类型与生产构建 | `frontend\npm run build` | exit 0；含 `vue-tsc -b`，Vite 产物约 250.44 kB JS |
| 已知开发资产/密钥签名 | `scripts/audit_release_secrets.py` 对 onedir 与 ZIP | exit 0；各 435 项、301,999,673 解压字节；已知特征 0 命中。首次遗漏 CLI 必需参数的调用 exit 1，补齐参数后通过 |
| 文档链接 | `scripts/check_document_links.py` | exit 0；28 份文档，0 断链 |
| ZIP 与清单 | 全部重算 `SHA256SUMS.txt`、ZIP `testzip()` | 437/437 哈希匹配；ZIP 完整性通过 |
| 冻结诊断 | 打包 EXE `--diagnose`，隔离数据目录 | 诊断 JSON `status=ok`、`frozen=true`、前端存在、数据库在安装目录外；该 PowerShell GUI EXE 启动方式未取得可靠 `$LASTEXITCODE`，不记为退出码通过 |
| 真实 DeepSeek 首轮链 | `backend\.venv\Scripts\python.exe scripts\run_phase_n_real_e2e.py` | exit 0，5 张合成 JPG 的 v1→v2/diff→明确批准→Execution #1 完成→重启读回；批准前磁盘不变，6 次模型调用均 `ok`。证据：`phase-n-real-deepseek-e2e.json` |
| 真实 DeepSeek 后续链 | `backend\.venv\Scripts\python.exe scripts\run_post_execution_deepseek_smoke.py`，`GUIXU_SMOKE_OUTPUT=artifacts/test-workspaces/release-postexec-2026-09-27` | exit 0，20 个隔离 JPG；LOCAL 范围 10 个候选、10 条证据复用、0 刷新；DELTA 2 项，Execution #2 完成，范围外 10 个文件不变 |
| 5,001 文件后端基准 | `scripts/run_phase_n_performance.py` 的 `run_size`，独立运行目录 | 首次：scan .382 s、persist .771 s、attach **12.424 s**、reconcile 4.373 s；隔离复测：scan .422 s、persist .616 s、attach **3.922 s**、reconcile 3.813 s、SQLite integrity `ok`、RSS 增量约 67.6 MB。单次冷态波动明显，未取得 p95 或桌面帧率 |
| 打包版原生 UI | 隔离数据库和三张合成 JPG；原生文件夹选择器、文件列表、图片预览 | 新会话正确绑定测试目录，列表 3 项；图片预览实际渲染且 Escape 可关闭。前一次文件夹选择是用户主动协助，不是异常关闭 |
| 打包版本地模型 | UI 保存本地千问档案、测试能力、切换会话模型 | 文本和视觉均显示“已验证”；两轮纯聊天均回答要求，未自动生成方案或移动文件 |
| 打包版本地图片整理 | 在 UI 原生创建的会话中，请求“按图片内容分类，目录全部中文” | **FAIL / P1**：模型规划调用成功，但三图分类批次失败，`task_events` 记录 `AI_CLASSIFY_BATCH_FAILED / VISION_DESCRIPTION_MISSING`。`conversation_plan_versions=0`、`operations=0`，源文件仍是 3 张。连接能力探测不能替代完整分类契约验收 |
| 打包版重启 | 关闭并重新启动同一隔离数据目录 | 同一会话、模型选择、用户要求及 3 张文件列表恢复；失败后仍无虚假 Plan/Execution |
| 签名/发布物 | `Get-AuthenticodeSignature`、`Test-Path LICENSE` | EXE `NotSigned`；仓库根目录无 `LICENSE`。未生成 1.0.0 RC1 |

另：由测试接口在另一个进程预建的会话能显示文件和聊天，但首次方案尝试曾出现“目录授权失效”。由于这不是用户从桌面原生选择文件夹的流程，不将其归因于产品缺陷；随后按真实 UI 流程新建会话并复测，得到了上表可复现的模型契约失败。

## 阻断项与建议

1. **P1：本地千问真实图片整理失败。** `qwen3-vl:4b-instruct` 档案通过文字/视觉能力测试，但三张合成 JPG 的分类响应没有必需的非空 `visual_description`。程序拒绝不完整结果是正确的安全行为；产品目前无法用这组配置完成一次整理。下一步需捕获脱敏的响应结构，确认是否模型遗漏字段、提示词约束不足或修复请求未补字段；增加覆盖该模型的三图“规划→视觉证据→分类→预览”真实回归，并在能力测试中加入契约级探测。失败时 UI 应显示明确错误码及可操作建议。**不可用文件名或臆测文本补造视觉证据。**
2. **发行环境阻断：** 无 Inno Setup 6、干净 Windows 主机/VM、签名证书及许可证决策；目前只验证本机便携包，不能宣称安装器和首次安装体验通过。需生成 1.0 RC、在干净环境执行安装/卸载/首次启动/模型连接/授权目录/重启测试，再核对签名及许可证。
3. **验收覆盖缺口：** 发行包真实模型 v1→v2→批准→执行→重启继续→Undo，目录越界/重解析点/长路径/ACL/多写者与异常退出组合，PDF/Office 实样，500/1,000/5,000 文件 WebView 交互、100–500 条消息、多 DPI/窗口尺寸均未在本轮完整通过。源码单测及隔离脚本不能替代这些发行态场景。
4. **性能波动：** 同机 5,001 文件 attach 本轮两次为 12.424 s 和 3.922 s；先记录冷/热缓存、磁盘与杀软状态并重复测 p50/p95，再判断是否仍有 I/O 串行或锁竞争问题。当前只可说明 SQLite integrity 通过，不可宣称桌面大目录流畅。
5. **既有非阻断缺陷：** `P2-003` 普通聊天模型调用未进入 `model_calls`；`P3-001` Markdown 回复按纯文本显示。见 `guixu-1.0-bug-registry.md`。

## 安全与收尾

- 本轮没有对用户照片目录调用模型或执行移动/重命名/删除；打包版文件操作记录为 0。
- 本机测试用打包应用进程已退出。隔离样本和报告保留以便复现；未 push、tag 或发布。
- 下一次放行检查从 P1 复测开始，之后按 `docs/current/deployment/RELEASE_ACCEPTANCE.md` 补齐所有 gate；在 clean environment PASS 前保持 **NOT RELEASE READY**。
