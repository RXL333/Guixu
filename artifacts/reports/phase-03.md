# 阶段 03 验收报告：本地多模态解析与资源组件

日期：2026-09-13  
环境：Windows 11 x64；Python 3.12.10；RapidOCR 3.9.2 + ONNX Runtime CPU；无 ffmpeg/ffprobe；无 ASR 本地模型

## 结论

统一 `FileProfile`、格式签名校验、独立 worker、内容寻址缓存、超时/内存/取消边界、结构化解析器、经固定 SHA-256 校验的 RapidOCR CPU、本地缩略图、组件状态/资源包导入、档案持久化 API 和证据查看界面均已实现。测试材料全部在 pytest 临时目录中确定性生成，未读取用户个人文件。

阶段状态记为 **BLOCKED_EXTERNAL（核心解析与 OCR 通过）**：本机没有 ffmpeg/ffprobe，也没有已授权的 faster-whisper 本地模型。音频与视频因此只返回真实可得的元数据及明确缺组件告警；没有伪造字幕、转写或视频帧。PA08 的实际 MP4 已生成并验证为非空容器，但均匀抽帧仍待 ffmpeg 资源组件。

## PA01～PA12

| 编号 | 结果 | 真实证据 |
|---|---|---|
| PA01 | PASS | 中文 TXT、Markdown、JSON、CSV 均解析为带 paragraph/row/field 定位的证据 |
| PA02 | PASS | reportlab 文本 PDF；Pillow 图像 PDF 经 pypdfium2 渲染并由本地 OCR 识别；加密 PDF 明确 partial |
| PA03 | PASS | python-docx 实际表格/段落；python-pptx 实际标题与正文 |
| PA04 | PASS | openpyxl read-only；公式仅标为 `FORMULA_NOT_EXECUTED`，不计算、不执行宏/对象 |
| PA05 | PASS | JPEG 实际 OCR；方向处理；生成 JPEG 缩略图复查无 EXIF；GPS 不进入 metadata |
| PA06 | PASS | 五帧 GIF 分层取首/中/尾三帧并标记 sampled |
| PA07 | PARTIAL_EXTERNAL | 一秒真实静音 WAV 头与时长通过；ASR 模型缺失，明确 `ASR_COMPONENT_MISSING`，无 transcript |
| PA08 | PARTIAL_EXTERNAL | OpenCV 实际编码 15 帧 MP4；ffprobe/ffmpeg 缺失，明确 metadata-only，不宣称抽帧通过 |
| PA09 | PASS | 20 页真实 PDF 的 fast 策略稳定抽取 1/7/14/20 页并标记 truncated |
| PA10 | PASS | 64,016,001 像素 PNG、假 PDF、加密 PDF、压缩膨胀 DOCX 均受控拒绝或降级 |
| PA11 | PASS | OCR ready、ASR missing/disabled、ffmpeg missing 状态可查询；导入校验 manifest/逐文件 hash/相对路径/reparse/大小并拒绝脚本 |
| PA12 | PASS | 睡眠 worker 在 0.2 秒超时后仅杀死其拥有的进程树；主测试进程继续运行 |

所有成功/partial/failed 的 `FileProfile` 测试均通过 `contracts/schemas/file-profile.schema.json` Draft 2020-12 + UUID format 校验。

## 关键安全实现

- 扩展名之外校验 PDF、OOXML、图片与文本签名；伪装格式返回 `FORMAT_SIGNATURE_MISMATCH`。
- OOXML 在打开前限制条目数、展开字节、压缩比和路径；不执行公式、宏或嵌入对象。
- Pillow 像素上限 64 MP；缩略图统一转码且不复制 EXIF。
- RapidOCR 仅在版本为 3.9.2 且三个本地 ONNX 文件命中固定 SHA-256 后初始化；不传 URL 或模型短名。
- worker 输出上限 2 MiB，默认 120 秒和 768 MiB RSS 上限；超时、取消、超内存均只清理自有进程树。
- 缓存键为内容 SHA-256 + parser version + options hash；Windows 文件名再哈希以规避 MAX_PATH；跨文件命中会重绑定当前 `file_id`。
- 组件导入使用显式 `component_import` grant；拒绝绝对路径、`..`、symlink/reparse、脚本、文件/总量超限或任一 hash 不符；导入过程不执行包内容。

## 运行命令与结果

| 命令 | 退出结果 |
|---|---:|
| `python scripts/verify.py parsers` | 0；14 passed（12 parser + 2 API integration） |
| `uv run --all-extras pytest -q` | 0；93 passed，2 个已知 warning |
| `npm run typecheck` | 0 |
| `npm test -- --run` | 0；1 passed |
| `npm run build` | 0；1686 modules transformed |

两个 warning 分别为 Starlette 测试客户端弃用提示，以及超大图防护测试故意触发的 Pillow decompression-bomb warning；均未被写成失败或忽略。

## 产物

- `backend/src/guixu/infrastructure/parsers/`：文本、文档、图片、OCR、媒体、注册表
- `backend/src/guixu/application/parser_runner.py`：worker 生命周期与缓存
- `backend/src/guixu/infrastructure/resources/components.py`：组件检测和资源包导入
- `backend/src/guixu/application/parsing.py`：解析档案持久化服务
- `/api/v1/components`、`/api/v1/components/import`、文件详情与 reanalyze API
- `frontend/src/pages/TaskScanPage.vue`：真实证据、定位、覆盖率、采样和告警面板
- `artifacts/samples/phase-03-expected-manifest.json`：确定性样本用途和预期
- `backend/uv.lock`：包含 OCR 可选依赖的精确解析锁

## 外部阻塞与下一恢复点

- ffmpeg/ffprobe：PATH 中均不存在；视频均匀抽帧、音轨抽取与 ffprobe 元信息未验证。
- ASR：未安装/导入已校验 faster-whisper 本地模型；真实语音转写未验证。
- 未下载大型模型、未安装 CUDA、未把 Qwen 权重放入项目。

下一阶段读取 `prompts/codex/04_CLASSIFICATION.md`，实现模板/规则、受限分类契约和确定性目录树；上述媒体组件缺口不阻塞纯文本、规则和分类安全边界。
