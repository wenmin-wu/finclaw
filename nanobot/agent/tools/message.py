"""Message tool for sending messages to users."""

from typing import Any, Awaitable, Callable

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage


class MessageTool(Tool):
    """Tool to send messages to users on chat channels."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
    ):
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id
        self._sent_in_turn: bool = False
        self._cron_deliver_auto: bool = False

    def set_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        cron_deliver_auto: bool = False,
    ) -> None:
        """Set the current message context (and whether this is a cron job with deliver=auto)."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id
        self._cron_deliver_auto = cron_deliver_auto

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    def start_turn(self) -> None:
        """Reset per-turn send tracking."""
        self._sent_in_turn = False

    @property
    def name(self) -> str:
        return "message"

    @property
    def description(self) -> str:
        return (
            "Send a message to the user. Use this when you want to communicate something. "
            "When this is a cron job with deliver=auto, the first call returns a confirmation prompt; "
            "call again with confirm_send=true only if the alert condition is met."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The message content to send. For cron+deliver=auto, only send when the alert condition is met."
                },
                "channel": {
                    "type": "string",
                    "description": "Optional: target channel (telegram, discord, etc.)"
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional: target chat/user ID"
                },
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: list of file paths to attach (images, audio, documents)"
                },
                "confirm_send": {
                    "type": "boolean",
                    "description": "For cron+deliver=auto: set to true only after confirming the alert condition is met. Omit or false: first call returns a prompt; call again with confirm_send=true to send.",
                    "default": False,
                },
            },
            "required": ["content"]
        }

    async def execute(
        self,
        content: str,
        channel: str | None = None,
        chat_id: str | None = None,
        message_id: str | None = None,
        media: list[str] | None = None,
        confirm_send: bool = False,
        **kwargs: Any
    ) -> str:
        channel = channel or self._default_channel
        chat_id = chat_id or self._default_chat_id
        message_id = message_id or self._default_message_id

        if not channel or not chat_id:
            return "Error: No target channel/chat specified"

        if not self._send_callback:
            return "Error: Message sending not configured"

        # Cron job with deliver=auto: require explicit confirm_send before actually sending
        if self._cron_deliver_auto and not confirm_send:
            preview = content[:200] + "..." if len(content) > 200 else content
            return (
                "[CONFIRM_NEEDED] You requested to send a message. This is a cron job with deliver=auto. "
                "Only send if the alert condition is met. Do not send for routine completion.\n\n"
                f"Preview: {preview!r}\n\n"
                "If the alert condition is met, call message again with the same content and confirm_send=true to send. "
                "If the alert condition is not met, do not call again (message will not be sent)."
            )

        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            media=media or [],
            metadata={
                "message_id": message_id,
            }
        )

        try:
            await self._send_callback(msg)
            if channel == self._default_channel and chat_id == self._default_chat_id:
                self._sent_in_turn = True
            media_info = f" with {len(media)} attachments" if media else ""
            return f"Message sent to {channel}:{chat_id}{media_info}"
        except Exception as e:
            return f"Error sending message: {str(e)}"
