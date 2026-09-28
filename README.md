# 归序 (Guixu) | AI File Organizer

[🇨🇳 中文](#-归序-guixu) | [🇬🇧 English](#-what-is-guixu)

---

# 🇨🇳 归序 (Guixu)

> 💾 **Windows 本地优先 AI 文件整理器**  
> 通过对话整理文件，而非盲目自动化。

[![Python](https://img.shields.io/badge/Python-77.9%25-3776ab?style=flat-square)](#-技术栈)
[![Vue](https://img.shields.io/badge/Vue-9.6%25-4FC08D?style=flat-square)](#-技术栈)
[![TypeScript](https://img.shields.io/badge/TypeScript-8.7%25-3178C6?style=flat-square)](#-技术栈)
[![Status](https://img.shields.io/badge/状态-0.1.0%20dev-orange?style=flat-square)](#-项目状态)
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

### 便携包

从 [Release 页面](../../releases) 下载：**Guixu-portable-x64-0.1.0.zip**  
解压即用 — 无需安装。

### 仅桌面模式

```powershell
.\scripts\run-desktop.ps1
```

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

**版本**：`0.1.0 dev`  
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
# 创建：artifacts/release/Guixu-0.1.0/Guixu.exe
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
[![Status](https://img.shields.io/badge/Status-0.1.0%20dev-orange?style=flat-square)](#-project-status)
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

Download from [Releases](../../releases): **Guixu-portable-x64-0.1.0.zip**  
Unzip and run — no installation needed.

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

**Version**: `0.1.0 dev`  
**Stage**: Feature-complete development, acceptance testing in progress

### ✅ Completed

- Conversation-driven planning
- Dual AI model adapters (DeepSeek + Qwen)
- Plan versioning with approval workflow
- File evidence & content parsing
- Safe execution with audit logging
- Session recovery & undo support
- Windows onedir + portable build
- 198+ backend tests, 40+ frontend tests
- Full E2E flow: 5-image v1→v2→execute→recover

### ⚠️ Known Limitations

- **No installer yet** (Inno Setup pending)
- **Code signing required** for production
- **Local Qwen Vision** — text-only verified, vision pipeline in progress
- **High-DPI displays** — 4K scaling not fully tested
- **Watch Folder** — auto-monitoring not implemented
- **Optional: ffmpeg/ASR** — audio transcription needs external setup

**Full details**: [docs/product/limitations.md](docs/product/limitations.md)

## 💻 Development

### Project Structure

```
Guixu/
├── backend/              # Python FastAPI, 198+ tests
├── frontend/             # Vue 3 + TypeScript, 40+ tests
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
# Creates: artifacts/release/Guixu-0.1.0/Guixu.exe
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
