# 百度文心助手多轮对话（baidu_ai_chat）

## 说明

通过 **agent-browser** 探测 [chat.baidu.com/search](https://chat.baidu.com/search) 页面结构后实现的百度文心多轮对话工具，与 `google_ai_chat` 同构：专用 context + 单 tab，纯 Playwright，无需浏览器插件。

**探测结论**（供后续页面改版时对照）：

- **输入**：`textarea.ci-textarea`（或 `textarea`），placeholder 随页面变化。
- **发送**：无独立发送按钮，使用 **Enter** 提交。
- **回复**：AI 回复在 `p.marklang-paragraph` 中，按出现顺序取第 N 条即为第 N 轮回复。

## 配置

在 `~/.nanobot/config.json` 的 `tools.baiduAiChat` 中配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | boolean | `false` | 是否启用 baidu_ai_chat |
| `responseTimeout` | int | `90` | 单轮回复最大等待秒数 |
| `headless` | boolean | `true` | 无头模式（自启 Chromium 时有效） |
| `useCdp` | boolean | `false` | 是否通过 CDP 连接本机 Chrome |
| `cdpPort` | int | `9222` | Chrome 调试端口（与 `scripts/start-chrome-debug.sh` 一致） |

推荐用法：先启动 Chrome 调试（如 `bash scripts/start-chrome-debug.sh`，端口 9222），再设置 `useCdp: true`、`cdpPort: 9222`。

示例：

```json
"baiduAiChat": {
  "enabled": true,
  "responseTimeout": 90,
  "useCdp": true,
  "cdpPort": 9222
}
```

## 使用

- Agent 调用工具 `baidu_ai_chat`，传入 `message` 发送一条消息，工具返回百度文心的回复文本。
- 同一会话内多次调用复用同一 tab，实现多轮对话。
- 传入 `end_conversation: true` 可结束当前对话并清空该 tab。

## 与 agent-browser 的对应关系

探测时使用的命令示例：

```bash
agent-browser connect 9222
agent-browser open https://chat.baidu.com/search
agent-browser snapshot -i -C    # 得到 textbox [ref=e1]
agent-browser fill @e1 "hello"
agent-browser press Enter
# 回复出现在 paragraph（p.marklang-paragraph）
```

工具内等价逻辑：Playwright 用相同选择器（textarea、Enter、p.marklang-paragraph）在专用 tab 中完成输入、发送与回复提取。
