# 从这个设计包开始开发

## 1. 文件放在哪里

新建一个专用项目文件夹，例如 `D:\Projects\Guixu`，把压缩包内的内容解压到这里。根目录应直接看到 `AGENTS.md`、`START_HERE.md`、`docs`、`contracts`、`seed`、`prompts`、`ui`；不要让 Codex 误把外层下载目录当成项目根目录。

若已有代码，把设计包放到独立工作副本后先让 Codex核对差异；不要覆盖已有 AGENTS.md、配置或用户改动。本设计默认从零开发，不假定已存在任何可用代码。

## 2. 推荐运行方式

在 Codex 中打开项目根目录，先使用 `prompts/codex/01_FOUNDATION.md` 的完整 Goal，完成基础闭环后再依次执行 02～09。每阶段都有明确产物、测试和禁止事项，便于控制额度、修正方向。

需要让 Codex连续推进时，使用 `prompts/codex/00_MASTER_GOAL.md`。这个总 Goal 会按同样九阶段推进，不要求每个阶段重新确认，但必须留下验收记录；权限、真实 Key、模型权重缺失等外部依赖必须如实报告，不能绕过。

`/goal` 是 Codex 的目标命令，不是 PowerShell 命令。官方提供 `/goal`、`/goal pause`、`/goal resume`、`/goal clear` 的生命周期控制；具体可用性取决于安装版本和使用界面。参考 docs/12_SOURCES_DECISIONS.md 的 S01。没有 Goal 命令的界面可以把同一目标作为普通任务输入，但不能声称具有完全相同的自动持续机制。

## 3. 开始前你实际需要准备的东西

开发阶段需要 Windows、Python 3.12.x、Node.js 22.12+ 的 22.x 版本线，以及允许 Codex在项目目录安装依赖。这里选择的是可复现基线，不是在声称这些是最新版本；第一阶段验证兼容后写入锁文件。

DeepSeek Key 可稍后通过应用的模型设置页输入；没有 Key 不影响基础开发、纯规则模式、离线假服务契约测试。真实云测试必须由你主动授权，并使用专门样例目录，不扫描桌面或下载目录。

Qwen3.8-27B 不需要在第一个开发阶段部署。应用只连接你后续启动的兼容推理服务，不负责下载几十 GB 权重、不自动改变 CUDA 环境，也不把模型塞进 EXE。

建议准备 `D:\GuixuTestData` 这样的测试副本目录。**真实个人文件不作为自动化测试素材。** 项目测试默认只写临时目录和 `artifacts/test-workspaces`。

## 4. 交给 Codex 的简短启动指令

```text
以当前目录为 Guixu 项目根目录。先阅读 AGENTS.md、START_HERE.md、docs/00_BLUEPRINT.md 和 PROJECT_STATUS.md，然后执行 prompts/codex/01_FOUNDATION.md 中的 Goal。不要只给我计划，要实际创建并验证代码。仅使用项目内测试文件，不碰真实个人目录；阶段完成后更新 PROJECT_STATUS.md 并生成阶段验收报告。
```

完整总 Goal 和各阶段 Goal 已单独提供，不需要一次性把所有设计文档粘贴到对话里。让 Codex按阶段定向读取，可以减少上下文和重复扫描。

## 5. 怎样判断真正完成

能在浏览器里展示页面，只说明 Web UI 可运行；不说明 Windows EXE 已验证。假服务测试通过，不说明 DeepSeek／本地 Qwen 真实联调通过。移动成功，不说明中断恢复与撤销已经可靠。发布阶段要求把这些维度分开写入报告。

本包的 SQL、JSON Schema、模板与接口是设计基线；开发实现后由真实类型与迁移生成产物并做一致性测试。不能让手写文档与实际 API 长期各自变化。
