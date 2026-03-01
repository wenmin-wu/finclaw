"""Cron tool for scheduling reminders and tasks."""

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule


class CronTool(Tool):
    """Tool to schedule reminders and recurring tasks."""
    
    def __init__(self, cron_service: CronService):
        self._cron = cron_service
        self._channel = ""
        self._chat_id = ""
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context for delivery."""
        self._channel = channel
        self._chat_id = chat_id
    
    @property
    def name(self) -> str:
        return "cron"
    
    @property
    def description(self) -> str:
        return (
            "Schedule reminders and recurring tasks. Actions: add, list, remove, update. "
            "deliver: always (always send response), auto (agent decides via message tool), never."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove", "update"],
                    "description": "Action to perform",
                },
                "message": {
                    "type": "string",
                    "description": "Reminder message (for add); omit in update to leave unchanged",
                },
                "every_seconds": {"type": "integer", "description": "Interval in seconds (for add/update)"},
                "cron_expr": {"type": "string", "description": "Cron expression e.g. '0 9 * * *' (for add/update)"},
                "tz": {"type": "string", "description": "IANA timezone for cron (e.g. 'America/Vancouver')"},
                "at": {"type": "string", "description": "ISO datetime for one-time run (for add/update)"},
                "job_id": {"type": "string", "description": "Job ID (for remove/update). Get from list."},
                "deliver": {
                    "type": "string",
                    "enum": ["always", "auto", "never"],
                    "description": "When to deliver response: always, auto (agent decides), never (for add/update)",
                },
                "name": {"type": "string", "description": "Job name (for update)"},
                "enabled": {"type": "boolean", "description": "Enable or disable job (for update)"},
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        message: str = "",
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        tz: str | None = None,
        at: str | None = None,
        job_id: str | None = None,
        deliver: str = "always",
        name: str | None = None,
        enabled: bool | None = None,
        **kwargs: Any
    ) -> str:
        if action == "add":
            return self._add_job(message, every_seconds, cron_expr, tz, at, deliver)
        if action == "list":
            return self._list_jobs()
        if action == "remove":
            return self._remove_job(job_id)
        if action == "update":
            return self._update_job(job_id, name, message, every_seconds, cron_expr, tz, at, deliver, enabled)
        return f"Unknown action: {action}"

    def _add_job(
        self,
        message: str,
        every_seconds: int | None,
        cron_expr: str | None,
        tz: str | None,
        at: str | None,
        deliver: str = "always",
    ) -> str:
        if not message or (isinstance(message, str) and not message.strip()):
            return "Error: message is required for add and must be non-empty"
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id). Cron needs this to deliver responses."
        if deliver not in ("always", "auto", "never"):
            deliver = "always"
        deliver_value: bool | str = {"always": True, "auto": "auto", "never": False}[deliver]
        if tz and not cron_expr:
            return "Error: tz can only be used with cron_expr"
        if tz:
            from zoneinfo import ZoneInfo
            try:
                ZoneInfo(tz)
            except (KeyError, Exception):
                return f"Error: unknown timezone '{tz}'"

        delete_after = False
        if every_seconds is not None:
            if every_seconds < 1:
                return "Error: every_seconds must be at least 1"
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            cron_expr = cron_expr.strip() if cron_expr else ""
            if not cron_expr:
                return "Error: cron_expr cannot be empty"
            schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
        elif at:
            at = (at or "").strip()
            if not at:
                return "Error: at cannot be empty (use ISO format)"
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
                at_ms = int(dt.timestamp() * 1000)
                schedule = CronSchedule(kind="at", at_ms=at_ms)
                delete_after = True
            except (ValueError, TypeError) as e:
                return f"Error: invalid at datetime: {e}"
        else:
            return "Error: for add provide exactly one: every_seconds, cron_expr, or at"

        job = self._cron.add_job(
            name=message[:30],
            schedule=schedule,
            message=message,
            deliver=deliver_value,
            channel=self._channel,
            to=self._chat_id,
            delete_after_run=delete_after,
        )
        return f"Created job '{job.name}' (id: {job.id})"
    
    def _list_jobs(self) -> str:
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        lines = [f"- {j.name} (id: {j.id}, {j.schedule.kind})" for j in jobs]
        return "Scheduled jobs:\n" + "\n".join(lines)
    
    def _remove_job(self, job_id: str | None) -> str:
        if not job_id or (isinstance(job_id, str) and not job_id.strip()):
            return "Error: job_id is required for remove. Get IDs from cron(action='list')."
        if self._cron.remove_job(job_id.strip()):
            return f"Removed job {job_id}"
        return f"Job {job_id} not found"

    def _update_job(
        self,
        job_id: str | None,
        name: str | None,
        message: str | None,
        every_seconds: int | None,
        cron_expr: str | None,
        tz: str | None,
        at: str | None,
        deliver: str | None,
        enabled: bool | None,
    ) -> str:
        if not job_id or (isinstance(job_id, str) and not job_id.strip()):
            return (
                "Error: job_id is required for update. "
                "Example: cron(action='update', job_id='abc123', deliver='auto')."
            )
        deliver_val: bool | str | None = None
        if deliver is not None:
            if deliver not in ("always", "auto", "never"):
                return "Error: deliver must be one of: always, auto, never"
            deliver_val = {"always": True, "auto": "auto", "never": False}[deliver]
        job_id = job_id.strip() if isinstance(job_id, str) else job_id
        msg_opt = message.strip() if (message and isinstance(message, str) and message.strip()) else None
        at_opt = at.strip() if (at and isinstance(at, str) and at.strip()) else None
        job = self._cron.update_job(
            job_id,
            name=name,
            message=msg_opt,
            every_seconds=every_seconds,
            cron_expr=cron_expr.strip() if cron_expr else None,
            tz=tz,
            at=at_opt,
            deliver=deliver_val,
            enabled=enabled,
        )
        if job:
            return f"Updated job '{job.name}' ({job_id})"
        return f"Job {job_id} not found"
