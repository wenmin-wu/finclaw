# 定时任务 deliver=auto 与 YAML 导入导出

本项目支持：

1. **deliver 为 `auto`**：由 Agent 自主决定是否通知用户  
2. **cron get**：将定时任务导出为 YAML  
3. **cron add --file / cron update**：从 YAML 导入或更新定时任务  

---

## 1. deliver 模式：always | auto | never

定时任务执行完成后，是否把 Agent 的回复推送给用户，由 `deliver` 控制：

| 取值     | 含义 |
|----------|------|
| `always` | 每次执行后都把最终回复发给用户（默认） |
| `never`  | 不发送回复，仅后台执行 |
| `auto`   | **由 Agent 自主决定**：只有当 Agent 通过 `message` 工具且带上 `confirm_send=true` 时才真正发送；否则不发送 |

### auto 的典型用法

- 定时检查（如每日扫描、价格监控）：  
  - 设置 `deliver=auto`，任务照常跑。  
  - Agent 只有在「满足告警条件」时调用 `message(..., confirm_send=true)` 才会发消息给用户。  
  - 日常无异常时不再发消息，避免打扰。  

- 实现方式：  
  - 执行 cron 时若 `deliver=auto`，会为当次会话设置「cron_deliver_auto」上下文。  
  - `message` 工具首次被调用时不会直接发送，而是返回一段确认提示，要求 Agent 在确认条件满足后再次调用 `message(..., confirm_send=true)` 才真正发送。  

### 配置示例

**CLI 添加任务并设为 auto：**

```bash
nanobot cron add --name "每日检查" --message "检查今日待办与异常" \
  --cron "0 9 * * *" --tz "Asia/Shanghai" --deliver auto \
  --channel telegram --to "YOUR_CHAT_ID"
```

**通过 Agent 的 cron 工具：**

```text
cron(action="add", message="每日检查；仅在有异常时通知", every_seconds=86400, deliver="auto")
cron(action="update", job_id="abc123", deliver="auto")
```

---

## 2. 导出为 YAML：cron get

将当前定时任务导出为 YAML，便于备份或编辑后再导入。

**导出全部任务到 stdout：**

```bash
nanobot cron get
```

**导出到文件：**

```bash
nanobot cron get --output cron-jobs.yml
# 或
nanobot cron get -o cron-jobs.yml
```

**只导出指定 job_id：**

```bash
nanobot cron get JOB_ID -o one-job.yml
```

**包含已禁用任务（默认只导出已启用）：**

```bash
nanobot cron get --all -o all-jobs.yml
```

导出格式示例：

```yaml
jobs:
  - id: abc123
    name: 每日检查
    message: 检查今日待办与异常
    enabled: true
    schedule:
      cron: "0 9 * * *"
      tz: Asia/Shanghai
    deliver: auto
    channel: telegram
    to: "123456"
```

---

## 3. 从 YAML 导入：cron add --file

使用导出的 YAML（或手写的 YAML）批量添加任务。

```bash
nanobot cron add --file cron-jobs.yml
# 或
nanobot cron add -f cron-jobs.yml
```

- 文件中可包含 `jobs` 列表（或单个 `job` 对象）。  
- 每个 job 需包含 `schedule`（`every_seconds` / `cron`+可选 `tz` / `at` 之一）和 `message`；`deliver` 可为 `always`、`auto`、`never`。  
- 已存在 `id` 时会被当作新任务添加（生成新 id），不会覆盖原有任务。若要以「覆盖」方式更新，请用 `cron update`（见下）。  

---

## 4. 更新任务：cron update

按 job_id 更新已有任务，仅修改传入的字段。

**只改 deliver：**

```bash
nanobot cron update JOB_ID --deliver auto
```

**修改时间与 deliver：**

```bash
nanobot cron update JOB_ID --cron "0 8 * * *" --tz Asia/Shanghai --deliver auto
```

**禁用/启用：**

```bash
nanobot cron update JOB_ID --disable
nanobot cron update JOB_ID --enable
```

其他可选参数：`--name`、`--message`、`--every`、`--at`、`--channel`、`--to` 等，与 `cron add` 一致。  

**通过 Agent 的 cron 工具更新：**

```text
cron(action="update", job_id="abc123", deliver="auto")
```

---

## 5. 列表中的 Deliver 列

`nanobot cron list` 会多出一列 **Deliver**，取值为 `always`、`auto` 或 `never`，便于一眼看出每个任务的通知策略。

---

## 6. 相关代码与依赖

- **类型与存储**：`nanobot/cron/types.py`（`CronPayload.deliver` 支持 `bool | Literal["auto"]`）、`nanobot/cron/service.py`（`_parse_deliver` / `_serialize_deliver`、`update_job`、add 时 deliver 解析）。  
- **Agent 行为**：`nanobot/agent/tools/message.py`（`cron_deliver_auto`、`confirm_send`）、`nanobot/agent/loop.py`（`process_direct(..., cron_deliver_auto)`、`_set_tool_context(..., cron_deliver_auto)`）。  
- **CLI**：`nanobot/cli/commands.py`（`cron get`、`cron add --file`、`cron update`、`_job_to_yaml_dict`、`_yaml_job_to_schedule`）。  
- **Cron 工具**：`nanobot/agent/tools/cron.py`（`update` 动作、`deliver` 参数）。  
- **依赖**：`pyyaml` 已加入 `pyproject.toml`，用于 YAML 的读写。  

---

## 更新日期

2025-03
