# Guixu 1.0 Final Acceptance Audit

更新时间：2026-09-24
审计基线：`main` / `b6ef4ed7dba24519bd7d4f03c4e042dc1f499eea`
当前结论：**NOT RELEASE READY — Feature Freeze / Acceptance In Progress**

## 1. 审计范围与规则

本报告以当前源码、正式设计文档、现有测试集合、真实模型报告和本机打包产物为准。历史报告只作为既有证据，不把“曾经运行过”“存在测试名”或 Fake Model 结果替代当前真实验收。

PHASE N 起执行 Feature Freeze：只允许 bug、安全、性能、测试、打包、错误提示和明确 UI 缺陷修复；不新增 Provider、向量搜索、Watch Folder、长期记忆、多 Agent 或新架构。新需求记录到 `docs/POST_1_0_BACKLOG.md`，本阶段不做 Legacy Cleanup。

## 2. 当前正式产品能力

| 能力 | 当前实现 | 主要证据 | 当前验收判断 |
|---|---|---|---|
| Conversation Workspace | 持久 Conversation、Message、Context、文件引用和三栏桌面 UI | `CONVERSATION_DATA_MODEL.md`、前端 39 tests | 已实现，仍需长会话/分辨率/打包 UI 回归 |
| 首次 AI 整理 | 授权目录扫描、真实 evidence、AI taxonomy/classification、FULL PlanVersion | `first_analysis.py`、`phase-n-real-deepseek-e2e.json` | 真实 DeepSeek 已完成 v1→v2→diff→批准→执行→重启读取一次；更广组合仍待验收 |
| PlanVersion | 线性不可变版本、diff、restore-as-new-version、hash/revision approval | `PLAN_VERSIONING.md`、集成测试、真实 DeepSeek E2E | v1→v2 首轮执行前修改链已实测通过；失败回滚故障矩阵仍待补齐 |
| 执行后继续对话 | Affected Scope、Evidence reuse、FULL/DELTA refinement、多轮执行 | `POST_EXECUTION_CONVERSATION.md`、真实 DeepSeek refinement 报告 | 已有真实模型局部 refinement 证据 |
| File References | selection/focus/文件名/最近消息/最近计划/最近执行映射到 stable file ID | `FILE_REFERENCES.md`、精确 5-file 候选范围及 500-file 集成测试 | 自动化引用/范围覆盖；完整计划执行与真实桌面多轮语义回归待跑 |
| Semantic Cache | stable file ID + fingerprint + evidence provenance、失效、重启、single-flight | `SEMANTIC_CACHE.md`、500-file 自动化 | Fake/本地测试覆盖；真实 DeepSeek cache smoke 仍为 BLOCKED_EXTERNAL |
| Session Recovery | AgentTurn interruption、workspace reconcile、plan revalidation、scope relink | `SESSION_RECOVERY.md`、真实临时文件测试 | 自动化覆盖；packaged EXE 重启继续对话待跑 |
| Conversational Undo | preview、approval、partial、依赖阻断、冲突、历史保留 | `CONVERSATIONAL_UNDO.md`、20 文件 smoke、10-file crash-resume test | 真实 FS 自动化及 4/10 子进程崩溃恢复通过；发行包 Undo 仍待验证 |
| FileOperationEngine | no-clobber、journal、copy/move、恢复、旧 Task undo | `08_SAFETY.md`、安全与 journal 测试 | 高风险自动化较强；专用卷断开/云占位仍无环境 |
| DeepSeek | 文本、JSON、Vision、能力探测、凭据存储、最小出站 | 模型测试、真实首次分析/refinement 报告 | 真实 text/vision/首次分析/refinement 有证据；完整 RC 链需重跑 |
| Windows Desktop | pywebview、单实例、随机 session、PyInstaller onedir/portable | `package-windows.ps1`、当前本机 onedir | 本机构建可用；Installer/签名/Clean Windows 未完成 |

## 3. 自动化测试现状

