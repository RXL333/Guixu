# PHASE F 首次整理分析冒烟报告

更新时间：2026-09-24

## 结论

首次发送消息不再只是写入 Message。新会话发送第一条整理要求后，会进入真实的 Scanner → Parser/Evidence → AI Taxonomy Planner → AI Classifier → Plan Compiler 链路，并只生成一个 `FULL / PROPOSED` 的 PlanVersion v1 预览；此路径不会调用执行器，不会改变真实磁盘文件。

## 已实现

- 新增 `POST /api/v1/conversations/{conversation_id}/turns`。
- 首次分析需要有效授权 scope、启用模型和内容授权确认。
- 复用现有 Task、FileProfile/Evidence、Semantic Cache、Planner、Classifier、OperationService 和 OperationJournal。
- 真实文件证据与文件数量会写入上下文、PlanVersion 和助手消息；不生成虚假助手回复。
- 前端首次发送显示扫描/分析/预览忙碌状态，并显示真实 PlanPreviewCard。
- 仅允许首次会话入口；已有方案或执行记录仍走后续 refinement 流程。

## 验证

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/integration/test_first_analysis.py tests/integration/test_ai_only_end_to_end.py` | 3 passed |
| `npm.cmd test -- --run tests/conversation-workspace.test.ts` | 14 passed |
| `npm.cmd run typecheck` | exit 0 |
| `npm.cmd run build` | exit 0 |
| `scripts/package-windows.ps1 -SkipTests -SkipInstaller` | onedir build + frozen diagnostic exit 0 |

专项测试验证：无 scope 会被拒绝；文本文件会产生真实 evidence；PlanVersion 为 v1/FULL 且无 baseline execution；执行轮次为空；文件路径和 SHA-256 在分析后保持不变。

修复后的 Windows 目录版已同步到 `artifacts/release-phase-m/Guixu-0.1.0/Guixu.exe`，冻结诊断 exit 0；SHA-256：`47AA4EB98AE33FCE270E9F6C3A9D4107CAF20ED4ACCF06464423D54EE3B1FA15`。

## 外部条件

本报告未伪造真实 DeepSeek/Qwen 网络调用结果。真实模型 smoke 仍取决于用户已完成的模型能力探测、有效凭据/本地服务和隐私授权；缺少这些条件时 API 会返回明确的 capability/authorization 错误，而不会回退到本地语义规则。
