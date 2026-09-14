# 阶段08｜安全、质量与性能验收

```text
/goal 完成归序阶段08发布前验收，按docs/09_TESTING.md和13_TRACEABILITY.md验证真实实现，修复发现的问题，不能只写一份漂亮测试报告。

运行后端全量、前端typecheck/test/build、浏览器E2E、数据库迁移与全部关键安全测试。重点验证路径越界、reparse/锁/目标竞态、no-clobber、跨盘恢复、undo冲突、localhost鉴权、媒体票据、XSS、Key泄露、提示注入、local-only和预算。

建立许可明确的样本manifest与人工作标评测集。真实模型可用且有授权时对相同样本/模板/采样/隐私设置比较DeepSeek与Qwen，分开报告高可信精度、macro-F1、覆盖率、弃判率、错误、调用/usage/时延。缺真实服务如实未验证；不能拿假服务或自评分做准确率。

测10,000文件元数据扫描、5,000行列表与多模态小批次，记录环境/文件总量/冷热缓存/主程序与模型各自内存。200ms响应等是目标不是预设结果。未达语义质量时收紧人工审阅、调整证据或模板，不篡改金标准。

只有相关文件安全与授权测试通过后才开放生产direct_move开关；新auto_plan树仍需批准，不绕过不确定项审阅。任何安全关键失败阻止发布真实文件操作版本。

输出phase-08.md、release-readiness.md、测试清单和准确的PASS/FAIL/BLOCKED_EXTERNAL。更新PROJECT_STATUS。缺Windows/真实跨卷环境必须具体标注，不用两个同盘目录伪装验证。
```
