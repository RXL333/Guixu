# 已知限制（0.1.0 dev）

- 生产 `direct_move` 关闭；请先用 `report_only` 或备份副本上的 `copy`。
- 未获授权的真实 DeepSeek Key 与 Qwen 服务，尚无现实语义准确率／公平对比结果。
- 当前发行未捆绑 ffmpeg/ffprobe 或 ASR 模型；视频和语音内容分析会 `partial`/弃判。
- OCR 只对锁定 RapidOCR/ONNX Runtime 组合做了本机构建验证；复杂手写、低质量扫描不承诺精度。
- pywebview 高 DPI、多显示器、Windows 10/Server/LTSC 与无 WebView2 路径尚待干净环境人工矩阵。
- 物理卷断开、云占位文件、网络盘/UNC 和第三方同步客户端冲突仍需专用环境。
- 安装程序只有本机存在 Inno Setup 6 时才生成；没有代码签名证书，产物会触发 Windows 信誉提示。
- 没有自动更新；升级使用新安装包。卸载默认保留数据，清理数据需用户另行明确操作。
- 项目源码尚未声明对外发布许可证；在所有者选定许可证前，构建产物只用于本项目验收，不应公开再分发。
