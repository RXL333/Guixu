# 归序 (Guixu) · Windows AI 文件整理器

[![Python 77.9%](https://img.shields.io/badge/Python-77.9%25-blue)](#技术栈)
[![Vue 9.6%](https://img.shields.io/badge/Vue-9.6%25-green)](#技术栈)
[![TypeScript 8.7%](https://img.shields.io/badge/TypeScript-8.7%25-3178c6)](#技术栈)
![Status: Dev](https://img.shields.io/badge/Status-0.1.0%20dev-orange)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

**归序** 是一个 Local-First 的 Windows 桌面 AI 文件整理应用。通过与 DeepSeek 或本地 Qwen 模型对话，生成文件分类和整理方案，经人工审阅批准后执行。所有文件操作版本化、可追溯、支持撤销。

- ✨ **AI 驱动但绝不自动化**：AI 仅生成受限的类别 ID + 证据，人工批准后才执行
- 🔒 **本地优先，隐私第一**：支持离线 Qwen，API Key 不入库；文件全文不上云
- 📋 **完整的审计链路**：所有操作记录日志，支持受限撤销和会话恢复
- 🎯 **确定性执行**：计划 hash 校验，无目标覆盖，跨卷移动使用 copy-verify-publish
- 🧪 **严格的验证标准**：后端 198+ 测试通过，前端 40+ 测试，完整 E2E 流程已实现

---

## 📦 快速开始

### 系统要求

- **Windows 10/11 x64**（测试环境：Windows 11 23H2）
- **Python 3.12**
- **Node.js 18+**（前端开发）
- **4GB RAM 最小**，8GB 推荐

### 一分钟启动

```powershell
# 1. 克隆仓库
git clone https://github.com/RXL333/Guixu.git
cd Guixu

# 2. 环境检查（自动）
.\scripts\doctor.ps1

# 3. 开发模式启动
.\scripts\run-dev.ps1
```

浏览器自动打开 http://localhost:5173，后端 API 运行在随机端口。

### 原生桌面启动

```powershell
# 仅启动桌面应用（不开发环境）
.\scripts\run-desktop.ps1
```

### Windows 便携包

从 [Release](../../releases) 下载 `Guixu-portable-x64-0.1.0.zip`，解压即用，无需安装。

---

## 🎯 核心功能

### 1. 会话驱动的文件整理

```
┌─────────────────────────────────────────┐
│  新建会话 → 选择授权目录                    │
└──────────────┬──────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  对话讨论 (Conversation)                 │
│  - 自然语言描述分类需求                   │
│  - 上传最多 3 张参考图片                  │
│  - AI 生成基础分类方案 (v1)               │
└──────────────┬──────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  方案预览与编辑 (Plan Versioning)         │
│  - 逐文件显示：原路径 → 目标 → 操作       │
│  - 支持编辑、搜索、版本对比               │
│  - 计划 hash 校验防篡改                   │
└──────────────┬──────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  人工审批 (Manual Approval)              │
│  - 逐项确认每个文件操作                   │
│  - 可拒绝、修改或要求重新分类            │
└──────────────┬──────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  确定性执行 (Execution)                  │
│  - 计划 hash 二次校验                    │
│  - 跨卷移动：Copy → Verify → Publish      │
│  - 操作日志与事件记录                    │
└──────────────┬──────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  结果审查与撤销 (Post-Execution)         │
│  - 查看已完成的操作                      │
│  - 受限撤销（需原始状态校验）            │
│  - 会话持续活跃，支持后续调整            │
└─────────────────────────────────────────┘
```

### 2. 双模型适配

| 模型 | 类型 | 延迟 | 隐私 | 成本 | 能力 |
|------|------|------|------|------|------|
| **DeepSeek** | 云 API | ~2s | 需同意上传 | ¥0.5-2/100万字 | 文本+视觉(Vision) |
| **本地 Qwen** | Ollama | ~5-10s | 完全离线 | 仅 CPU/显存 | 文本+视觉(预期) |

- 自动降级：DeepSeek 超时 → 切换 Qwen
- 单选模型：用户在会话中明确指定
- 隐私优先：本地模型优先展示

### 3. 内容证据系统

AI 分类基于结构化证据，可追溯：

| 证据类型 | 来源 | 示例 |
|---------|------|------|
| **文件名** | 路径解析 | `2024-03-15_meeting.txt` → 日期、会议主题 |
| **文件内容** | 本地 OCR/解析 | PDF 标题、文档摘要 |
| **视觉描述** | DeepSeek Vision | 图片包含的物体、文本、场景 |
| **用户上传** | 对话中最多3张参考图 | 参考分类、风格指引 |

### 4. 文件命名功能

对话式生成文件名建议：
- 基于文件内容证据
- 保留原扩展名与目录
- 验证 Windows 名称规范
- 逐文件预览后批准执行

### 5. 安全边界

- ✅ **执行前校验**：计划 hash 二次确认、文件指纹匹配
- ✅ **无覆盖策略**：目标已存在 → 跳过或提示
- ✅ **操作日志**：所有移动/复制/删除记入 SQLite 日志
- ✅ **受限撤销**：需要原始文件状态完整存在
- ✅ **跨卷安全**：Copy → SHA-256 校验 → 原始删除

---

## 🏗️ 架构概览

### 分层结构

```
┌─────────────────────────────────────────────────┐
│         Guixu.exe (pywebview + EdgeChromium)    │
│  - 原生 Windows 窗口，无外部浏览器依赖          │
└────────────────┬────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────┐
│  FastAPI Backend (127.0.0.1:随机端口)           │
│  - 会话管理 / AI 规划 / 文件执行                │
│  - SQLite 数据库 (schema v11)                   │
│  - 日志与审计                                   │
└────────────────┬────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────┐
│  Vue 3 Frontend (TypeScript + Vite)             │
│  - 三栏布局：会话导航 / 消息与输入 / 文件预览   │
│  - 实时消息同步                                 │
│  - 方案编辑与批准界面                          │
└─────────────────────────────────────────────────┘
```

### 数据库

- **SQLite** 本地存储，`%LOCALAPPDATA%\Guixu\app.sqlite3`
- **Schema v11**：Conversation、Message、PlanVersion、Operation、FileReference
- **WAL 模式**：支持并发读写
- **自动迁移**：Alembic 版本管理

详见 [`contracts/database.sql`](contracts/database.sql) 和 [`backend/migrations/`](backend/migrations/)。

### 核心模块

| 模块 | 职责 | 关键类 |
|------|------|--------|
| **Scanner** | 递归扫描目录，提取文件元数据 | `FileScanner`、`FileProfile` |
| **Parser** | OCR、解析、多模态内容提取 | `TextParser`、`ImageParser`、`DocumentParser` |
| **AI Planner** | 对话、方案生成、版本管理 | `ConversationAgent`、`PlanVersionService` |
| **ModelGateway** | DeepSeek / Qwen 适配层 | `DeepSeekAdapter`、`QwenAdapter` |
| **Executor** | 计划执行、日志、撤销 | `FileOperationExecutor`、`UndoService` |
| **Security** | 路径校验、指纹核对 | `ScopeValidator`、`ChecksumManager` |

---

## 🛠️ 开发指南

### 项目结构

```
Guixu/
├── backend/                    # Python FastAPI 后端
│   ├── app/
│   │   ├── api/              # REST 路由
│   │   ├── models/           # SQLAlchemy ORM
│   │   ├── services/         # 业务逻辑
│   │   ├── adapters/         # AI 模型适配
│   │   └── executor/         # 文件操作执行
│   ├── tests/                # 后端单元 + 集成测试 (198+ pass)
│   ├── migrations/           # Alembic 数据库迁移 (v11)
│   └── pyproject.toml        # UV 依赖管理
│
├── frontend/                   # Vue 3 + TypeScript 前端
│   ├── src/
│   │   ├── components/       # 可复用组件
│   │   ├── pages/            # 页面视图
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── api/              # HTTP 客户端
│   │   └── types/            # TypeScript 定义
│   ├── tests/                # 单元 + E2E 测试 (40+ pass)
│   └── package.json
│
├── docs/                       # 文档
│   ├── product/              # 产品文档：功能、工作流、限制
│   ├── current/              # 当前实现：架构、API、决策日志
│   ├── development/          # 开发指南：启动、测试、打包
│   └── archive/              # 历史资料：蓝图、提示词、截图
│
├── contracts/                  # API 和数据库契约
│   ├── openapi.json          # 初始设计 API 约定
│   ├── openapi-runtime.json  # 实际生成的 OpenAPI 定义
│   └── database.sql          # DDL 快照
│
├── scripts/                    # 自动化脚本
│   ├── doctor.ps1            # 环境检查
│   ├── run-dev.ps1           # 开发启动
│   ├── run-desktop.ps1       # 桌面启动
│   ├── verify.py             # 全量验证
│   ├── package-windows.ps1   # 构建便携包 + 安装器
│   └── audit_release_secrets.py  # 安全审计
│
├── seed/                       # 运行时资源（分类法、提示词等）
├── artifacts/                  # 构建产物、测试报告、便携包
└── PROJECT_STATUS.md           # 当前开发状态（详见下文）
```

### 快速命令

```powershell
# 环境检查 (Python、Node、Git)
.\scripts\doctor.ps1

# 开发启动 (同时运行后端 + 前端)
.\scripts\run-dev.ps1

# 原生桌面启动 (需后端已启动)
.\scripts\run-desktop.ps1

# 后端单元测试
cd backend
uv run pytest -q                    # 全量 198+ 测试
uv run pytest tests/test_scanner.py # 单个模块

# 前端单元测试
cd frontend
npm run test:run                    # 全量 40+ 测试
npm run test -- src/components/...  # 单个文件

# 全量验证 (测试 + 类型检查 + 构建)
python .\scripts\verify.py all

# 构建 Windows 便携包 + 安装器
.\scripts\package-windows.ps1
```

### 常见开发任务

#### 添加新的 REST 端点

1. 在 `backend/app/models/` 定义数据模型
2. 在 `backend/app/services/` 实现业务逻辑
3. 在 `backend/app/api/` 创建路由
4. 添加测试到 `backend/tests/`
5. 运行 `uv run pytest` 验证
6. 更新 `contracts/openapi-runtime.json`

#### 添加新的 AI 模型适配

参考 `backend/app/adapters/deepseek_adapter.py`：

```python
from app.adapters.base import ModelAdapter

class MyModelAdapter(ModelAdapter):
    def chat(self, messages: List[Dict], **kwargs) -> ModelResponse:
        # 实现您的模型调用逻辑
        pass
    
    def is_available(self) -> bool:
        # 检查连接状态
        pass
```

注册到 `ModelGateway`：

```python
gateway.register_adapter("my-model", MyModelAdapter(...))
```

#### 修改数据库 Schema

1. 新增模型字段或表到 `backend/app/models/`
2. 生成迁移：`alembic revision --autogenerate -m "description"`
3. 检查生成的迁移文件
4. 测试迁移：`alembic upgrade head` 和 `alembic downgrade -1`
5. 提交迁移文件

---

## 📊 当前项目状态

### 版本：0.1.0 dev

**发布判定**：⚠️ **NOT RELEASE READY**

最新工作进展详见 [PROJECT_STATUS.md](PROJECT_STATUS.md)（自动更新，每阶段记录）。

### 已完成

| 阶段 | 功能 | 状态 |
|------|------|------|
| **PHASE D** | 对话数据模型 (Conversation schema v4) | ✅ PASSED |
| **PHASE E** | 三栏 UI 骨架 (会话/消息/文件窗口) | ✅ PASSED |
| **PHASE F** | 首次整理分析链路 (AI 方案 v1 生成) | ✅ PASSED |
| **PHASE G** | 方案版本管理 (v1→v2 diff/审批) | ✅ PASSED |
| **PHASE H** | 执行后对话 (Conversation 持续活跃) | ✅ PASSED |
| **PHASE I** | 文件引用 (精确路径映射) | ✅ PASSED |
| **PHASE J** | 语义缓存 (证据复用) | ✅ PASSED |
| **PHASE K** | 会话恢复 (重启读回数据) | ✅ PASSED |
| **PHASE L** | 对话撤销 (UndoPlan + FORWARD/UNDO) | ✅ PASSED |
| **PHASE M** | UI 深度优化 (统一弹窗、设置页等) | ✅ PASSED |
| **AI-only 核心** | 双模型、视觉、隐私、执行链 | ✅ PASSED |

### 外部阻塞（需后续条件）

- 🔴 **Inno Setup 安装器**：未生成
- 🔴 **代码签名**：无 EV 证书
- 🔴 **干净 Windows 测试**：无 Python/Node 环境
- 🔴 **高 DPI 多系统验收**：4K 显示器测试缺失
- 🔴 **本地 Qwen 完整链路**：需 Ollama 环境验证
- 🔴 **ffmpeg / ASR 组件**：可选功能，未集成

### 测试覆盖

- ✅ **后端**：198 passed（含 AI-only、安全、性能、真实模型）
- ✅ **前端**：40+ passed（组件、页面、集成）
- ✅ **E2E**：核心流程真实验证（5-JPG v1→v2→执行→恢复）
- ✅ **数据库**：迁移、幂等性、并发
- ✅ **安全**：无 hardcoded key、文件超权、跨会话泄露

---

## 🔐 安全与隐私

### 核心原则

| 原则 | 实现 |
|------|------|
| **本地优先** | 所有数据默认存储在 `%LOCALAPPDATA%\Guixu\`，仅在用户明确选择云模型时上传 |
| **Key 隔离** | API Key 仅在内存中，不写数据库/日志/浏览器存储 |
| **文件不上云** | 仅上传 AI 模型需要的结构化内容（文件名、摘要、缩略图），不发送全文或原始媒体 |
| **路径隐私** | 受授权目录严格限定，跨目录访问拒绝 |
| **操作审计** | 所有文件操作记入 SQLite 日志，包括执行者、时间、变更前后状态 |

### 隐私模式

```
普通模式          │ 隐私模式
-----------------│------------------
DeepSeek (云)     │ 本地 Qwen
需配置 API Key     │ 无需网络、无 Key
需同意隐私协议     │ 完全离线
较快（~2s/请求）  │ 较慢（~5-10s/请求）
文件内容摘要上传    │ 仅本地处理
```

用户可在设置中随时切换，已生成的方案不依赖模型绑定。

### 安全审计

运行 `python .\scripts\audit_release_secrets.py` 检查便携包：

- ✅ 扫描 434 个文件、301MB 解压字节
- ✅ 检测常见 Key 特征（DeepSeek、GitHub、AWS、PEM）
- ✅ 验证字符串编码、环境变量注入点
- ✅ 生成审计报告

---

## 📚 文档导航

| 文档 | 内容 |
|------|------|
| [docs/product/](docs/product/) | 产品文档：功能、工作流、已知限制 |
| [docs/current/](docs/current/) | 实现细节：架构、API、决策日志、部署 |
| [docs/development/](docs/development/) | 开发指南：快速开始、测试、打包、发布 |
| [docs/archive/](docs/archive/) | 历史资料：初始蓝图、提示词、视觉稿（参考用，非当前实现） |
| [contracts/](contracts/) | 契约文件：OpenAPI、数据库 DDL |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | 实时项目状态：阶段进度、测试结果、已知问题 |

---

## 🐛 已知限制

### 功能

- ⚠️ **不支持 Watch Folder**：目录变更监听功能未实现
- ⚠️ **本地 Qwen Vision 未测**：仅 Ollama deepseek-7b 文本模型验证过
- ⚠️ **跨卷移动限制**：`direct_move` 模式（不经 copy-verify-publish）在发布门关闭
- ⚠️ **L3 分类决策缓存**：暂未实现多层级分类的语义缓存
- ⚠️ **RAG/向量存储**：未集成，复杂问题仍需手工编排

### 系统

- ⚠️ **仅支持 Windows x64**：无 ARM 或 macOS/Linux 适配
- ⚠️ **需要管理员权限**（某些目录）：系统文件夹访问需提权
- ⚠️ **不自动下载大模型**：Qwen、CUDA、ffmpeg 需用户手动安装
- ⚠️ **高 DPI 显示器**：4K 及以上分辨率 UI 缩放未充分测试

详见 [docs/product/limitations.md](docs/product/limitations.md)。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 提交前检查

```powershell
# 1. 运行全量���试
python .\scripts\verify.py all

# 2. 检查代码风格
cd backend
uv run ruff check .
uv run black --check .

cd ../frontend
npm run lint

# 3. 类型检查
npm run typecheck
```

### PR 流程

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改并补充测试
4. 推送到 Fork：`git push origin feature/your-feature`
5. 开启 Pull Request，描述改动和测试结果

---

## 📦 技术栈

### 后端

- **Python 3.12** + **FastAPI** 0.109+
- **SQLAlchemy 2.0** + **Alembic** 迁移
- **Pydantic** 数据校验
- **pytest** 单元和集成测试
- **httpx** HTTP 客户端（DeepSeek/Qwen API）

### 前端

- **Vue 3** (Composition API)
- **TypeScript** 4.9+
- **Vite** 5.0+ 构建工具
- **Pinia** 状态管理
- **TailwindCSS** + 自定义组件库
- **Vitest** 单元测试

### 桌面

- **pywebview** 0.5.11+ （Chromium 集成）
- **UPX** 可执行文件压缩（便携包）
- **Inno Setup 6** 安装器生成（未集成）

### 外部依赖

- **DeepSeek API**（可选，需 Key）
- **Ollama**（可选，本地 Qwen）
- **OCR/解析**（本地或云，可选）

---

## 📄 许可证

[MIT License](LICENSE) - 自由使用、修改、分发（需保留许可证文本）。

---

## 💬 反馈与支持

- 📮 **GitHub Issues**：[提交问题](../../issues)
- 💭 **讨论区**：[GitHub Discussions](../../discussions)
- 📖 **详细文档**：[docs/](docs/) 和 [PROJECT_STATUS.md](PROJECT_STATUS.md)

---

## 🙏 致谢

- [DeepSeek API](https://deepseek.com)：强大的多模态 AI 模型
- [Ollama](https://ollama.ai)：本地模型运行时
- [FastAPI](https://fastapi.tiangolo.com)：现代 Python Web 框架
- [Vue 3](https://vuejs.org)：渐进式前端框架
- [pywebview](https://github.com/r0x0r/pywebview)：跨平台桌面应用开发

---

**最后更新**：2026-09-28 | **版本**：0.1.0 dev | **项目状态**：[查看详情](PROJECT_STATUS.md)
