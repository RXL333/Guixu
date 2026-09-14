# 阶段 08 发布前验收矩阵

日期：2026-09-14  
平台：Windows 11 x64；Python 3.12.10；Node/npm 锁定依赖；Chromium 本地 UI

状态含义：`PASS` 表示本轮有实际自动化或实机证据；`PARTIAL` 表示安全降级已验证但增强组件缺失；`BLOCKED_EXTERNAL` 表示必须依赖用户服务、专用硬件／卷或人工桌面环境；`NOT_RUN` 不视为通过。

| 验收组 | 状态 | 本轮证据 |
|---|---|---|
| FS01～FS14 | PASS | 扫描模式、深度／节点限制、输出排除、项目／系统／reparse 防护、no-clobber、稳定后缀、计划 hash、未知格式、同伴组自动化通过；10,000 文件真实项目测试目录扫描通过 |
| FS15 | PASS | Windows 锁文件不强制移动、只读源可安全复制；真实句柄语义测试通过 |
| OP01～OP03 | PASS | 待确认默认保留、只执行选中项、AI 输出不能提供目标路径或执行权限 |
| OP04 | PASS | 自动检测到 pytest 临时目录与项目目录位于不同 `st_dev`，真实跨卷执行 copy→verify→publish→delete，未 skip |
| OP05～OP07 | PASS | 各提交点恢复、块级取消、暂停／恢复、启动恢复审计、单执行锁 |
| OP08～OP14 | PASS | 撤销外部修改冲突、幂等、目标竞态、源变化、稳定同名、组部分失败；项目测试目录完成移动和反向撤销 |
| PA01～PA06 | PASS | 文本、PDF、Office、图片元信息与 OCR 自动化通过 |
| PA07 | PARTIAL | 音频 metadata 与缺 ASR 时的 `partial` 降级通过；已校验本地 ASR 模型未提供 |
| PA08～PA09 | PARTIAL | 视频无 ffmpeg/ffprobe 时不假成功并弃判通过；真实抽帧／字幕／ASR 未运行 |
| PA10～PA12 | PASS | 损坏签名、解压上限、未知格式、worker 隔离与退出码通过 |
| CL01～CL11 | PASS | 模板树、策略、规则／AI 优先、固定类别、证据与弃判、自然语言编译边界、树／计划版本、人工反馈、缓存隔离通过 |
| AI01～AI03 | BLOCKED_EXTERNAL | 无用户授权的 DeepSeek Key 与 Qwen 推理服务；未运行真实模型正确率／能力比较 |
| AI04～AI12 | PASS | 超时／重试／预算、出站授权、能力探测、JSON 边界、最小上传、凭据脱敏、local-only/LAN 标识自动化通过 |
| UI01～UI05 | PASS | 模板、审阅／证据、批改、部分成功计数、报告浏览器流程通过 |
| UI06 | BLOCKED_EXTERNAL | 响应式 CSS 与浏览器窄屏测试通过；pywebview 原生高 DPI 多显示器仍需人工补证 |
| UI07～UI10 | PASS | 键盘／Escape、报告导出、短期媒体票据、计划 hash 显示与批准闭环通过 |
| DT01 | BLOCKED_EXTERNAL | 浏览器壳完整通过；原生 pywebview 冻结窗口待阶段 09 产物和人工桌面补证 |
| DT02 | PASS | 随机会话 token、Host/Origin 限制、无 token 拒绝、媒体 scoped ticket 与 no-store 响应通过 |
| DT03 | PARTIAL | 启动恢复、进程级崩溃点和持久事件通过；冻结 GUI 强制关闭恢复待阶段 09 |
| DT04 | PASS | worker 独立入口与 `freeze_support` 约束由测试覆盖；冻结产物复验在阶段 09 |
| DT05～DT08 | BLOCKED_EXTERNAL | 无 Python/Node 启动、安装/升级/卸载、WebView2 与多环境兼容需要阶段 09 打包及干净 Windows 用户环境 |
| DT09 | PASS | Key 不写仓库／数据库／报告／浏览器持久存储，凭据接口和脱敏日志测试通过 |

## 质量样本与性能证据

- `artifacts/evaluation/gold-manifest.json`：120 个项目自产、CC0-1.0 样本，生成后按 SHA-256 冻结；每类 text/image/pdf/office/audio/video 各 20 个。
- `artifacts/evaluation/technical-smoke-results.json`：仅文件类型和解析降级技术冒烟，不是现实语义准确率。120 项 accuracy/macro-F1/automatic coverage 均为 0.8333，abstain 0.1667；20 个视频因缺 ffmpeg/ffprobe 全部 `partial` 并弃判，未改金标准。
- `artifacts/reports/phase-08-performance.json`：10,000 文件冷/热扫描 2.404/2.452 秒，持久化 3.440 秒；5,000 行 50 次分页查询 p95 3.790 ms；120 项多模态批次 8.394 秒。
- 浏览器任务 `10cb9cf3-809e-4f62-8594-381adee36ec3`：100 行/页、100 页、第二页从 `metadata-00100.txt` 开始；全选筛选结果显示 10,000，精确搜索返回 1 项；console warning/error 均为 0。

## 未开放能力

生产 `direct_move` 继续关闭。当前自动化文件安全门已通过，但原生冻结桌面、专用卷断开、真实模型和干净用户安装验证尚未完成；不会因为脚本或浏览器通过而扩大到用户真实目录。
