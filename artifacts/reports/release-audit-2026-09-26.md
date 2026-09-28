# 发布复核：2026-09-26

结论：**NOT RELEASE READY**。本轮没有发布、打标签或推送；测试目标是当前 `0.1.0` Windows onedir/便携 ZIP，而不是尚未构建的 `1.0.0 RC1`。所有文件操作测试均在仓库测试夹或临时目录进行，没有整理用户照片。

## 本轮已验证

| 范围 | 命令或实际操作 | 结果 |
|---|---|---|
| 后端全量 | `cd backend; uv run pytest -q --disable-warnings` | exit 0；218 passed，2 warnings；另有 Windows pytest 临时目录清理提示。日志：`release-backend-full-2026-09-26.log` |
| 分域回归与前端 | `python scripts/verify.py all` | exit 0；unit/contract 8、safety/integration 157、parsers 19、classification 22、models 25、reliability 10、quality 12，各分域有重复用例；前端 47 passed，typecheck 和 production build 通过。日志：`release-verify-2026-09-26.log` |
| 真实模型与文件安全链 | `uv run --project backend python scripts/run_phase_n_real_e2e.py` | exit 0；5 张合成 JPG，真实 DeepSeek 生成 v1、按新要求生成 v2/diff、审批前源文件 hash 不变，显式审批后执行完成，重启读回 5 条消息、2 个方案、1 次执行、5 个文件引用；8 次模型调用记录均为 ok。报告：`phase-n-real-deepseek-e2e.json`；日志：`release-real-model-2026-09-26.log` |
| 冻结包桌面 | 启动 `artifacts/release-agent-chat/Guixu-0.1.0/Guixu.exe`，设置 `GUIXU_TEST_MODE=1` 与独立 `GUIXU_TEST_DATA_DIR` | 本机 WebView2 下能新建授权目录会话，右侧显示 2 个文本文件；关闭再启动后会话和 2 个文件恢复。另新建会话扫描 3 个测试文件，合成 JPG 预览成功，Escape 关闭。测试数据：`artifacts/test-workspaces/release-desktop-2026-09-26/` 与 `release-desktop-fixture-2026-09-26/` |
| 冻结包真实普通聊天 | 在隔离数据库复用已验证 DeepSeek 模型档案；“先聊、不生成方案”后继续发送“按内容分类、文件夹名称用中文” | 两轮均获实际 AI 回复，第二轮正确复述要求；数据库为 4 条消息、0 个方案、0 次执行、0 条操作，证明普通发言不会自动整理。选中合成 JPG 后出现明确的“发送到 DeepSeek 云端”确认弹窗；本轮取消，UI 图片上传后的回复未验收 |
| 冻结诊断 | EXE `--diagnose`，独立 `GUIXU_DIAGNOSTIC_DATA_DIR` | exit 0；`diagnostics.json` 记录 frozen=true、前端资源存在、SQLite 位于安装目录外、本机 WebView2 153.0.4234.48 |
| 包内容 | `python scripts/audit_release_secrets.py` 检查 onedir 与 ZIP | exit 0；各 435 个文件、301,991,192 解压字节；开发资产路径与已知密钥签名均 0 命中。仅覆盖脚本已知模式 |
| 包完整性 | 对 `SHA256SUMS.txt` 逐条重新计算 SHA-256 | 437/437 匹配，0 缺失或不一致 |
| 大目录后端 | 500、1000、5000 文件隔离重测 | 独立运行时 scan 0.094/0.228/0.963 秒，attach 0.346/0.681/3.766 秒，reconcile 0.339/0.679/3.570 秒；SQLite integrity 均 ok。并发运行时 5000 attach 曾达 19.875 秒；未测 UI 5000 项渲染。日志：`release-performance-isolated-2026-09-26.log`、`release-performance-2026-09-26.log` |
| 文档 | `python scripts/check_document_links.py` | exit 0；27 份文档、0 断链 |

## 阻断正式上线的事项

1. **安装和发行环境未验收**：本机无 Inno Setup 6，未生成或安装 Setup；没有干净 Windows 虚拟机/主机完成首次启动、升级、卸载、中文路径、不同 DPI 验收。EXE 的 `Get-AuthenticodeSignature` 为 `NotSigned`，仓库没有公开许可证文件。当前包是 `0.1.0`，不是 `1.0.0 RC1`。
2. **发行包完整业务链未验收**：真实 DeepSeek 的 v1→v2→审批→执行→重启链在源码集成测试通过；本机冻结包验证了两轮普通聊天、会话、目录列表、图片预览和重启读取。冻结包中生成方案后的实际模型整理、继续 refinement、Undo、恢复组合仍缺证据（C17 等）。
3. **安全与异常矩阵尚不完整**：参见 `docs/current/deployment/RELEASE_ACCEPTANCE.md` 的 S01-S17、D01-D12。特别是跨授权/重解析组合、SQLite 意外关闭和并发、真实旧库迁移、真实 429/401/取消请求、发行态凭据与日志检查尚未完成；不能把单次成功 E2E 当作稳定性证明。
4. **规模和界面矩阵尚不完整**：未测 5000 项真实桌面渲染、100/300/500 条消息、125%/150% DPI、1280/1366/1440 多状态及完整键盘/可访问性。5000 文件 attach 在独立运行约 3.8 秒、并发负载约 19.9 秒，建议为首次挂接增加进度反馈并做基准阈值与并发复测。
5. **模态与样本覆盖不足**：PDF/Office 的实际分类验收未完成；图像和文本只有部分样本链。真实用户照片未用于本轮云端测试或整理。
6. **新登记的 P2-003**：冻结包普通聊天实际成功 2 次，但 `model_calls` 仍为 0。聊天接口绕过模型调用 ledger，费用/用量、时延与错误审计缺失；修复建议见缺陷登记。图片发送确认弹窗已验证，实际通过弹窗发送合成 JPG 未执行。
7. **新登记的 P3-001**：真实 AI 回复的 Markdown 强调与列表标记直接显示，长回复可读性较差；需要安全的受限富文本渲染。

## 达到发布门槛的下一步

先完成冻结包真实模型全链和故障恢复；再补安全、取消请求、旧库迁移与大目录 UI/DPI 验收。安装 Inno Setup 6 后构建 `1.0.0 RC1` 并在干净 Windows 上安装、升级、卸载测试；确定公开许可证与签名/未签名发行策略。所有阻断项有直接证据通过后，按 release acceptance 的规则重新作 `RELEASE_READY` 判定。
