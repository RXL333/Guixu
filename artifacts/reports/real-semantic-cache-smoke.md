# Real Semantic Cache Smoke

状态：BLOCKED_EXTERNAL（本次实现环境未提供用户明确授权的 DeepSeek API key 与 10 张授权 JPG，因此没有发起真实云请求，也没有写入任何密钥、base64 或私人内容。）

预留验收流程：

1. 使用已有 `DeepSeekAdapter` 和用户授权目录，第一次对 10 张 JPG 记录 `VISUAL_DESCRIPTION` model calls。
2. 只改变 taxonomy/requirements，确认 10 条 evidence `CACHE_HIT`、Vision 调用为 0。
3. 修改其中 1 个文件内容，再次确认 9 hit、1 invalid/refresh，新增 Vision 调用为 1。
4. 只在实际运行后填写 calls、latency、estimated calls saved；不使用 fake adapter 数字替代真实证据。
