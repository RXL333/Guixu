# 阶段02｜文件安全先行

```text
/goal 完成归序阶段02的安全文件执行、恢复和撤销闭环。基于阶段01真实工程继续，不重建整个项目。先读AGENTS.md、PROJECT_STATUS.md、docs/03_DATABASE.md、07_API.md、08_SAFETY.md、09_TESTING.md及对应SQL/OpenAPI。

用确定性分类树与测试样本实现PlanCompiler：合法名称、受授权目标、同名稳定后缀、逐文件SHA256/卷ID/文件ID、taxonomy/settings/source快照、不可变plan_hash、用户批准和幂等。模型不参与本阶段。

实现持久操作日志和serial executor。先落PREPARED，再处理文件；同卷用不覆盖重命名，跨卷按独占temp复制、flush/fsync、读回校验、no-clobber发布、再核验源并移除。禁止os.replace覆盖目标，不把shutil.move当完整安全协议。DB日志失败时停止破坏动作。

实现预览移动、复制、报告；直接移动只在测试环境启用。执行前源变化/目标出现/权限丢失必须冲突或安全暂停，不临时改目标绕过批准。取消仅停止未开始项。恢复需逐项检查源/目标/temp与日志，不以数据库单一状态猜磁盘。

实现独立undo计划：plan_kind、parent_plan_id与reverses_operation_id持久化。移动反向恢复不覆盖原位置；撤销复制只回收本任务且未变化的副本，回收站不可用则保留。被外部修改的目标标UNDO_CONFLICT。支持重复execute/undo幂等，保留新建目录记录但不自动清源空目录。

逐项通过FS09～FS16、OP01～OP14。用故障注入在各持久检查点终止并恢复。跨卷测试必须是两个真实卷，Windows句柄行为必须在Windows测；环境不具备如实标阻塞，不把同盘子目录冒充跨盘。

报告phase-02.md记录源/目标hash清单、故障点恢复矩阵、撤销冲突证据；更新PROJECT_STATUS。安全失败不得放行后续真实文件执行，其他独立解析开发可以继续。
```
