# DeepSeek vision probe 修复报告

日期：2026-09-19  
范围：仅 DeepSeek vision probe、DeepSeek 图片输入、capability 持久化与模型连接卡片显示；未修改任务页、Planner 或 Classifier。

## 1. 根因

原 probe 使用的硬编码 1×1 PNG 虽有正确 PNG 文件签名，但 IDAT chunk 校验和损坏。Pillow `verify()` 报告：

`SyntaxError: broken PNG file (bad header checksum in b'IDAT')`

DeepSeek 因此返回 HTTP 400：

`.messages[0].image[0]: You have uploaded an unsupported image. Please make sure your image is valid and has one of the following formats: webp, png, jpeg, and gif.`

传输层此前丢弃服务端 error body，只将所有 4xx 映射为 `MODEL_REQUEST_REJECTED`，所以连接页无法显示真实原因。完整原始证据见 `artifacts/reports/deepseek-vision-probe-diagnosis.md`。

## 2. 原始错误请求的问题

- provider、endpoint、`model=deepseek-flash` 正确。
- `messages[].content[]`、`type=text`、`type=image_url` 和嵌套 `image_url.url` 均正确。
- MIME 前缀是 `data:image/png;base64,`，base64 可以解码。
- 没有 `response_format`、JSON schema 或 tools。
- 实际问题是解码后的 PNG 损坏；视觉请求还附带了非必要的 `thinking={"type":"disabled"}`。

## 3. 修复后的请求结构

```json
{
  "model": "deepseek-flash",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Describe the main visual content of this image briefly."
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,<BASE64>"
          }
        }
      ]
    }
  ],
  "stream": false
}
```

DeepSeek 多模态请求不再附带 `thinking`。视觉 probe 明确使用 `json_mode=false`。

## 4. JSON / structured 参数

- vision capability probe：没有 `response_format`、JSON schema、structured output 或 tools。
- 正式图片分类链路仍需 JSON 结果，因此保留 `response_format={"type":"json_object"}`；已用同一项目测试 JPG 对 `deepseek-flash + image + json_mode=true` 做真实请求，成功得到非空 `visual_description`。

## 5. Probe 图片格式

- 运行时用 Pillow 动态生成，不依赖用户文件。
- 64×64 RGB PNG，蓝色背景和中央红色方块。
- PNG bytes 在编码前由 Pillow 重新打开并执行 `verify()`。
- Base64 严格编码为 `data:image/png;base64,...`。
- 单元测试验证 MIME、Base64、PNG 格式和 64×64 尺寸。

## 6. 真实 probe 结果

模型：`deepseek-flash`。2026-09-19 真实探测结果：

- reachable：supported
- authentication：supported
- text：supported
- json_mode：supported
- vision：supported
- cancellation：supported
- vision：`true`
- vision_verified：`true`
- probe_status：`success`
- probe_error：`null`
- last_probe_at：`2026-09-19T14:25:02.269200+00:00`

视觉探测不再返回 `MODEL_REQUEST_REJECTED`。

## 7. Capability 持久化

探测结果写入 `model_profiles.capabilities_json`。关闭首次 `Database` / `ModelProfileService` 实例后，重新创建实例读取，仍得到：

```json
{
  "status": "supported",
  "vision": true,
  "vision_verified": true,
  "probe_status": "success",
  "probe_error": null
}
```

模型连接页新增明确摘要：文本“已验证/失败”、视觉“已验证/失败”，失败时显示持久化的具体 `probe_error`。传输层现在保留经过长度限制的 provider error code/message，不包含请求头、Key 或请求 body。

## 8. 单图真实视觉描述

输入：项目测试 JPG `artifacts/test-workspaces/phase-09-final/ocr/cache/final-ocr-frame-0.jpg`，5474 bytes。没有读取用户个人文件。

真实 `DeepSeekAdapter` 请求结果：

- model：`deepseek-flash`
- image data URL：`data:image/jpeg;base64,`，总长度 7323
- latency：1248 ms
- input tokens：232
- output tokens：135
- visual description：`This image features a solid blue background with a white border around the edges. Centered in the middle is the white text "Guixu synthetic acceptance sample image 01".`

结果已写入隔离测试数据库的 FileProfile：

```json
{
  "kind": "visual_description",
  "text": "This image features a solid blue background with a white border around the edges. Centered in the middle is the white text \"Guixu synthetic acceptance sample image 01\"."
}
```

测试数据库：`artifacts/test-workspaces/deepseek-vision-validation/file-profile-96a3ab013cd8412f9f1653ff7d77f68d.sqlite3`。

另一次真实 `image + json_mode=true` 请求也通过：latency 1782 ms，input 260 tokens，output 95 tokens，`visual_description` 非空。

## 9. 测试结果

| 命令 / 验证 | 结果 |
|---|---|
| DeepSeek 原错误复现 | HTTP 400，获得原始 `invalid_request_error`；PASS |
| 动态 PNG + 最小请求真实 probe | vision supported；PASS |
| 重建 DB/service 后读取 capability | vision verified 保持；PASS |
| 项目测试 JPG 真实视觉描述及 FileProfile 写入 | PASS |
| DeepSeek 图片 + JSON mode | PASS |
| `pytest backend/tests/models/test_models.py backend/tests/classification/test_ai_file_classifier.py backend/tests/contract/test_database.py backend/tests/parsers/test_parsers.py -q` | 27 passed，1 个既有 Pillow decompression warning |
| `pytest backend/tests -q` | 136 passed，2 warnings |
| `npm test -- --run` | 16 passed（含 vision 成功持久化与失败详情两种模型卡片状态） |
| `npm run typecheck` | exit 0 |
| `npm run build` | exit 0 |
| `backend/.venv/Scripts/python.exe scripts/verify.py all` | exit 0；全部后端分组、前端 typecheck/test/build 通过 |
| `scripts/package-windows.ps1 -SkipTests` | exit 0；onedir、portable ZIP、冻结诊断和打包校验通过 |

Pytest 收尾时还报告 Windows 临时目录 reparse 测试垃圾目录无法删除的既有警告；不影响测试退出码，也未操作用户个人文件。

重建发布产物：

- `artifacts/release/Guixu-0.1.0/Guixu.exe`：SHA-256 `54bf1c954317b47f0369e667c9c41de3d14971f5a78fa656d0f043172f52be50`
- `artifacts/release/Guixu-portable-x64-0.1.0.zip`：SHA-256 `b42434848cde31ece93a450f3d832c5b38e0053b5f3b1dcb27f270517a7afb28`
- Inno Setup 6 仍未安装，因此本轮按既有规则只重建 onedir 与 portable ZIP，未伪报安装器完成。

## 完成条件

- [x] DeepSeek `deepseek-flash` 文本 probe 成功
- [x] DeepSeek `deepseek-flash` 视觉 probe 成功
- [x] 视觉 probe 不再显示 `MODEL_REQUEST_REJECTED`
- [x] 模型连接页显示 vision 已验证
- [x] 重启服务对象后 capability 保持
- [x] 单张真实 JPG 获得 `visual_description` evidence
