# 归序 (Guixu) | AI File Organizer

[🇨🇳 中文](#-归序-guixu) | [🇬🇧 English](#-what-is-guixu)

---

# 🇨🇳 归序 (Guixu)

> 💾 **Windows 本地优先 AI 文件整理器**  
> 通过对话整理文件，而非盲目自动化。

[![Python](https://img.shields.io/badge/Python-77.9%25-3776ab?style=flat-square)](#-技术栈)
[![Vue](https://img.shields.io/badge/Vue-9.6%25-4FC08D?style=flat-square)](#-技术栈)
[![TypeScript](https://img.shields.io/badge/TypeScript-8.7%25-3178C6?style=flat-square)](#-技术栈)
[![Status](https://img.shields.io/badge/状态-0.9.0-blue?style=flat-square)](#-项目状态)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

![Windows x64](https://img.shields.io/badge/Windows%20x64-✓-brightgreen)
![AI驱动](https://img.shields.io/badge/AI%20驱动-DeepSeek%2FQwen-blue)
![开源](https://img.shields.io/badge/开源-MIT-green)

## ✨ 什么是归序？

**归序** 在 AI 辅助和人类控制之间找到平衡。与其盲目信任 AI 重新整理文件，你可以：

1. **对话讨论** 你的文件整理需求
2. **逐文件审阅** AI 生成的方案
3. **人工批准** 你认可的操作
4. **安全执行** 完整的审计链和撤销支持

所有数据保留本地。所有操作可追溯。AI 很聪明，但 **你掌控全局**。

```
📁 扫描目录
    ↓
💬 与 AI 对话
    ↓
👁️  预览方案
    ↓
✅ 人工批准
    ↓
🔄 安全执行（支持撤销）
```

## 🎯 核心特性

### 🤝 对话驱动的文件整理

- **自然语言规划**：与 DeepSeek 或本地 Qwen 讨论文件组织方式
- **多轮迭代**：提出后续要求、请求修改、生成 v2 方案
- **内容感知**：AI 理解文件内容（文本、OCR、图像描述）
- **证据可见**：每个分类都有明确的理由（文件名、内容、视觉线索）

### 🔒 隐私优先设计

- **本地优先**：默认所有数据本地存储，仅在选择云 AI 时上传
- **离线模式**：通过 Ollama 使用本地 Qwen，零网络访问
- **Key 隔离**：API Key 仅在内存中，不写入数据库、日志或浏览器
- **选择性共享**：仅发送元数据和摘要到 AI，绝不上传原始文件

### ✔️ 批准制执行

- **方案版本管理**：v1、v2 及修改对比
- **哈希验证**：每个批准的方案在执行前都经过密码学验证
- **不覆盖**：现有文件不会被无故覆盖
- **原子操作**：跨卷移动采用 Copy → Verify → Publish 模式

### 📋 完整审计链

- **操作日志**：每次移动/复制/删除都记录时间戳和用户批准
- **会话恢复**：关闭应用后，重新打开从原处继续
- **撤销支持**：执行后支持撤销（跨卷移动有限制）
- **决策历史**：查看每个文件为何被分类到某个位置

### 🎨 额外功能：AI 命名

基于内容证据生成智能文件名，批准后应用。

## 🚀 快速开始

### 系统要求

- **Windows 10/11 x64**
- **Python 3.12** + **Node.js 18+**（开发模式）
- **4GB RAM 最小**（8GB 推荐）

### 一键启动

```powershell
# 克隆并安装
git clone https://github.com/RXL333/Guixu.git
cd Guixu

# 自动环境检查
.\scripts\doctor.ps1

# 启动开发环境
.\scripts\run-dev.ps1
```

浏览器自动打开 **http://localhost:5173**，后端运行在随机安全端口。

### 便携包（普通用户看这里）

从 [Releases 页面](https://github.com/RXL333/Guixu/releases) 下载 **`Guixu-portable-x64-0.9.0.zip`**，
解压到任意目录，双击 `Guixu.exe`。不需要装 Python，不需要装 Node.js，不需要管理员权限。

> ⚠️ **Windows 会先拦住你，这是正常的。**
> 本项目没有购买代码签名证书，所以 SmartScreen 会显示「Windows 已保护你的电脑」。
> 确认发布者是你信任的来源后，点 **更多信息 → 仍要运行**。
> 这是未签名开源软件的通例，不是本项目的异常行为。

<details>
<summary><b>验证下载完整性（推荐）</b></summary>

每个 Release 都附 `SHA256SUMS.txt`，覆盖 app 内每一个文件。下载后在解压目录里核对：

```powershell
# 逐个文件比对；不匹配会打印出来
Get-FileHash -Algorithm SHA256 .\Guixu-0.9.0\Guixu.exe
```

或在 Release 页面直接核对压缩包本身的哈希。
</details>

<details>
<summary><b>关于杀毒软件误报</b></summary>

PyInstaller 打包的 Python 程序偶尔被启发式引擎误判。**请先核验 SHA256 再决定是否放行**，
不要直接加白名单。
</details>

### 仅桌面模式

```powershell
.\scripts\run-desktop.ps1
```

## 🧭 第一次使用

下载解压后第一次打开，按这个顺序走：

### 1. 配置模型连接

归序不内置任何模型，需要你自己接一个。二选一：

| | 归序做什么 | 你要准备什么 |
|---|---|---|
| **DeepSeek**（云端） | 发文件名、扩展名和**你勾选同意发送的内容/图片**去分类 | [platform.deepseek.com](https://platform.deepseek.com) 的 API Key |
| **本地 Qwen**（推荐，更私密） | 全部在本机推理，**文件不出你的电脑** | 先装 [Ollama](https://ollama.com)，再 `ollama pull qwen3-vl:4b-instruct` |

设置页填入 Base URL 和 Key 后，点「测试连接」。
**能力测试会如实显示文本/视觉是否可用**——不通就是不通，不会假装成功。

> 🔑 **API Key 不会**被写进仓库、日志、浏览器存储或任何导出报告。
> 也不要把你的 Key 填到 GitHub issue 里。

### 2. 授权一个文件夹

点「选择文件夹」，选你要整理的目录。

出于安全考虑，**系统目录和整个磁盘不允许被授权**（`C:\Windows`、`C:\Program Files`、
`C:\Users`、盘符根都会被拒绝）。你 profile 根目录本身也不允许，但
`Documents`、`Downloads`、`Pictures` 和任何项目子目录都正常可用——这正是产品要做的事。

### 3. 描述你要怎么分，然后**看预览**

用自然语言说要求（「按内容分类，别分太细」「截图和文档分开」）。
归序会给出**完整预览**：每个文件从哪来、到哪去、为什么。

> ⚠️ **这一步不动你的磁盘。** 预览出来之前不会有任何文件被移动。

### 4. 明确批准，才执行

看完预览，点「确认并开始整理」。**只有这一步会移动文件。**

对话里说「确认执行」「直接开始吧」这类话**不会**触发移动——
执行只能由你看得见的批准动作发起。这一点有 12 项测试守着。

### 数据存在哪

```
%LOCALAPPDATA%\Guixu\
├── app.sqlite3      会话、文件记录、方案版本、模型调用记录
├── backups\         自动备份
├── cache\           解析结果缓存（可安全删除，会重建）
└── diagnostics.json 诊断信息
```

**所有对话历史和审计记录都在这个数据库里。** 卸载便携包不会删它——
想彻底清除，手动删除这个目录即可。

## ⚠️ 已知限制

诚实列出当前版本做不到的事：

- **未做代码签名。** SmartScreen 会拦截，绕过步骤见上文。
- **单文件路径超过 260 字符的操作会失败。** 取决于你的卷是否启用了
  `LongPathsEnabled`（系统设置，需管理员 + 重启）。本项目的长路径用例在未启用的
  卷上会被跳过，不是通过。
- **同一 Windows 账户下无法构造「真实 ACL 拒绝」场景。** 你是文件的所有者，
  所有者权限始终有效，所以这条测试路径在本项目里不可验证。
- **Windows 凭据管理器未接入。** API Key 目前由应用自行管理存储，
  相关日志审计尚未覆盖（见 `RELEASE_ACCEPTANCE.md` 的 S17）。
- **只支持 Windows x64。** 没有 macOS/Linux 构建。
- **打包版真实模型链路未做完整验收。** 源码路径与冻结诊断均通过，
  但「打包版 → 建议确认 → 批准执行」的完整人工复测尚未覆盖。

完整的门禁状态见 [`docs/current/deployment/RELEASE_ACCEPTANCE.md`](docs/current/deployment/RELEASE_ACCEPTANCE.md)。

## 📸 工作流程

### 第一步：扫描与对话

```
✅ 选择授权目录
✅ 选择 AI 模型（DeepSeek 云或 Qwen 本地）
✅ 上传最多 3 张参考图片（可选）
✅ 描述你的文件整理需求
```

### 第二步：AI 规划

```
AI 分析：
  • 文件名和元数据
  • 内容（OCR、文本解析）
  • 嵌入图像和描述
  • 你上传的参考示例

生成方案 v1：
  ✓ 建议的类别
  ✓ 文件-类别映射
  ✓ 置信度评分
  ✓ 每个决策的依据
```

### 第三步：人工审阅与批准

```
每个文件显示：
  📄 当前位置：/path/to/file.ext
  🎯 建议位置：/Categories/Business/contract.pdf
  📝 理由：OCR 检测到内容包含"合同"
  ☑️ 操作：[移动] [跳过] [重命名]

批准、编辑或要求重新分类。
所有变更生成新的方案 v2。
```

### 第四步：执行与跟踪

```
✓ 方案哈希验证
✓ 原子执行（copy→verify→publish）
✓ 每个操作记入日志
✓ 实时进度更新

执行后：
  • 查看完成的操作
  • 撤销单个移动（有限制）
  • 继续聊天处理下一批文件
```

## 🏗️ 架构

### 本地优先单体设计

```
┌────────────────────────────────────┐
│   Guixu.exe                        │
│   (pywebview + EdgeChromium)       │
│   - 原生 Windows 窗口              │
│   - 无需外部浏览器                 │
└──────────────┬─────────────────────┘
               │
        ┌──────▼──────────────────────┐
        │  FastAPI 后端               │
        │  (localhost:随机端口)       │
        │                             │
        │  ✓ 会话管理                 │
        │  ✓ AI 编排                  │
        │  ✓ 文件操作                 │
        │  ✓ SQLite 持久化            │
        └──────┬──────────────────────┘
               │
        ┌──────▼──────────────────────┐
        │  Vue 3 前端                 │
        │  (TypeScript + Tailwind)    │
        │                             │
        │  ✓ 三栏布局                 │
        │  ✓ 实时同步                 │
        │  ✓ 方案编辑器               │
        │  ��� 操作预览                 │
        └─────────────────────────────┘
```

**数据**：SQLite 本地数据库，schema v11，完整迁移历史  
**API**：RESTful，OpenAPI 文档，契约在 `contracts/`  
**状态**：Pinia（前端）+ SQLAlchemy ORM（后端）

## 🧠 双模型支持

| | **DeepSeek（云）** | **Qwen（本地/Ollama）** |
|---|---|---|
| 速度 | ~2s/请求 | ~5-10s/请求 |
| 隐私 | 需授权协议 | 100% 离线 |
| 功能 | 文本 + 视觉 | 文本 + 视觉（预期） |
| 成本 | ¥0.5-2/100万字 | CPU/显存 |
| 设置 | API Key | Ollama `qwen:7b` |

**优雅降级**：DeepSeek 超时 → 自动切换 Qwen  
**用户控制**：每个会话选择模型，无强制默认

## 🔐 安全与隐私

### 核心保证

✅ **无自动执行** — 每个操作都需人工批准  
✅ **不上传文件** — 内容本地分析或仅发送摘要  
✅ **Key 不持久化** — API Key 仅在内存中  
✅ **路径隔离** — 跨目录访问严格禁止  
✅ **操作审计** — 所有移动/复制/删除永久记录  

### 安全机制

| 机制 | 保护 |
|------|------|
| **方案哈希** | 执行前检测篡改 |
| **不覆盖** | 现有文件不被无故覆盖 |
| **原子移动** | Copy → SHA-256 验证 → 原始删除 |
| **作用域验证** | 仅访问授权目录 |
| **软删除** | 操作可恢复直到硬清除 |

**运行审计**：`python .\scripts\audit_release_secrets.py`  
扫描 434 个文件、301MB 字节，检测 API key、硬编码密密、字符串注入。

## 📊 项目状态

**版本**：`0.9.0`  
**阶段**：功能完整开发，验收测试进行中

### ✅ 已完成

- 对话驱动规划
- 双 AI 模型适配（DeepSeek + Qwen）
- 方案版本管理与批准工作流
- 文件证据与内容解析
- 安全执行与审计日志
- 会话恢复与撤销支持
- Windows onedir + 便携包构建
- 198+ 后端测试，40+ 前端测试
- 完整 E2E：5 图片 v1→v2→执行→恢复

### ⚠️ 已知限制

- **暂无安装器**（Inno Setup 待开发）
- **需要代码签名**（生产环保需要）
- **本地 Qwen 视觉** — 仅验证文本，视觉管道进行中
- **高 DPI 显示器** — 4K 缩放未充分测试
- **监控文件夹** — 自动监听未实现
- **可选：ffmpeg/ASR** — 音频转录需外部设置

**完整详情**：[docs/product/limitations.md](docs/product/limitations.md)

## 💻 开发

### 项目结构

```
Guixu/
├── backend/              # Python FastAPI，198+ 测试
├── frontend/             # Vue 3 + TypeScript，40+ 测试
├── docs/
│   ├── product/         # 功能、工作流、隐私
│   ├── current/         # 架构、决策、API
│   ├── development/     # 设置、测试、打包
│   └── archive/         # 历史设计（参考用）
├── contracts/           # OpenAPI、数据库 DDL
├── scripts/             # 构建、测试、验证自动化
└── seed/                # 运行时数据（分类法、提示词）
```

### 基础命令

```powershell
# 后端测试
cd backend && uv run pytest -q          # 198 测试
cd backend && uv run pytest tests/test_scanner.py  # 单个模块

# 前端测试
cd frontend && npm run test:run          # 40+ 测试
cd frontend && npm run typecheck        # 类型检查

# 全量验证（测试 + 类型 + 构建）
python .\scripts\verify.py all

# 构建便携包
.\scripts\package-windows.ps1
```

### 技术栈

| 层 | 技术 |
|----|------|
| **后端** | Python 3.12、FastAPI、SQLAlchemy、Pydantic |
| **前端** | Vue 3、TypeScript、Vite、Pinia、TailwindCSS |
| **桌面** | pywebview、EdgeChromium |
| **数据库** | SQLite、Alembic 迁移 |
| **AI API** | DeepSeek HTTP、Ollama 本地 |
| **测试** | pytest、Vitest、E2E 烟雾测试 |

## 🤝 贡献

### 提交前检查

```powershell
python .\scripts\verify.py all    # 所有测试必须通过
cd backend && uv run ruff check .
cd frontend && npm run lint
```

### PR 流程

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 为更改添加测试
4. 运行验证（见上文）
5. 推送并开启 PR 并附带描述

## 📚 文档

| 链接 | 用途 |
|------|------|
| [docs/product/](docs/product/) | **用户指南**：功能、工作流、限制 |
| [docs/development/](docs/development/) | **开发设置**：快速开始、测试、打包 |
| [docs/current/](docs/current/) | **架构**：数据模型、API、决策 |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | **实时状态**：阶段进度、测试结果、阻塞项 |
| [contracts/](contracts/) | **API & DB**：OpenAPI、DDL |

## 🎓 了解更多

### 架构问答

**Q：为什么要本地优先？**  
A：你的文件保留在你的机器上。仅元数据发送给 AI（如果选择云模型）。无追踪，无分析。

**Q：如果我不同意 AI 的方案怎么办？**  
A：编辑它。更改类别、重命名文件、跳过操作。新方案 v2 反映你的变更。

**Q：可以撤销操作吗？**  
A：可以，有限制。单卷移动可以干净撤销。跨卷移动需要原始状态验证。

**Q：为什么有这么多测试？**  
A：文件整理风险很高。一个错误会丢失数据。我们测试每个代码路径、真实 AI、真实文件。

### 真实案例

```
目标：组织 48 张最近旅行的照片

1. 创建会话，授权 ~/Pictures/2024-Trip/
2. 对话："按位置和日期整理这些照片"
3. AI 审阅文件名、EXIF 数据、图像内容
4. 方案 v1：12 个类别（海滩、森林、人物、美食等）
5. 你审阅："合并海滩和水"、"添加人物/集体"
6. 生成方案 v2 包含你的修改
7. 批准并执行 → 48 张照片在 <5s 内移动
8. 审阅操作日志 → 所有 48 个文件已跟踪
9. 关闭应用 → 次日重新打开，会话完整
```

## 📦 部署

### 对于用户

**推荐**：从 [Release](../../releases) 下载便携 ZIP  
解压，运行 `Guixu.exe`，无需依赖。

**替代方案**：从源码构建
```powershell
.\scripts\package-windows.ps1
# 创建：artifacts/release/Guixu-0.9.0/Guixu.exe
```

### 对于开发者

```powershell
# 开发模式（热重载）
.\scripts\run-dev.ps1

# 桌面构建（pywebview）
.\scripts\run-desktop.ps1

# 生产包
.\scripts\package-windows.ps1
```

## 🐛 反馈与问题

发现 Bug？有想法？

- 🐞 [开启 Issue](../../issues)
- 💬 [开启讨论](../../discussions)
- 📖 [查看文档](docs/)

---

# 🇬🇧 Guixu

> 💾 **Local-First AI File Organizer for Windows**  
> Organize your files through conversation, not automation.

[![Python](https://img.shields.io/badge/Python-77.9%25-3776ab?style=flat-square)](#-tech-stack)
[![Vue](https://img.shields.io/badge/Vue-9.6%25-4FC08D?style=flat-square)](#-tech-stack)
[![TypeScript](https://img.shields.io/badge/TypeScript-8.7%25-3178C6?style=flat-square)](#-tech-stack)
[![Status](https://img.shields.io/badge/Status-0.9.0-blue?style=flat-square)](#-project-status)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

![Windows x64](https://img.shields.io/badge/Windows%20x64-✓-brightgreen)
![AI Powered](https://img.shields.io/badge/AI%20Powered-DeepSeek%2FQwen-blue)
![Open Source](https://img.shields.io/badge/Open%20Source-MIT-green)

## ✨ What is Guixu?

**Guixu** bridges AI assistance and human control in file organization. Instead of blindly trusting AI to reorganize your files, you:

1. **Discuss** your filing needs in natural conversation
2. **Review** the AI-generated plan file-by-file
3. **Approve** only what you're comfortable with
4. **Execute** with full audit trail and undo support

All data stays local. All operations are traceable. AI is smart, but *you* stay in control.

```
📁 Scan Directory
    ↓
💬 Discuss with AI
    ↓
👁️  Preview Plan
    ↓
✅ Approve Manually
    ↓
🔄 Execute Safely (with undo)
```

## 🎯 Key Features

### 🤝 Conversation-Driven Organization

- **Natural language planning**: Talk to DeepSeek or local Qwen about how you want to organize
- **Multi-turn refinement**: Ask follow-ups, request changes, generate v2 plans
- **Context-aware**: AI understands file content (text, OCR, image descriptions)
- **Evidence-based**: Every classification has a visible reason (filename, content, visual cues)

### 🔒 Privacy-First Design

- **100% local-by-default**: No file uploads unless you choose cloud AI
- **Qwen offline mode**: Use local models via Ollama, zero network access
- **API key isolation**: Keys never touch database, logs, or browser storage
- **Selective sharing**: Only metadata and summaries go to AI, never full file content

### ✔️ Approval-Based Execution

- **Plan versioning**: Compare v1, v2, modifications side-by-side
- **Hash verification**: Every approved plan is cryptographically validated before execution
- **No clobber**: Existing files are never silently overwritten
- **Atomic operations**: Copy → Verify → Publish pattern for cross-drive safety

### 📋 Full Audit Trail

- **Operation logs**: Every move/copy/delete recorded with timestamp and user approval
- **Session recovery**: Close app and resume exactly where you left off
- **Undo support**: Revert execution (with caveats for cross-drive moves)
- **Decision history**: See why each file was categorized a certain way

### 🎨 Bonus: AI-Powered Naming

Generate smart file names based on content evidence, approve before applying.

## 🚀 Quick Start

### Requirements

- **Windows 10/11 x64**
- **Python 3.12** + **Node.js 18+** (dev mode)
- **4GB RAM minimum** (8GB recommended)

### One-Click Setup

```powershell
# Clone and install
git clone https://github.com/RXL333/Guixu.git
cd Guixu

# Auto environment check
.\scripts\doctor.ps1

# Start dev environment
.\scripts\run-dev.ps1
```

Browser opens to **http://localhost:5173**, backend runs on a random secure port.

### Portable Package

Download from [Releases](https://github.com/RXL333/Guixu/releases): **Guixu-portable-x64-0.9.0.zip**  
Unzip anywhere and run `Guixu.exe` — no Python, no Node.js, no administrator rights.

> ⚠️ **Windows will block this at first, and that is expected.**
> The project carries no code-signing certificate, so SmartScreen shows
> "Windows protected your PC". After confirming you trust the source, click
> **More info → Run anyway**. This is normal for unsigned open-source software.

<details>
<summary><b>Verify the download</b></summary>

Every release ships a `SHA256SUMS.txt` covering every file in the app. Check it in the
extracted directory, or compare the archive hash on the Releases page.
</details>

<details>
<summary><b>First run</b></summary>

1. **Connect a model** — either DeepSeek (cloud; send it your API key) or local Qwen
   via Ollama (recommended; nothing leaves your machine). The capability test reports
   text/vision honestly — it will not pretend to work.
2. **Authorize a folder** — system directories and drive roots are refused by design;
   your profile root too, but `Documents`, `Downloads` and any project folder work.
3. **Describe what you want**, then read the preview. **Nothing moves yet.**
4. **Approve explicitly to execute.** Saying "确认执行" in the chat does *not* move
   files — 12 tests hold that line.

Data lives in `%LOCALAPPDATA%\Guixu\` (`app.sqlite3`, `backups\`, `cache\`).
Deleting that directory removes all history.
</details>

### Desktop-Only Mode

```powershell
.\scripts\run-desktop.ps1
```

## 📸 How It Works

### Phase 1: Scan & Discuss

```
✅ Select authorized directory
✅ Choose AI model (DeepSeek cloud or Qwen local)
✅ Upload up to 3 reference images (optional)
✅ Describe your filing needs
```

### Phase 2: AI Planning

```
AI analyzes:
  • File names and metadata
  • Content (OCR, text parsing)
  • Embedded images and descriptions
  • Your reference examples

Generates Plan v1:
  ✓ Proposed categories
  ✓ File-to-category mapping
  ✓ Confidence scores
  ✓ Evidence for each decision
```

### Phase 3: Manual Review & Approval

```
For each file, you see:
  📄 Current: /path/to/file.ext
  🎯 Proposed: /Categories/Business/contract.pdf
  📝 Why: OCR detected "contract" in content
  ☑️ Action: [Move] [Skip] [Rename]

Approve, edit, or request re-classification.
All changes generate new Plan v2.
```

### Phase 4: Execute & Track

```
✓ Plan hash verified
✓ Atomic execution (copy→verify→publish)
✓ Every operation logged
✓ Live progress updates

Post-execution:
  • Review completed operations
  • Undo individual moves (with caveats)
  • Continue chatting for next batch
```

## 🏗️ Architecture

### Monolithic Local-First Design

```
┌─────────��──────────────────────────┐
│   Guixu.exe                        │
│   (pywebview + EdgeChromium)       │
│   - Native Windows window          │
│   - No external browser needed     │
└──────────────┬─────────────────────┘
               │
        ┌──────▼──────────────────────┐
        │  FastAPI Backend            │
        │  (localhost:random_port)    │
        │                             │
        │  ✓ Session management       │
        │  ✓ AI orchestration         │
        │  ✓ File operations          │
        │  ✓ SQLite persistence       │
        └──────┬──────────────────────┘
               │
        ┌──────▼──────────────────────┐
        │  Vue 3 Frontend             │
        │  (TypeScript + Tailwind)    │
        │                             │
        │  ✓ 3-column layout          │
        │  ✓ Real-time sync           │
        │  ✓ Plan editor              │
        │  ✓ Operation preview        │
        └─────────────────────────────┘
```

**Data**: SQLite local database, schema v11, full migration history  
**APIs**: RESTful, OpenAPI documented, contracts in `contracts/`  
**State**: Pinia (frontend) + SQLAlchemy ORM (backend)

## 🧠 Dual AI Model Support

| | **DeepSeek (Cloud)** | **Qwen (Local/Ollama)** |
|---|---|---|
| Speed | ~2s/request | ~5-10s/request |
| Privacy | Need auth agreement | 100% offline |
| Features | Text + Vision | Text + Vision (preview) |
| Cost | ¥0.5-2/1M chars | CPU/VRAM only |
| Setup | API Key | Ollama `qwen:7b` |

**Graceful degradation**: DeepSeek timeout → auto-fallback to Qwen  
**User control**: Choose model per session, no forced defaults

## 🔐 Security & Privacy

### Core Guarantees

✅ **No automatic execution** — every operation needs human approval  
✅ **No file uploads** — content analyzed locally or via summaries only  
✅ **No key storage** — API keys live in memory, never persisted  
✅ **Path isolation** — cross-directory access strictly forbidden  
✅ **Operation audit** — all moves/copies/deletes logged permanently  

### Safety Mechanisms

| Mechanism | Protection |
|-----------|-----------|
| **Plan hash** | Tampering detection before execution |
| **No clobber** | Existing files never overwritten |
| **Atomic moves** | Copy → SHA-256 verify → original delete |
| **Scope validator** | Authorized directories only |
| **Soft delete** | Operations recoverable until hard-purge |

**Run audit**: `python .\scripts\audit_release_secrets.py`  
Scans 434 files, 301MB bytes for API keys, hardcoded secrets, string injections.

## 📊 Current Status

**Version**: `0.9.0`  
**Stage**: Feature-complete development, acceptance testing in progress

### ✅ Completed

- Conversation-driven planning
- Dual AI model adapters (DeepSeek + Qwen)
- Plan versioning with approval workflow
- File evidence & content parsing
- Safe execution with audit logging
- Session recovery & undo support
- Windows onedir + portable build
- 291 backend tests, 67 frontend tests
- Full E2E flow: 5-image v1→v2→execute→recover

### ⚠️ Known Limitations

Stated plainly, because a release note that overstates readiness is worse than one
that admits its edges:

- **Unsigned.** SmartScreen intercepts the first launch; bypass steps are above.
- **Paths over 260 characters fail** unless the volume has `LongPathsEnabled`
  (a system setting needing admin rights and a reboot). The long-path test is
  *skipped* on volumes without it — not passing.
- **A real ACL-denial scenario is not constructible** under a single Windows
  account: you own your files, so owner rights always apply.
- **Windows Credential Manager is not integrated.** API key storage is
  app-managed, and its log audit is not yet covered (S17 in the acceptance doc).
- **Windows x64 only.** No macOS or Linux build.
- **The packaged build's end-to-end model chain has not been fully re-verified
  by hand.** Source paths and the frozen diagnostic pass; the complete
  "packaged → confirm suggestion → approve → execute" run is still uncovered.

Feature-level limitations (watch folder, audio transcription) are unchanged.
**Full details**: [docs/product/limitations.md](docs/product/limitations.md)

## 💻 Development

### Project Structure

```
Guixu/
├── backend/              # Python FastAPI, 291 tests
├── frontend/             # Vue 3 + TypeScript, 67 tests
├── docs/
│   ├── product/         # Features, workflows, privacy
│   ├── current/         # Architecture, decisions, API
│   ├── development/     # Setup, testing, packaging
│   └── archive/         # Historical designs (reference only)
├── contracts/           # OpenAPI, database DDL
├── scripts/             # Build, test, verify automation
└── seed/                # Runtime data (taxonomies, prompts)
```

### Essential Commands

```powershell
# Backend tests
cd backend && uv run pytest -q          # 198 tests
cd backend && uv run pytest tests/test_scanner.py  # Single module

# Frontend tests
cd frontend && npm run test:run          # 40 tests
cd frontend && npm run typecheck        # Type checking

# Full validation (tests + types + build)
python .\scripts\verify.py all

# Build portable package
.\scripts\package-windows.ps1
```

### Tech Stack

| Layer | Tech |
|-------|------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy, Pydantic |
| **Frontend** | Vue 3, TypeScript, Vite, Pinia, TailwindCSS |
| **Desktop** | pywebview, EdgeChromium |
| **Database** | SQLite, Alembic migrations |
| **AI APIs** | DeepSeek HTTP, Ollama local |
| **Testing** | pytest, Vitest, E2E smoke tests |

## 🤝 Contributing

### Before You PR

```powershell
python .\scripts\verify.py all    # All tests must pass
cd backend && uv run ruff check .
cd frontend && npm run lint
```

### PR Process

1. Fork this repo
2. Create feature branch: `git checkout -b feature/your-feature`
3. Add tests for your changes
4. Run validation (see above)
5. Push and open PR with description

## 📚 Documentation

| Link | Purpose |
|------|---------|
| [docs/product/](docs/product/) | **User Guide**: Features, workflows, limitations |
| [docs/development/](docs/development/) | **Dev Setup**: Getting started, testing, packaging |
| [docs/current/](docs/current/) | **Architecture**: Data models, API, decisions |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | **Live Status**: Phase progress, test results, blockers |
| [contracts/](contracts/) | **API & DB**: OpenAPI spec, DDL |

## 🎓 Learn More

### Architecture Q&A

**Q: Why local-first?**  
A: Your files stay on your machine. Only metadata goes to AI (if you choose cloud models). No tracking, no profiling.

**Q: What happens if I disagree with the AI plan?**  
A: You edit it. Change categories, rename files, skip operations. New Plan v2 reflects your changes.

**Q: Can I undo operations?**  
A: Yes, with caveats. Single-drive moves undo cleanly. Cross-drive moves require original state verification.

**Q: Why is there so much testing?**  
A: File organization is high-risk. One mistake loses data. We test every code path, real AI, real files.

### Real-World Example

```
Goal: Organize 48 photos from a recent trip

1. Create session, authorize ~/Pictures/2024-Trip/
2. Chat: "Sort these by location and date"
3. AI reviews file names, EXIF data, image content
4. Plan v1: 12 categories (Beach, Forest, People, Food, etc.)
5. You review: "Merge Beach + Water", "Add People/Group"
6. Plan v2 generated with your changes
7. Approve and execute → 48 photos moved in <5s
8. Review operation log → all 48 files tracked
9. Close app → reopen next day, session intact
```

## 📦 Deployment

### For Users

**Recommended**: Download portable ZIP from [Releases](../../releases)  
Unzip, run `Guixu.exe`, no dependencies needed.

**Alternative**: Build from source
```powershell
.\scripts\package-windows.ps1
# Creates: artifacts/release/Guixu-0.9.0/Guixu.exe
```

### For Developers

```powershell
# Development mode (hot reload)
.\scripts\run-dev.ps1

# Desktop build (pywebview)
.\scripts\run-desktop.ps1

# Production package
.\scripts\package-windows.ps1
```

## 🐛 Feedback & Issues

Found a bug? Have an idea?

- 🐞 [Open an Issue](../../issues)
- 💬 [Start a Discussion](../../discussions)
- 📖 [Check Docs](docs/)

## 📄 License

MIT © 2024–Present. See [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [DeepSeek API](https://deepseek.com) — Powerful multimodal AI
- [Ollama](https://ollama.ai) — Local model runtime
- [FastAPI](https://fastapi.tiangolo.com) — Modern Python web
- [Vue 3](https://vuejs.org) — Progressive frontend framework
- [pywebview](https://github.com/r0x0r/pywebview) — Desktop app bridge

---

<div align="center">

**中文** | **[English](#-what-is-guixu)**

**[🚀 Get Started](#-quick-start)** · **[📚 Read Docs](docs/)** · **[💬 Discuss](../../discussions)** · **[⭐ Star](../../)**

Made with ❤️ for better file organization | 为更好的文件整理而打造

</div>