本轮 backend 完整回归 `uv run pytest -q` **198 passed**（78.29s，exit 0）；其后新增 timeout/5xx transport 测试定向 **2 passed**，按用户要求没有重复整套，因此新增用例后的 backend 完整总数未确认。前端 `npm run test:run` **39 passed / 5 files**（exit 0）；生产 build/typecheck、PyInstaller、frozen diagnose/worker smoke 均已通过。Backend 有 Starlette/Pillow 测试警告及 Windows symlink fixture cleanup 警告；Frontend ModelsPage 测试有未注册 RouterLink warning。三个后端定向集成测试（方案版本 diff/恢复、首轮批准执行、执行后多轮 DELTA）修复后通过；其中发现并修复“扫描时尚无 files.sha256 导致 ConversationFile 指纹为空、计划批准误报 FILE_STATE_UNAVAILABLE”的运行时问题。

高风险自动化已覆盖：

- no-clobber、目标竞态、源变化、磁盘空间、journal 写失败、跨卷 copy/verify/publish/delete；
- PREPARED/COPYING/TEMP_WRITTEN/VERIFIED/PUBLISHED/COMMITTED 进程退出恢复；
- approval/hash/revision、重复 execute、旧计划失效；
- Undo 原路径占用、内容修改、外部移动、missing、历史依赖、partial 和 double confirm；
- Conversation restart persistence、PlanVersion diff/restore、File References 隔离；
- Semantic Cache 命中、fingerprint 变化、重启、500-file lookup；
- workspace 外部 move/rename/modify/missing/new 与 scope unavailable；
- 目录授权、reparse/symlink、ADS、hardlink、Windows 非法路径段；
- Key/Authorization/base64 不写审计记录的模型边界测试。

当前最终工作树已重跑 backend 与 frontend 全量自动化；结果与 warning 类型见本报告上文及 `guixu-1.0-final-acceptance.md`。已测测试集通过不代替尚未运行的真实 DeepSeek 错误矩阵、桌面手测或 clean-machine smoke。

本阶段随后完成 13 个安全/幂等定向测试：不可信文本提示不会让分类器输出 allowlist 外路径；首次自然语言整理只生成预览；审批 hash 错误被拒绝；目标竞态与同名冲突不覆盖；Workspace reconcile 正确识别外部 rename/move/modify/missing/new；重复 execute/undo 幂等；Windows reparse point 不被扫描器递归。另有 7 个模型/分类定向测试覆盖 401 不重试、429 Retry-After、有限修复、不支持 Vision、拒绝路径型分类输出及同扩展名按内容分类。它们只证明相应隔离子场景，不替代完整安全矩阵、发行态或 clean-machine 验收。

## 4. Fake Model、真实模型与真实文件系统证据

### Fake Model / 受控 evaluator

- 首次 Conversation 自动化使用 `FakeAnalysisGateway` 验证 scanner→evidence→planner→classifier→plan→approval→execute。
- AI Planner/Classifier 大多数分类契约测试使用受控 gateway，重点验证 schema、类别 allowlist、证据引用、无本地规则 fallback。
- Post-execution 多轮测试使用受控 evaluator，验证影响范围、版本、批准和执行状态，而不是供应商语义质量。
- DeepSeek 错误测试主要是 transport/adapter 层模拟，不等于真实供应商故障现场。

### 真实 DeepSeek

- 已有真实 Text 与 JSON mode 冒烟证据。
- 已有 `deepseek-flash` 真实 Vision probe 与图片 evidence 证据。
- 2026-09-24 完成 5 JPG 首次 Conversation 分析：planning/classification 各 1 次，生成 FULL v1，未执行磁盘操作。
- 2026-09-21 完成真实 post-execution refinement：20 文件中只评估 10 个候选，复用 10 份 evidence，1 次 classification，执行 DELTA Round #2。
- 真实 Semantic Cache 19/1 refresh 场景尚未运行；现有报告明确为 `BLOCKED_EXTERNAL`。
- 2026-09-24 当前工作树真实 DeepSeek 5-JPG E2E 已通过：首次 v1、执行前修改生成 parent=v1 的 v2、diff、审批前文件 hash 不变、批准后 Execution #1 COMPLETED、重启后恢复 5 条消息/2 方案/1 执行/5 文件引用。尚未覆盖重启后继续对话和 Undo 的同一组合链。

### 真实文件系统

