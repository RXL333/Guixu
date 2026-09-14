# 阶段09｜Windows发行交付

```text
/goal 完成归序阶段09 Windows打包与可复现交付。读取docs/10_RELEASE.md、09_TESTING.md、PROJECT_STATUS与阶段08发布清单，先核对安全门禁，不绕过未通过项。

在Windows构建前端静态资源、Python冻结产物和PyInstaller onedir，验证主程序/worker入口不会互相启动GUI。写可复现打包脚本和资源路径解析，数据保存用户AppData不写安装目录。不要改文件扩展名冒充EXE，不在Linux宣称完成Windows实机打包。

用Inno Setup生成安装程序；处理WebView2检测与用户知情安装，在线/离线资源包区别明确。ffmpeg/OCR等资源来源、版本、hash、许可有清单，可选ASR单独资源包；不捆绑Qwen权重/CUDA，不默默下载大文件。

在没有Python/Node的干净Windows用户环境验证安装、首次启动、中文路径、纯规则离线模式、组件缺失、模型连接配置、测试样本整理/撤销、关闭恢复、升级/卸载保留数据。提供onedir时必须整个目录交付，不能只发孤立exe。

补齐用户手册、开发启动/测试/打包指南、架构/契约同步、CHANGELOG、KNOWN_LIMITATIONS、THIRD_PARTY_NOTICES、发行校验值。运行最终测试并附产物实际路径。签名证书没有就说明未签名，不申请提权或绕过系统安全警告。

缺Windows或发行资源时，交付已验证源码/脚本与具体BLOCKED_EXTERNAL、后续需要的动作；不能把“脚本存在”算“EXE测试通过”。最终更新phase-09.md、PROJECT_STATUS与release-readiness.md，明确哪些产物真正可运行、哪些仍需外部验证。
```
