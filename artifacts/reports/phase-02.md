# 阶段 02 验收报告：安全文件执行、恢复与撤销

日期：2026-09-13  
环境：Windows 11 x64；Python 3.12.10；本地 NTFS C: 临时目录与项目 D: 测试目录

## 结论

安全执行核心已实现并通过自动化：确定性 PlanCompiler、完整源 SHA-256/身份快照、不可变 plan_hash、显式批准、SQLite 操作日志、同卷句柄重命名、跨卷 copy-verify-publish-delete、no-clobber、取消、恢复和独立 undo 计划均已落地。生产 direct_move 继续关闭，仅能由显式测试开关启用。

状态记为 **BLOCKED_EXTERNAL（核心自动化通过）**：当前机器没有可安全断开的专用测试卷，也没有受控的云端占位文件样本，因此 FS15 的卷中途断开和 FS16 的真实云占位属性仍缺实机证据。ENOSPC 使用精确 `OSError(ENOSPC)` 故障注入，不冒充真实填满磁盘。上述缺口不放宽执行器条件；独立的阶段 03 解析开发可以继续。

## 文件安全验收

| 编号 | 结果 | 证据摘要 |
|---|---|---|
| FS09 | PASS | 既有同名稳定生成 `(2)`；预览目标即实际目标 |
| FS10 | PASS | 批内冲突按 file_id 稳定排序 |
| FS11 | PASS | 批准后目标出现返回冲突，不临时改名 |
| FS12 | PASS | 执行前及复制发布前复核身份、mtime、大小和 SHA-256 |
| FS13 | PASS | 未支持格式生成 skip，保持原处 |
| FS14 | PASS | JPG/XMP、视频字幕、音频歌词唯一配对；歧义不组；统一冲突后缀 |
| FS15 | PARTIAL_EXTERNAL | 文件锁、只读源通过；真实卷中途断开无专用介质，未测 |
| FS16 | PARTIAL_EXTERNAL | NTFS ADS 与硬链接阻塞通过；真实云占位样本未提供 |

## 执行与恢复验收

| 编号 | 结果 | 证据摘要 |
|---|---|---|
| OP01 | PASS | report_only 前后清单与 SHA-256 不变 |
| OP02 | PASS | copy 后源存在且源/目标 SHA-256 相同 |
| OP03 | PASS | 同卷 move 使用已核验 Windows 句柄和 `SetFileInformationByHandle`，ReplaceIfExists=false |
| OP04 | PASS | C:→D: 两个真实卷按 COPY/FSYNC/TEMP_WRITTEN/VERIFIED/PUBLISHED/SOURCE_REMOVED/COMMITTED 执行 |
| OP05 | PASS | 独立子进程在六个持久检查点直接 `os._exit(91)`，重开 SQLite 后恢复一致 |
| OP06 | PASS | 重复 execute 不新增事件、不重复移动 |
| OP07 | PASS | chunk 检查点取消，已提交项保留；自有临时文件由恢复服务核验 |
| OP08 | PASS | undo move 原路径占用时 UNDO_CONFLICT，不覆盖 |
| OP09 | PASS | undo copy 仅处理未变化副本；Windows 回收站实际调用通过 |
| OP10 | PASS | 重复 undo 幂等 |
| OP11 | PASS_INJECTED | ENOSPC 注入发生在发布前，源保留、目标未出现 |
| OP12 | PASS | PREPARED 日志提交失败时无磁盘动作 |
| OP13 | PASS | 新目标出现不绕过批准目标 |
| OP14 | PASS | 组预检失败整组不动；中途 sidecar 失败报告 COMMITTED+FAILED，不伪装原子成功 |

## 崩溃恢复矩阵

以下每一行均由新子进程加载已批准计划，状态事务提交后立即强制退出；父进程重新打开数据库并执行 RecoveryService。

| 退出检查点 | 恢复结果 |
|---|---|
| PREPARED | 重新核验源后重试，提交成功 |
| COPYING | 删除/替换仅属于本操作的不完整临时文件后重试 |
| TEMP_WRITTEN | 校验临时文件后发布并提交 |
| VERIFIED | 发布已验证临时文件并提交 |
| PUBLISHED | 根据目标预期 SHA-256 补提交；不重复复制 |
| COMMITTED | 识别终态，不重复执行 |

同卷移动还覆盖“源缺失、目标哈希匹配、日志未提交”的恢复；未知目标内容进入 CONFLICT。

## 运行命令与结果

| 命令 | 退出结果 |
|---|---:|
| `uv run pytest -q` | 0；最终 81 passed |
| `python scripts/verify.py safety` | 0；73 passed（新增测试前的阶段出口快照） |
| `python scripts/verify.py unit` | 0；6 passed |
| `uv run pytest tests/integration/test_operation_journal.py -q` | 0；14 passed，含六项真实子进程退出 |
| Windows 回收站定向测试 | 0；1 passed |

测试只使用 pytest 临时目录与 `artifacts/test-workspaces`。真实跨卷用例在 D: 创建唯一临时目录，并在 `finally` 中仅清理该已核验目录；未触碰个人文件。

## 关键产物

- `backend/src/guixu/application/plan_compiler.py`
- `backend/src/guixu/application/recovery.py`
- `backend/src/guixu/application/undo.py`
- `backend/src/guixu/infrastructure/db/operation_journal.py`
- `backend/src/guixu/infrastructure/filesystem/executor.py`
- `backend/src/guixu/infrastructure/filesystem/windows_handles.py`
- 安全 API：plan/compile、plan/approve、execute、undo/plan

## 外部阻塞与后续限制

- FS15 卷断开：需要可牺牲的可卸载测试卷或虚拟磁盘；当前不自动创建/挂载磁盘。
- FS16 云占位：需要明确授权的受控 OneDrive Files On-Demand 样本。
- OP11 真实磁盘满：未填满用户磁盘，仅验证 ENOSPC 分支。
- direct_move：生产仍关闭，阶段 08 全量安全验收前不开放。

## 下一恢复点

读取 `prompts/codex/03_PARSERS.md` 及解析/Profile 契约，开始 ParserRegistry、隔离 worker、真实文本/PDF/Office/图片/音视频小样本与缺组件降级；云调用继续关闭。
