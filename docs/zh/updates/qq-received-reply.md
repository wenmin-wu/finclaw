# QQ 收到消息后的即时回复

## 说明

QQ 通道在收到用户私聊消息后，默认会**先发一条短文案**暗示“已收到”，再进入 Agent 处理流程，避免用户长时间看不到任何反馈。

## 配置

在 `~/.nanobot/config.json` 的 `channels.qq` 中可配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `received_reply` | string | `"收到，正在处理～"` | 收到消息后立即发送的文案；设为 `""` 可关闭此行为 |

示例：

```json
"qq": {
  "enabled": true,
  "app_id": "...",
  "secret": "...",
  "allow_from": [],
  "received_reply": "收到，正在处理～"
}
```

关闭“已收到”提示：

```json
"received_reply": ""
```

## 行为

- 仅对通过 `allow_from` 校验的用户发送（未配置 allow_from 时视为全部允许）。
- 先发送 `received_reply`，再将该条用户消息交给 Agent；用户会先看到“收到”提示，再在稍后收到正式回复。
