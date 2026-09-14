# 可选组件包格式

归序安装包不包含 Qwen 权重、CUDA、未知驱动或任意安装脚本。ffmpeg、OCR、ASR 的离线组件须由用户单独取得并审阅许可，解压到普通目录后通过应用显式导入。

`manifest.json` 必须包含：

```json
{
  "component_id": "vendor-component-version-x64",
  "component_type": "ffmpeg",
  "version": "actual-version",
  "platform": "windows",
  "arch": "x64",
  "relative_files": [
    {"path": "bin/ffmpeg.exe", "sha256": "64 lowercase hex characters"}
  ],
  "license_source": "https://vendor.example/license",
  "entry_paths": ["bin/ffmpeg.exe"]
}
```

导入器拒绝绝对路径、`..`、symlink/reparse point、脚本后缀、缺失文件、hash 不符、超过 2,000 文件或总计超过 4 GiB 的包。当前仓库没有下载或捆绑 ffmpeg/ASR；OCR 来自锁定 Python 依赖，构建时将实际模型文件收进 onedir。
