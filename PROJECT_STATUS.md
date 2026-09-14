# 项目状态

版本：0.1.0 dev（九阶段实现完成，发布门仍有外部阻塞）。更新时间：2026-09-14。

**阶段 01～09 的源码、安全闭环、执行器、本地解析、分类、双模型隐私适配、完整界面、恢复、发布前验收与 Windows onedir/portable 已实现；ffmpeg/ASR、真实模型、Inno 安装器与干净 Windows 发行矩阵仍有外部补证项。**

| 阶段 | 内容 | 状态 | 验收报告 |
|---|---|---|---|
| 01 | 桌面骨架与只读扫描闭环 | BLOCKED_EXTERNAL（自动化通过，DT01待人工桌面补证） | [phase-01](artifacts/reports/phase-01.md) |
| 02 | 安全执行器、日志、复制、移动、撤销 | BLOCKED_EXTERNAL（核心通过；卷断开/云占位待专用环境） | [phase-02](artifacts/reports/phase-02.md) |
| 03 | 多模态本地解析与资源管理 | BLOCKED_EXTERNAL（核心与OCR通过；ffmpeg/ASR待组件） | [phase-03](artifacts/reports/phase-03.md) |
| 04 | 模板、规则、目录规划与分类契约 | PASSED | [phase-04](artifacts/reports/phase-04.md) |
| 05 | DeepSeek／Qwen 模型适配、隐私与预算 | BLOCKED_EXTERNAL（AI04～AI12通过；AI01～AI03待用户服务） | [phase-05](artifacts/reports/phase-05.md) |
| 06 | 全页面与审阅交互集成 | BLOCKED_EXTERNAL（UI01～UI10自动化／浏览器通过；pywebview待人工补证） | [phase-06](artifacts/reports/phase-06.md) |
| 07 | 任务恢复、缓存、纠错、完整工作流 | PASSED | [phase-07](artifacts/reports/phase-07.md) |
| 08 | 质量验证、安全、性能与真实模型评测 | BLOCKED_EXTERNAL（自动化/性能通过；真实模型与桌面等待外部条件） | [phase-08](artifacts/reports/phase-08.md) |
| 09 | Windows 打包、安装、离线资源与交付 | BLOCKED_EXTERNAL（onedir/portable/原生窗口通过；Inno/签名/干净机待外部条件） | [phase-09](artifacts/reports/phase-09.md) |

## 执行者后续维护格式

每次更新写明当前阶段、完成的验收项、失败项、外部阻塞、最后一次测试命令与退出结果、下一项可执行工作。阶段可以是 IN_PROGRESS、PASSED、BLOCKED_EXTERNAL、FAILED；不能为了显示完成而把外部联调标成 PASSED。

## 当前恢复点

- 当前阶段：九阶段实现已收口；版本保持 dev，发布门等待外部补证。
- 最近通过：维护回归后端全量 121 passed、前端 11 passed/typecheck/build、`python scripts/verify.py all` 退出 0；计划批准支持同 ID/同 hash 幂等重试，模型连接支持确认删除并从可用列表移除；Windows onedir 已重建为 434 文件/301,371,902 bytes，冻结诊断与中文 worker exit 0。详见 [maintenance-2026-09-14](artifacts/reports/maintenance-2026-09-14.md)。
- 已交付：`artifacts/release/Guixu-0.1.0/`、`Guixu-portable-x64-0.1.0.zip`、SBOM、SHA256SUMS、锁文件、迁移、源码、脚本、用户/开发手册和九份阶段报告。
- 外部阻塞：Inno Setup/安装器、代码签名、无 Python/Node 干净机安装升级卸载、高 DPI/多系统；真实 DeepSeek/Qwen、公平语义评测、ffmpeg/ffprobe/ASR、物理卷断开／云占位；生产 `direct_move` 仍关闭。
- 恢复动作：在受控构建机安装 Inno Setup 6 后运行 `.\scripts\package-windows.ps1`；按 `artifacts/reports/release-readiness.md` 的阻塞清单补证，全部通过前不得改为 beta/release。
