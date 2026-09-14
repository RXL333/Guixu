# 阶段 04 验收报告：模板、规则、分类树与人工审阅

日期：2026-09-13  
环境：Windows 11 x64；本地 SQLite；模型协议仅使用测试中明确注入的假服务

## 结论

阶段 04 **PASS**。24 套内置模板完整校验并幂等入库；用户模板使用复制/新版本方式编辑，不能覆盖内置版本。规则采用受限 AST，分类树按区域、版本和 hash 冻结；分类结果只能引用当前文件证据与当前批准树的可选 category ID。人工 review 与原建议分别持久化，树或 review 改动会使未执行旧计划失效。

真实自然语言理解与语义质量不在本阶段冒充完成：测试假服务仅验证受限模型协议，真实 DeepSeek/Qwen 连接、隐私预算和质量评测进入阶段 05/08。

## CL01～CL11

| 编号 | 结果 | 证据 |
|---|---|---|
| CL01 | PASS | 24 个稳定 template_id；全部通过 template schema、无环、父节点、深度、同级数、正反例检查；重复 seed 后仍 24 条 |
| CL02 | PASS | modality_first + depth=1 只生成单层模态节点，无隐藏二级 |
| CL03 | PASS | exclude 高于 force；最小 priority 强制命中；同优先级不同类别返回 `RULE_CONFLICT` |
| CL04 | PASS | `rules_only + auto_plan` 由完整设置模型拒绝 |
| CL05 | PASS | 非当前树、结构节点、路径样式 category ID 均返回 `CATEGORY_NOT_ALLOWED` |
| CL06 | PASS | fallback “其他”是实体类别；证据不足使用 `abstain=true/category_id=null`，两者不混用 |
| CL07 | PASS | 自评分必须结合证据、覆盖率和警告；0.99 也不能绕过类别/证据校验 |
| CL08 | PASS | 文件证据中的“忽略规则/输出路径”只作为文本；恶意类别被 allowlist 拒绝，无文件操作 |
| CL09 | PASS | 新 taxonomy draft 生成新版本并把 draft/validated/approved 旧计划设为 superseded |
| CL10 | PASS | 人工改类写 reviews；原 classifications 记录保持不变 |
| CL11 | PASS | 分类 input_hash 包含 profile + taxonomy；跨树版本不复用；解析内容缓存也重绑定当前 file_id |

补充通过：自然语言政策输出按 `policy-result.schema.json` 校验且 unknown 固定 abstain；规划样本按 scope、模态、原子目录确定性轮询，每区最多 48、全任务最多 200。

## 实现摘要

- `TemplateService`：筛选、读取、复制、用户模板导入/版本化；内置模板只读。
- `validate_nodes` / `TaxonomyService`：无环、父节点、同级重名、深度/兄弟/总节点限制；区域归属与批准 hash；版本化持久化。
- `RuleService` / `RuleEngine`：字段白名单、比较符白名单、AST 深度/叶子限制、scope、priority、exclude/force/suggest；不使用 eval、脚本或复杂正则。
- `ClassificationService`：JSON Schema、file/taxonomy/evidence/category 四重上下文验证；T24 纯规则真实运行；测试假服务明确通过参数注入，生产缺模型返回 unavailable。
- `review_bulk`：同一事务内做 task revision CAS、区域/树/可选节点校验、review 写入及旧计划失效。
- `OperationService`：存在批准树时只编译 high 建议或明确人工决定的真实 category path；medium/low/abstain 保持原处。

## API 与真实 UI

已实现模板列表/导入/复制、规则列表/创建/只读试跑、任务 taxonomy 列表/批准、批量 review、文件详情建议与 review。扫描使用模板时按各 scope 产生 draft tree；必须在界面点击批准后才分类。

Playwright 在本机开发服务完成以下真实操作：

- 打开模板页并读取 SQLite 中 24 套模板：`output/playwright/phase-04-templates.png`。
- 在规则页保存 `.tmp` 排除规则，刷新后的列表显示持久记录：`output/playwright/phase-04-rules.png`。
- 仅扫描 `artifacts/test-workspaces/phase-01-sample` 的直接文本文件；点击批准 T24 hash；显示 high 建议与真实 extracted_text：`output/playwright/phase-04-review.png`。
- 人工把该测试文件改为另一合法类别；UI 显示更新人工决定，而原 high 建议仍显示文本类别：`output/playwright/phase-04-review-saved.png`。

上述任务为 `report_only`，页面计数始终“已执行 0”，测试样本未移动或复制。

## 命令与结果

| 命令 | 退出结果 |
|---|---:|
| `python scripts/verify.py classification` | 0；11 passed |
| `uv run --all-extras pytest -q` | 0；102 passed，2 个已知 warning |
| `npm run typecheck` | 0 |
| `npm test -- --run` | 0；1 passed |
| `npm run build` | 0；1690 modules transformed |
| Playwright 模板/规则/批准树/人工审阅流程 | 0；4 张截图与可访问性快照 |

另有一次从项目根误运行 `uv run --all-extras pytest -q` 因根目录不是 Python project 而退出 1；随后在 `backend/` 正确重跑全量并通过，未将误命令写成通过。

## 下一恢复点

读取 `prompts/codex/05_MODELS_PRIVACY.md`。实现 DeepSeek 与 OpenAI-compatible Qwen transport、Windows 凭据存储、能力探测、OutboundEnvelope、逐任务 consent/预算/重试/取消。无真实 Key 或本地模型时以外部阻塞记录，不把测试假服务暴露为生产成功。
