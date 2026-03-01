# Tool Usage Notes

Tool signatures are provided automatically via function calling.
This file documents non-obvious constraints and usage patterns.

## Available Tools (overview)

| 工具 | 功能 |
|------|------|
| **文件操作** | |
| `read_file` | 读取文件内容（支持文本和图片） |
| `write_file` | 写入文件内容（自动创建目录） |
| `edit_file` | 编辑文件（查找替换文本） |
| `list_dir` | 列出目录内容 |
| **网络** | |
| `web_search` | 网页搜索（返回标题、URL、摘要） |
| `web_fetch` | 获取网页内容并提取为可读文本 |
| `read_rednote` | 读取小红书笔记内容 |
| **系统** | |
| `exec` | 执行 shell 命令 |
| **AI/自动化** | |
| `spawn` | 创建子代理处理后台任务 |
| `message` | 发送消息到指定频道（如 Telegram、QQ） |
| **定时任务** | |
| `cron` | 添加/列出/删除定时提醒和周期性任务 |
| **AI 多轮对话**（配置启用后可用） | |
| `google_ai_chat` | 与 Google Search AI 多轮对话（搜索增强） |
| `baidu_ai_chat` | 与百度文心助手多轮对话 |

`google_ai_chat` 与 `baidu_ai_chat` 需在 config 中对应开启（如 `tools.googleAiChat.enabled`、`tools.baiduAiChat.enabled`）后才会出现在工具列表中。

## exec — Safety Limits

- Commands have a configurable timeout (default 60s)
- Dangerous commands are blocked (rm -rf, format, dd, shutdown, etc.)
- Output is truncated at 10,000 characters
- `restrictToWorkspace` config can limit file access to the workspace

## cron — Scheduled Reminders

- Please refer to cron skill for usage.
