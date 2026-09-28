# 发布与验收

当前是 `0.1.0 dev`，尚未满足 1.0 发布门。以[验收矩阵](../current/deployment/RELEASE_ACCEPTANCE.md)和 [PROJECT_STATUS.md](../../PROJECT_STATUS.md)为准。

Windows 包必须在 Windows x64 构建。安装、首次启动、中文路径、备份副本上的 copy/move/undo、恢复、升级和卸载保留数据需要分别留证。没有证书标注未签名；未运行的桌面或干净机测试不能写成通过。

安装默认为当前用户，不自动清除 `%LOCALAPPDATA%\Guixu`。WebView2 离线安装包须从官方渠道另行取得并记录版本、哈希及许可。
