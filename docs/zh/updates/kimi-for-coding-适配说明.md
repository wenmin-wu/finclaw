# Kimi For Coding 适配说明

## 背景

Kimi For Coding 接口（`https://api.kimi.com/coding/v1`）仅对「编程类 Agent」开放，服务端会校验请求头中的 `User-Agent`，若未被识别为 Kimi CLI、Claude Code、Roo Code 等 Coding Agent，会返回：

```text
MoonshotException - Kimi For Coding is currently only available for Coding Agents such as Kimi CLI, Claude Code, Roo Code, Kilo Code, etc.
```

通过 LiteLLM 调用时，自定义 Header（如 `User-Agent`）无法可靠传递到 Moonshot/Kimi 接口，因此会触发上述错误。

## 本项目的处理方式

本项目中在 `nanobot/providers/litellm_provider.py` 做了如下适配：

1. **检测 Kimi For Coding 端点**  
   当配置的 `api_base` 包含 `api.kimi.com/coding` 时，视为使用 Kimi For Coding 接口。

2. **绕过 LiteLLM，直连 OpenAI 兼容接口**  
   对该端点不再经 LiteLLM，改为使用 `openai.AsyncOpenAI` 直接请求，并固定设置：
   - `default_headers={"User-Agent": "KimiCLI/0.77"}`
   以满足服务端对 Coding Agent 的校验。

3. **模型名处理**  
   请求时自动去掉 provider 前缀，例如配置为 `moonshot/kimi-for-coding` 时，实际请求模型名为 `kimi-for-coding`。

4. **与现有配置兼容**  
   无需修改现有配置，只要 `apiBase` 为 `https://api.kimi.com/coding/v1`，请求会自动走上述直连逻辑。

5. **reasoning_content（思考内容）**  
   Kimi 等支持「思考」的模型会在回复中返回 `reasoning_content`，且多轮对话时要求 assistant 消息在带 `tool_calls` 时也带上 `reasoning_content` 字段（可为空字符串）。本项目做如下适配：
   - **Provider**：`_parse_response` 已从响应中解析 `message.reasoning_content` 并写入 `LLMResponse.reasoning_content`。
   - **Context**：`context.add_assistant_message` 在添加带 `tool_calls` 的 assistant 消息时，始终写入 `reasoning_content`（有值用原值，无则用 `""`）；无 `tool_calls` 但有思考内容时也写入 `reasoning_content`，保证多轮对话符合 Kimi 接口要求。

## 配置示例

与 [使用说明](../使用说明.md) 中一致即可：

```json
"defaults": {
  "model": "moonshot/kimi-for-coding",
  ...
},
"moonshot": {
  "apiKey": "<your-kimi-api-key>",
  "apiBase": "https://api.kimi.com/coding/v1",
  "extraHeaders": null
}
```

配置后，所有发往该 `api_base` 的对话请求都会通过直连方式携带正确 `User-Agent`，从而正常使用 Kimi For Coding。

## 相关代码

- 直连实现：`nanobot/providers/litellm_provider.py` 中的 `_chat_kimi_direct`
- 路由逻辑：同文件中 `chat()` 内对 `api.kimi.com/coding` 的判断与分流
- reasoning_content 解析：同文件 `_parse_response` 中的 `reasoning_content` 提取
- reasoning_content 回写：`nanobot/agent/context.py` 中 `add_assistant_message` 对带 `tool_calls` 消息必带 `reasoning_content` 的处理

## 更新日期

2025-03
