# 阶段 08 验收报告：安全、质量与性能

日期：2026-09-14  
环境：Windows 11 x64；Python 3.12.10；32 logical CPUs；34,024,747,008 bytes RAM；SQLite WAL；Chromium 本地 UI；仅项目测试目录

## 结论

阶段 08 为 **BLOCKED_EXTERNAL**，不是发布通过。116 项后端测试、前端 typecheck/8 项测试/production build、数据库全新迁移、浏览器 E2E、真实 C:→D: 跨卷路径、安全预览票据、10,000 文件扫描与 5,000 行列表性能均通过，未发现 P0 自动化安全失败。

发布仍被真实 DeepSeek/Qwen 语义评测、ffmpeg/ffprobe/ASR 增强能力、pywebview 原生高 DPI/多显示器、专用卷断开与干净 Windows 安装环境阻塞。自产技术样本只证明类型管线和安全降级，不能替代真实语义质量。因此 `direct_move` 生产开关保持关闭，版本仍是 `dev`。

## 本轮实现与修复

- 后端文件列表增加服务器端搜索、状态过滤、limit/offset 和 LIKE 转义；前端审阅页改为 100 行分页，10,000 项全选按 500 条分批获取。
- 新增随机 60 秒媒体预览 ticket，只允许已扫描且未变化的 raster/audio/video 文件；拒绝 HTML/PDF 原样注入，支持单 Range，响应带 `no-store`、`nosniff` 与严格 CSP；生产关闭访问日志，避免 ticket 泄漏。
- 扫描器同时排除当前输出根和数据库记录的历史输出根，覆盖重复任务回扫。
- 建立 120 项许可明确、可复现、带 hash 的冻结样本 manifest，以及独立的技术冒烟结果；不把该结果命名为真实模型准确率。
- 增加可重复的 10,000 文件／5,000 行／多模态批次基准脚本和 `quality` 验证范围。

## 关键安全验收

| 范围 | 结果 | 说明 |
|---|---|---|
| 越界、reparse、系统／项目目录 | PASS | 路径解析、授权根、输出排除与重解析点测试通过 |
| 锁、源变化、目标竞态、no-clobber | PASS | Windows 真实锁句柄、提交前身份/hash、exclusive publish、稳定同名后缀通过 |
| 跨卷与恢复 | PASS / 外部补证 | 本机真实 C: 临时目录→D: 项目测试目录未 skip，安全顺序通过；物理卷拔出仍需专用环境 |
| 撤销冲突 | PASS | 外部修改或原位占用均不覆盖；反向计划另行批准 |
| localhost 与媒体预览 | PASS | 随机会话、Host/Origin、ticket scope/TTL/文件身份与安全响应通过 |
| XSS、提示注入、Key 泄漏 | PASS | Vue 文本渲染、分类结构边界、凭据存储/脱敏/导出检查通过 |
| local-only 与隐私预算 | PASS | 未授权内容不出站；预算和重试有硬上限；缺服务不伪造成功 |
| direct_move | CLOSED | 自动化门通过，但完整发行门未通过，因此生产仍禁用 |

## 质量与性能

质量样本由 `scripts/create_acceptance_samples.py` 在项目测试目录生成，声明 CC0-1.0，manifest 中含每个文件 SHA-256。生成后未为提高结果而修改标注。

技术冒烟 120 项：80 `ready`、40 `partial`；accuracy/macro-F1/automatic coverage = 0.8333，abstain = 0.1667。80 个自动接受项类型命中率 100%；20 个音频以 metadata `partial` 归类，20 个视频因 ffmpeg/ffprobe 缺失全部安全弃判。这是合成类型识别测试，不含真实内容语义、模型调用或人工现实语料，不能宣称满足真实分类质量目标。

性能：10,000 个共 138,890 bytes 的 metadata 文件，冷扫描 2.404 秒、立即热扫描 2.452 秒、扫描并持久化 3.440 秒；进程 RSS 从 87,908,352 增至扫描后 109,600,768、入库后 116,170,752 bytes。5,000 行按 100 行查询 50 次，median 2.711 ms、p95 3.790 ms、max 3.818 ms。120 项多模态批次 8.394 秒。模型服务内存未测，因为没有获授权真实服务。

浏览器 E2E 使用同一 10,000 项任务：第 1 页 100 行、共 100 页；第 2 页首项 `metadata-00100.txt`；筛选全选显示 10,000；搜索 `metadata-09999` 返回 1 项；console 0 warning/error。点击发起全选请求约 303 ms，1.2 秒后的观测确认状态已完成；不把该观测间隔冒充精确完成时延。

## 命令与实际结果

| 命令／操作 | 退出结果 |
|---|---:|
| `python scripts/create_acceptance_samples.py` | 0；120 项、manifest 与许可文件生成 |
| `python scripts/run_phase08_benchmarks.py` | 0；10,000 文件、5,000 行查询、120 项批次结果落盘 |
| 全新数据目录执行 `uv run alembic upgrade head` | 0；revision `0001`，23 张表 |
| `python scripts/verify.py quality` | 0；6 passed |
| `python scripts/verify.py all` | 0；所有后端范围、前端 typecheck/test/build 通过 |
| `uv run --all-extras pytest -q` | 0；116 passed，2 个已知 warning |
| `uv run pytest -q -rs tests/safety/test_cross_volume_cancel.py` | 0；4 passed，无 skip |
| Chromium 万文件分页／全选／搜索／console 检查 | PASS；console 0 warning/error |

完整逐项状态见 `artifacts/reports/phase-08-test-matrix.md`，原始指标见 `artifacts/reports/phase-08-performance.json` 与 `artifacts/evaluation/technical-smoke-results.json`。

## 外部阻塞与下一阶段

- 用户未配置并授权真实 DeepSeek Key 或 Qwen 服务，AI01～AI03 与双模型公平语义对比未运行。
- ffmpeg/ffprobe 和已校验本地 ASR 模型不存在，音视频增强仍为 `partial`/弃判。
- pywebview 原生窗口的高 DPI、多显示器、强制关闭恢复与干净 Windows 用户安装尚无证据。
- 物理卷断开、云占位文件和代码签名证书需要专用环境／资源。

进入阶段 09：构建并核验 Windows onedir，尝试 Inno Setup；补齐资源清单、手册、校验值和已知限制。脚本存在不计作 EXE 或安装器通过。
