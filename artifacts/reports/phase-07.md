# 阶段 07 验收报告：长任务可靠性与完整工作流

日期：2026-09-14  
环境：Windows 11 x64；Python 3.12.10；SQLite WAL；Chromium 本地 UI；仅项目测试目录

## 结论

阶段 07 **PASS**。TaskCoordinator、持久检查点、启动恢复审计、单执行锁、协作式暂停／恢复／取消、解析与分类缓存边界、任务快照、同伴组、授权报告导出、全局幂等键、后端一致计数和反向撤销工作流已经实现并完成自动化与真实测试目录 UI 闭环。

应用只停止自己创建的 worker；取消标志不会终止用户的 Qwen 服务。恢复服务根据源、目标、自有临时文件、身份和完整 SHA-256 核对磁盘事实，不盲目重放 move。相同内容可共享无上下文解析结果，但各路径保留独立 file_id；最终分类缓存另含文件上下文、taxonomy ID／版本／hash、规则、模型快照、隐私授权和 prompt 版本。

## 可靠性实现与证据

| 范围 | 结果 | 证据 |
|---|---|---|
| 唯一执行与控制 | PASS | 全局非阻塞执行锁；活动执行的 pause 先进入 PAUSE_REQUESTED，在块／文件检查点进入 PAUSED；CAS stale revision 返回 409 |
| 启动恢复 | PASS | 启动把 RUNNING／PAUSE_REQUESTED 转为 RECOVERY_REQUIRED，并追加单调 seq；无未闭合磁盘操作时核对后进入 PAUSED |
| 操作恢复 | PASS | OP05 的 PREPARED、COPYING、TEMP_WRITTEN、VERIFIED、PUBLISHED、SOURCE_REMOVED 崩溃点均由真实子进程测试覆盖 |
| 幂等 | PASS | 同 endpoint/key/body 返回首次完整响应且只创建一项；同 key 不同 body 返回 IDEMPOTENCY_KEY_REUSED |
| 缓存 | PASS | 两个同内容 TXT 只调用解析 worker 一次但 profile.file_id 不同；源 hash、parser version、preset 均在解析键中 |
| 分类失效 | PASS | taxonomy 实例／版本／hash、文件名和 scope、规则快照、模型快照、隐私 consent、prompt version 全部进入输入 hash |
| 任务快照 | PASS | 创建任务时冻结选定规则和模板版本；后续全局修改不改变既有任务分类输入 |
| 同伴组 | PASS | 图片+XMP、视频+字幕、音频+歌词仅在一一对应时分组；歧义告警且不猜；组预检与 partial group 已测试 |
| 防回扫 | PASS | 当前输出和数据库已记录的外部输出根均作为 OUTPUT_EXCLUDED；不会无限嵌套 |
| 一致计数 | PASS | discovered/eligible/excluded/profile_ready/profile_partial/high/review/conflict/executed 由数据库聚合，不由当前 UI 页长度推断 |
| 报告导出 | PASS | 仅 export grant 下 exclusive create JSON/CSV；拒绝 `../`；同名不覆盖；CSV 的 `= + - @ tab CR` 前缀加单引号 |
| 撤销 | PASS | 反向计划单独预览、hash 批准和执行；外部修改／原位占用不覆盖；重复撤销幂等 |
| 故障路径 | PASS | 假服务断网、预算耗尽、树版本变化、执行崩溃、ENOSPC、撤销前外部修改、重复 undo 与分页全选均有自动化证据 |

## 项目测试目录真实 UI 闭环

任务：`4c6a17e0-891b-4727-bb7f-d4f7e412f4d2`  
测试根：`artifacts/test-workspaces/phase-07-e2e`

1. UI 扫描 `source/归序可靠性测试.txt`，批准 8 节点树，编译计划 `8c763aa8…`。
2. 最终确认框未选时执行按钮禁用；选中后只在测试根内移动到 `source/文本/归序可靠性测试.txt`。
3. 报告同时显示数据库聚合：discovered=1、eligible=1、profile_ready=1、suggested_high=1、executed=1、conflict=0；forward operation=COMMITTED。
4. 通过 export grant 写出 `export/guixu-report-4c6a17e0.csv`（697 bytes）。
5. 生成反向计划 `89af0486…`，再次明确确认后执行；文件回到原路径，目标不存在，原文件 SHA-256 为 `C1601E5C035B359294CA92AA15BA9D5CB3194B32E58E51955233E826BA21A68F`。
6. 数据库最终：forward=COMMITTED、undo=UNDONE，task event seq 1～13 共 13 条且无重复；UI `undo.available=false`、`recoverable=0`。浏览器 console 0 warning/error。

撤销首轮完成后 UI 曾仍显示“可撤销”，原因是报告用历史 forward COMMITTED 数量推导，而未排除 UNDONE 反向操作；已改为查询“已提交且不存在成功反向操作”的项目并复验。

## 命令与结果

| 命令 | 退出结果 |
|---|---:|
| `python scripts/verify.py reliability` | 0；8 passed |
| `uv run --all-extras pytest -q` | 0；114 passed，2 个已知 warning |
| `python scripts/verify.py all` | 0；各既有范围与前端构建全部通过 |
| `python scripts/verify.py ui` | 0；8 tests，production build 1714 modules |
| 本地 UI 移动／导出／撤销及 DB／磁盘核对 | 0；原文件恢复、目标消失、日志和计数一致 |

## 下一阶段

进入阶段 08：按完整追踪矩阵执行质量、安全、性能和真实能力验收；真实 DeepSeek/Qwen、真实双卷、云占位、完整音视频组件等仍按各自外部条件单独报告，不以假服务或同卷目录替代。
