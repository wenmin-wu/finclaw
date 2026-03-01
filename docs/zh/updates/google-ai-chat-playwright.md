# Google Search AI 多轮对话（纯 Playwright）

## 说明

本项目提供与 **Google Search AI**（https://www.google.com/search?udm=50）的多轮对话能力，供 Agent 作为工具调用。实现方式为**纯 Playwright** 自动化浏览器，**无需** Chrome 插件或独立 Socket.IO 服务器。

功能对齐 [google-ai-search](https://github.com/your-org/google-ai-search) 的交互效果：发送消息 → 等待 AI 回复完成 → 提取文本返回给 Agent。使用**专用于 Google Chat 的 browser context 与单个 tab**，不与其它用途混用；同一会话内多次调用复用该 tab 实现多轮对话。

## 安装

需安装 Playwright 及 Chromium（若使用「自行启动浏览器」模式）：

```bash
pip install playwright
playwright install chromium
```

若使用「连接本机 Chrome 调试端口」模式，仅需 `pip install playwright`，无需 `playwright install chromium`（与 read_rednote 一致）。

## 配置

在 `~/.nanobot/config.json` 的 `tools.googleAiChat` 中配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | boolean | `false` | 是否启用 google_ai_chat 工具 |
| `responseTimeout` | int | `90` | 单轮回复最大等待秒数 |
| `headless` | boolean | `true` | 是否无头模式（仅在使用 Playwright 自启浏览器时有效） |
| `useCdp` | boolean | `false` | 是否通过 CDP 连接本机已开启调试的 Chrome |
| `cdpPort` | int | `19327` | Chrome 调试端口（与 tools.chromeDebug.cdpPort 一致时便于共用） |

示例（启用工具，使用 Playwright 自启 Chromium）：

```json
"tools": {
  "googleAiChat": {
    "enabled": true,
    "responseTimeout": 90,
    "headless": true,
    "useCdp": false,
    "cdpPort": 19327
  }
}
```

使用本机 Chrome 调试端口（可与 read_rednote 共用同一 Chrome）：

```json
"googleAiChat": {
  "enabled": true,
  "useCdp": true,
  "cdpPort": 19327
}
```

## 使用

- Agent 调用工具 `google_ai_chat`，传入 `message` 发送一条消息，工具会返回 Google Search AI 的回复文本。
- 使用专用于 Google Chat 的独立 tab（在独立 context 中），同一会话内多次调用复用该 tab 延续对话。
- 传入 `end_conversation: true`（`message` 可留空）可结束当前对话并清空该 tab。

## 与 google-ai-search 项目对比

| 项目 | 实现方式 | 依赖 |
|------|----------|------|
| google-ai-search | Chrome 扩展 + 独立 FastAPI/Socket.IO 服务 | 需安装扩展、运行 server、浏览器保持打开对应标签页 |
| 本项目 | 纯 Playwright | 仅需 `pip install playwright`（可选 `playwright install chromium`） |

无需扩展、无需单独起服务，由 nanobot Agent 直接通过 Playwright 与 Google Search AI 页面交互。