- 10 文件 AI-only 整理、20 文件多轮 Undo、跨卷复制/移动、Windows lock/handle、journal crash/recovery 均使用真实临时文件。
- Conversation 删除和 Task 删除的磁盘不变性已有自动化。
- 分析 31/50 后异常退出：已新增真实独立子进程退出测试；重启复用 31 个视觉 evidence，只重新请求剩余 19 个文件的视觉分析，另为 3 个已有视觉 evidence 补齐分类。最终 50 个分类和视觉 evidence 齐全，Conversation v1 PlanVersion 与提议消息恢复落库，临时目录 50 个源文件 hash 不变。Fake gateway / 当前开发态；发行包恢复仍未验证。
- Undo 10 项中完成 4 项后独立子进程 `os._exit(91)`：重启识别 4 UNDONE + 6 PLANNED、标记 Conversation round/Undo plan 为 RECOVERY_REQUIRED，续跑只处理剩余 6 项。
- Execution 20 项中完成 8 项后独立子进程 `os._exit(91)`：重启识别 8 COMMITTED + 12 PLANNED，恢复只处理余下 12 项，20 个文件最终均在新目录且 Conversation round 完成；指定集成用例通过。
- 单图真实临时 JPG 在服务重启后命中相同视觉 evidence 与分类输入，未再次调用分类 gateway；但这不等于目标中的 50 图在第 31 项进程崩溃后续跑。
- 物理卷断开、云占位、同步客户端冲突：缺少专用环境。

## 5. 缺乏异常测试的功能

| 缺口 | 风险 | 当前状态 |
|---|---|---|
| 首次执行前修改要求生成 v2 | 当前真实 DeepSeek 5-JPG 完整流程一次通过；失败回滚核心矩阵 5 tests 通过 | PASS（一次真实运行 + 定向失败注入） |
| Analysis 31/50 crash 后按 cache 续跑 | 发布态恢复路径仍需证明 | PASS（当前开发态 Fake gateway：31 evidence 复用、只重跑 19 个视觉分析并完成 PlanVersion；发行包未测） |
| Conversational Undo 4/10 crash | 子进程退出后会话投影与续跑 | PASS（10 file temp FS） |
| Execution 8/20 crash | 子进程退出、重启与续跑后 Conversation 执行状态 | PASS（20 file temp FS） |
| packaged EXE 完整 DeepSeek→execute→restart→undo | 开发态通过不能代表发行态 | NOT_TESTED |
| 真实 DeepSeek invalid key/429/5xx/timeout/cancel 矩阵 | 现有主要为模拟 transport | PARTIAL |
| Prompt injection evidence → planner/classifier/operation chain | 分类 allowlist 拒绝路径注入；真实多载荷与执行链未覆盖 | PARTIAL |
| ConversationFile scope escape | P0-001 已修复；越权 file ID API 回归和原子批处理测试通过，`..`/system path/junction 全矩阵仍缺 | PARTIAL |
| Conversation soft delete safety | 新增已执行临时文件后删除验证 path/hash 不变、journal/round 保留，恢复后 Undo 预览成功 | PASS (dev integration) |
| 100/300/500 messages 与 10+ agent turns | revision/current pointers 长程一致性 | NOT_TESTED |
| 500/1000/5000 Conversation workspace 性能 | 现有 10k scanner 与 5000 DOM window 单项测试不足 | PARTIAL |
| 1366×768、1280×720、Windows 125%/150% | 可能存在不可点击/溢出 | NOT_TESTED |
| Installer/升级/卸载/Clean Windows | 发布包可安装性未知 | BLOCKED |
| 中文用户名、空格路径、普通用户 Program Files/AppData | 发行权限兼容性不足 | PARTIAL |

## 6. 状态一致性风险

1. 执行前重规划旧方案保护已通过 5 个定向集成测试：规划失败、分类失败、核心 Plan 编译后版本提交前失败、中断后启动恢复、v1→v2 正常路径。并发交错仍需单独验收，但当前没有已知 open P1。
2. 首次 FULL 执行与首轮执行前 v1→v2 已在当前源码真实 5-JPG DeepSeek 端到端脚本中一次成功，审批前磁盘不变、审批后执行完成并经重启恢复；这不替代 packaged EXE 和继续对话/Undo 组合验收。
3. Session Recovery 对部分 Undo 与普通执行的崩溃恢复均有指定子进程集成覆盖；发行包启动后自动呈现/引导恢复流程仍未验收。
4. AgentTurn 当前主要承担持久状态和中断记录；首次分析为同步请求，没有细粒度文件级 turn checkpoint。已用语义 evidence/classification 持久缓存验证 31/50 崩溃后只重跑 19 个视觉分析，并补齐 PlanVersion；任意百分比的流式进度与发行包重启仍未验证。
5. 当前 API 传入 idempotency header 的若干 Conversation route 直接 `del idempotency_key`，底层依靠 approval/round 唯一约束和 UI busy latch；重复请求矩阵需专门验收，不能只依据前端禁用按钮。

