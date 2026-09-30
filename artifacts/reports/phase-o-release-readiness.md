# 阶段 O — 上线就绪收敛（2026-09-30）

## 结论

**NOT RELEASE READY。** 本轮关闭了登记缺陷与两项可在本机验证的安全/性能缺口，但门禁仍被外部环境阻塞：安装器、干净 Windows、打包版多 DPI/视口验收、RC1 打包。

## 命令与退出结果

| 命令 | 结果 |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/safety/test_filesystem_and_storage_edges.py -q -p no:randomly` | **15 passed, 1 skipped**（3.54s） |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | **249 passed, 1 skipped, 2 warnings**（83.17s） |
| `frontend: npm run test:run` | **9 files / 67 tests passed**（18.70s，exit 0） |
| `frontend: npm run build`（含 `vue-tsc -b`） | **exit 0**，1744 modules transformed |
| `backend/.venv/Scripts/python.exe scripts/run_phase_n_performance.py --sizes 500 1000 5000 --repeat 5 --report artifacts/reports/phase-n-performance.json` | **exit 0**，15 组分布（3 规模 × 5 阶段） |

唯一 skip：`test_s06_max_depth_nested_long_category_path_is_created_and_published` —— 本卷未启用长路径，执行器暂存名 `.<名>.guixu-part-<uuid>` 使 229 字符目标在暂存阶段达 280 字符。属环境限制，不是缺陷。

## 产物

- `artifacts/reports/phase-n-performance.json`（`schema_version: 2`，含 `method.caveat` 与 `limitations`）
- `artifacts/reports/guixu-1.0-bug-registry.md`（统计重算、新增 P2-004、撤回 P2-001 的单次采样数字）
- `docs/current/deployment/RELEASE_ACCEPTANCE.md`（S05/S06/S07/S15/S16、B01/B02/B03、P01–P03）
- `artifacts/test-workspaces/phase-n-performance/`（每轮一个独立目录，脚本不删除任何内容）

## 本轮修复

### 1. 每轮对话的全库重哈希（性能，最大的一处）

`post_execution` 的工作区核对此前对每个文件无条件重算 SHA-256，成本是 **O(字节)** 而非 O(文件数)。基准 fixture 每文件 33 字节，问题被完全掩盖；真实照片库约 4MB/张，相当于每条消息重读约 20GB。

改为复用启动核对已有的 `quick_same` 快速路径：size 与 mtime_ns 均未变即视为未重写，沿用已存指纹。

- 5,001 项核对：p50 **3.2465s → 0.7341s**，p95 3.6674s → **0.8758s**（4.4×）
- 安全性未削弱：执行器在**每次移动前仍重新哈希**，`test_forged_mtime_still_fails_the_pre_move_identity_check` 证明伪造 mtime 无法让被改内容通过 `identity_matches`
- 代价已记录：内容被改但 size 与 mtime 同时还原时，核对层会漏判。执行器不受影响。取舍见 `DECISION_LOG.md` 2026-09-29

### 2. 目标路径被按盘上大小写改写（数据完整性，登记为 P2-004）

`path_policy.ensure_within` 对尚不存在的叶子调用 `Path.resolve()`，Windows 上会按盘上大小写重写路径。目录中已有 `photo.jpg` 时，指向 `Photo.jpg` 的方案会被折叠成 `photo.jpg`，用户文件最终**以占用者的大小写发布**。NTFS 大小写不敏感，该差异不可见，因此长期未暴露；网络共享、exFAT 卡、同步目录上这是一次真实重命名。

包含性检查仍用解析后形式（防 junction / `..` 绕过授权），仅**返回**词法绝对路径。

### 3. 撤回不可复现的性能数字

P01–P03 曾记录单次采样，含「5,000 项 attach 1.298s、reconcile 3.409s」。基准脚本重写为多次重复 + nearest-rank 后，attach 真实 p50 为 **3.13s** —— 比原记录高一倍以上。**这些数字已撤回并在两处文档标注更正**。「32.73s → 1.298s」的定性结论仍成立，措辞修正为「32.73s → p50 3.13s」。教训：未经分布的单次计时不应写进验收矩阵。

## 新增回归（`backend/tests/safety/test_filesystem_and_storage_edges.py`）

- **S05 ×3**：仅大小写不同的目标生成 `Photo (2).jpg` 而非覆盖；审批后出现的大小写冲突记 `CONFLICT`/`TARGET_APPEARED` 且双方文件留存；两个授权根下仅大小写不同的源分得不同目标
- **S06 ×4**：60 字符类别名边界；超长整份方案在落盘前拒绝；超出 MAX_PATH 的目标安全失败且源文件留存；贴近上限的成功路径（本机 skip）
- **S07 ×2**：源不可读 → 记 CONFLICT 且不删除；目标不可写 → 操作失败且不触碰源
- **S15 ×6**：WAL/busy_timeout PRAGMA 生效；回滚无残留行；两写者提交均不丢；busy_timeout 阻塞至首个提交；乐观锁恰好一个赢家；**独立子进程 `os._exit` 后未提交丢弃、已提交留存**

## 未通过 / 仍未关闭

- **S06**：贴近 MAX_PATH 的**成功**路径在本机无法验证（长路径未启用 + 暂存名 +50 字符）
- **S07**：两项新用例在 `read_identity`/`identity_matches` 的系统调用边界注入 `PermissionError`，**不是真实 ACL deny**。真实 deny ACE 无法在不提权的 shell 中撤销（deny ACE 会挡住撤销它自身所需的 ACL API），故"真实 OS 拒绝"这一半仍未测
- **S16**：v11 迁移用例是**测试内构造**的旧表，非真实历史发布版 `.sqlite3` 文件；v1→v12 链式连续升级未演练
- **C05 / C07 / C12 / C17**：打包版真实模型链
- **U01–U04**：打包版视口与多 DPI
- **B07**（RC1 打包）、**B09**（安装器）、**B10 / Clean Windows**（干净环境）

## 外部阻塞（需用户决定，非工程可解）

1. **Inno Setup 6** 不在本机构建机上 → B09 无法开始
2. **无干净 Windows** VM/主机 → B10 与 Clean Windows 无法取证；判定规则明确不接受在开发机重跑
3. **无签名证书**、**许可证未选定** → 受控分发、写明 SmartScreen
4. **一个被 ACL 损坏的临时目录需要用户授权修复**：
   `C:\Users\renxiaolin\AppData\Local\Temp\pytest-of-renxiaolin\pytest-44\test_s07_acl_denied_destinatio0\out\blocked`
   该目录的当前用户显式 ACE 被一个早前子代理的 `icacls /deny` 测试剥离，现只剩 SYSTEM/Administrators/OWNER RIGHTS。测试代码中的 ACL 路径已整体删除（改用系统调用边界注入），但**磁盘上的损害仍在**。修复需要 `icacls <路径> /reset /T /C`，该命令被安全分类器拦截，需用户明确授权后才可执行。目录内无用户数据，仅测试产物。
