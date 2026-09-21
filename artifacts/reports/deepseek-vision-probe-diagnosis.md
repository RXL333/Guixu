# DeepSeek vision probe 诊断

日期：2026-09-19  
范围：仅复现当前模型连接页的 DeepSeek `deepseek-flash` 视觉能力探测；未修改生产代码，未读取用户文件。

## 复现配置

- provider：`deepseek`
- model_id：`deepseek-flash`
- endpoint：`https://api.deepseek.com/chat/completions`
- API Key：从 Windows Credential Manager 读取并仅用于请求头；未打印、未写入报告。

## 原始请求结构（脱敏）

```json
{
  "model": "deepseek-flash",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Describe the single built-in test pixel."
        },
        {
          "type": "image_url",
          "image_url": {
            "url": {
              "prefix": "data:image/png;base64,",
              "length": 114
            }
          }
        }
      ]
    }
  ],
  "stream": false,
  "thinking": {
    "type": "disabled"
  }
}
```

结构检查：

- `messages[].content[]`：有。
- `type=text` block：有。
- `type=image_url` block：有。
- image URL：`data:image/png;base64,` 前缀，总长度 114。
- `response_format` / JSON mode：无。
- JSON schema / structured output：无。
- 无 tools 或其他工具参数。
- 当前 `DeepSeekAdapter` 会额外附带 `thinking={"type":"disabled"}`；修复后的视觉 probe 将移除该非必要参数。

## DeepSeek 原始响应

- HTTP status：`400`
- error code：`invalid_request_error`
- error type：`invalid_request_error`
- error message 原文：`.messages[0].image[0]: You have uploaded an unsupported image. Please make sure your image is valid and has one of the following formats: webp, png, jpeg, and gif.`

## 本地图像校验

- Base64 严格解码：成功。
- 解码字节数：68 bytes。
- 文件签名：`89504e470d0a1a0a`（PNG）。
- Pillow 初步识别：PNG，1×1，LA。
- Pillow `verify()`：失败，`SyntaxError: broken PNG file (bad header checksum in b'IDAT')`。

因此，API 拒绝的根因不是 Key、模型 ID、MIME、content block 或 JSON 参数，而是当前硬编码的 1×1 PNG 内容损坏。

## 当前错误映射路径

1. `ModelProfileService.probe()` 发送硬编码 1×1 PNG。
2. DeepSeek 返回 HTTP 400 与上述 `invalid_request_error`。
3. `OpenAICompatibleTransport.chat()` 对所有 `>=400` 响应只抛出 `ModelTransportError("MODEL_REQUEST_REJECTED", status=400)`，没有保留响应 error code/message。
4. `ModelProfileService.probe()` 捕获该异常，将 vision 保存为 `status=unsupported, message=MODEL_REQUEST_REJECTED`。
5. 模型连接页只能显示通用的 `MODEL_REQUEST_REJECTED`，无法显示底层图像损坏原因。

## 诊断结论

应动态生成并用 Pillow 回读验证一个 64×64、具有明显颜色区域的合法 PNG，再以最小视觉请求发送；同时让传输异常保留脱敏后的 API error code/message，并在 capability 中持久化明确的 probe 元数据。
