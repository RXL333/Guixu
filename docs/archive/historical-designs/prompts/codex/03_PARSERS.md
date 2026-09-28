# 阶段03｜本地多模态解析

```text
/goal 完成归序阶段03本地解析器、资源组件管理与统一FileProfile。读取AGENTS.md、PROJECT_STATUS、docs/02_ARCHITECTURE.md、05_AI_PIPELINE.md、09_TESTING.md及file-profile schema。

实现ParserRegistry与独立worker执行边界，实际格式判定、限时、限内存/像素/解压量、缓存与取消。文本支持TXT/MD/JSON/CSV；PDF区分可提取文字和扫描页；DOCX/PPTX/XLSX按结构抽取，不执行公式/宏/嵌入对象。图片提取尺寸/方向/受控EXIF并生成去EXIF缩略图；RapidOCR使用本地已校验资源。GIF采样多帧。

ffprobe读取音视频元信息，ffmpeg按fast/standard/deep策略抽帧/音轨；可选faster-whisper CPU INT8本地转写。文件没有语音不等于音乐，失败不得编造字幕。所有page/frame/time/row位置和覆盖率进入FileProfile证据；不以首段代整份文档。

实现组件状态与资源包导入，验证manifest/hash/路径，不执行包内脚本。缺少ffmpeg/OCR/ASR时显示具体不可用能力，元数据仍可用。不偷偷下载模型，不安装GPU CUDA，不把Qwen权重放入项目。

用有效真实小样本通过PA01～PA12和JSON Schema。含中文名、损坏文件、加密PDF、超大图、无语音、扫描页、格式伪装；所有样本均测试副本或自造许可清晰内容。前端能查看真实提取片段与采样提示，解析超时不锁死主窗。

生成phase-03.md与样本manifest，列明完整/部分/不支持/缺组件的真实状态；更新PROJECT_STATUS。不要将空白伪格式文件当成支持证据。
```
