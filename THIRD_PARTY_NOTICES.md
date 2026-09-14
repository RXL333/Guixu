# Third-party notices

归序 0.1.0 使用 `backend/uv.lock` 与 `frontend/package-lock.json` 锁定的第三方软件。构建生成的 `artifacts/release/SBOM.json` 列出实际解析版本及可读取的许可证元数据；发布前仍需人工复核原始许可证全文与再分发条件。

主要运行时组件包括 FastAPI、Uvicorn、SQLAlchemy、Alembic、Pydantic、platformdirs、pywebview/pythonnet、Pillow、pypdf/pypdfium2、python-docx、python-pptx、openpyxl、RapidOCR、ONNX Runtime、psutil、httpx、jsonschema、Vue、Vue Router、Pinia、Naive UI 与 Lucide。各组件版权归其作者所有，本文件不改变其许可证。

Microsoft Edge WebView2 Runtime 不包含在当前仓库或便携包内，由 Microsoft 按其条款独立提供。ffmpeg/ffprobe、ASR 模型、Qwen 权重与 CUDA 未捆绑。任何后续离线组件包必须另附来源、版本、逐文件 SHA-256 和许可来源。

本项目自身许可证尚未由所有者声明，因此当前产物不是公开发行授权声明。