## 7. 当前打包状态

- PyInstaller Windows x64 onedir 与 portable zip 可以在当前开发机构建；PHASE N 新包位于 `artifacts/release-phase-n/Guixu-0.1.0/Guixu.exe`，旧 `release-phase-m` 包未覆盖。
- 冻结诊断和 worker 已有本机构建证据，前端资源由 `frontend/dist` 打入 `_internal`。
- `Guixu.spec` 已排除 pytest/hypothesis；PHASE N onedir 共 434 个文件、portable zip 为 470 个目录/文件记录（434 个文件），两者均未发现 node_modules/tests/maps/.env。新增 `scripts/audit_release_secrets.py` 对 onedir 与 zip 各扫描 301,780,329 uncompressed bytes，DeepSeek/GitHub/AWS/PEM/Bearer/inline credential signatures 均为 0 命中。由于是模式扫描且不覆盖任意格式未知凭据，B08 仍 PARTIAL。
- 本机未找到 Inno Setup 6：Setup EXE 未构建。
- 没有代码签名证书；项目对外许可证尚未确定。
- 无“没有 Python/Node/源码/旧 SQLite”的 clean Windows 验收环境。
- 当前 release 仍为 `0.1.0`，尚未生成 `1.0.0-rc.1` 元数据、SHA256 和用户 release notes。

## 8. 已知 P0 / P1 风险

### P0

当前没有 open P0；本轮发现并修复了 P0-001 ConversationFile 跨授权 scope 引用漏洞（整批拒绝 + API 回归通过）。Execution crash、完整 path/symlink scope 矩阵和 clean-machine gate 尚未全部完成，因此现在不能把“open P0 = 0”当作最终发布结论。

### P1

- **P1：当前登记 open P1 = 0。** 这不代表完整安全、并发或 crash gate 已完成；未知风险仍由验收矩阵追踪。

以下是发布阻塞证据缺口，不先当作已确认软件缺陷：Clean Windows、Installer、packaged full E2E、真实 Semantic Cache 成本场景、完整 crash matrix。任何一项实际失败将按结果升级为 P0/P1 bug。

## 9. 当前最需要验证的链路

优先级按发布风险排序：

1. 用发行包串联执行后继续对话、Undo 与重启恢复；目前开发态真实首轮 v1→v2→执行链已通过一次。
2. 完成剩余并发/Crash/安全/桌面/clean-machine 发布门。
3. 发行包中的 Analysis/Execution/Undo 崩溃续跑组合；当前开发态 Analysis 31/50、Execution 8/20、Undo 4/10 已通过隔离子进程测试。
4. Session restart 后继续对话、File References、cache、Undo 的组合链。
5. 500/1000/5000 文件扫描、DB、reconcile、Conversation open、UI windowing 和内存记录。
6. packaged EXE 的首次启动、配置、执行、重启和 Undo。
7. Clean Windows install/extract 与普通用户权限矩阵。

## 10. 审计结论

当前代码库已经拥有较强的文件安全与状态持久化基础，真实 DeepSeek 首轮修改、执行和重启读取也已通过一次，登记的 P1 已清零；当前工作树全量 backend/frontend 测试通过，但仍不满足 Guixu 1.0 Release Ready。发行包已验证关闭/重启后恢复保存会话；剩余关键门包括真实模型失败与完整安全矩阵、发行包重启后继续 refinement/执行/Undo、长会话与桌面 DPI、干净 Windows/安装器。按 `docs/RELEASE_ACCEPTANCE.md` 继续推进，未运行项目保持 `NOT_TESTED`/`BLOCKED`，不得提前升级为 PASS。
