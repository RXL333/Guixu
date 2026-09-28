# 文件系统与安全

当前操作以扫描后的 stable file ID、授权范围、指纹、方案版本和批准记录为依据。AI 不提供目标路径；安全执行器不覆盖已有文件，持久化操作日志用于恢复和撤销。代码入口见 `backend/src/guixu/infrastructure/filesystem/`，契约见 `contracts/`。

相关说明：[会话恢复](../architecture/SESSION_RECOVERY.md)、[对话式撤销](../agent/CONVERSATIONAL_UNDO.md)。
