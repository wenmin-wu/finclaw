"""File system tools: read, write, edit."""

import base64
import difflib
import mimetypes
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

_IMAGE_MIME_PREFIXES = ("image/jpeg", "image/png", "image/gif", "image/webp")


def _resolve_path(path: str, workspace: Path | None = None, allowed_dir: Path | None = None) -> Path:
    """Resolve path against workspace (if relative) and enforce directory restriction."""
    p = Path(path).expanduser()
    if not p.is_absolute() and workspace:
        p = workspace / p
    resolved = p.resolve()
    if allowed_dir:
        try:
            resolved.relative_to(allowed_dir.resolve())
        except ValueError:
            raise PermissionError(f"Path {path} is outside allowed directory {allowed_dir}")
    return resolved


class ReadFileTool(Tool):
    """Tool to read file contents with optional line range and image support."""

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        max_line_length: int = 2000,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._max_line_length = max_line_length

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file at the given path. "
            "For text files: use line_offset and n_lines to read a specific line range (1-based). "
            "For image files (jpg, png, gif, webp): the image is shown to you for visual analysis. "
            "IMPORTANT: read_file does NOT send the image to the user; use the message tool with media_paths to send images."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The file path to read"},
                "line_offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Line number to start reading from (1-based). Omit to read from the start.",
                },
                "n_lines": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Number of lines to read. Default 1000 if omitted.",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        line_offset: int | None = None,
        n_lines: int | None = None,
        **kwargs: Any
    ) -> str | list[dict[str, Any]]:
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            mime, _ = mimetypes.guess_type(str(file_path))
            if mime and mime in _IMAGE_MIME_PREFIXES:
                b64 = base64.b64encode(file_path.read_bytes()).decode()
                return [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": f"[Image: {path}]"},
                ]

            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                size = file_path.stat().st_size
                return f"Error: {path} is a binary file ({size:,} bytes) and cannot be read as text."

            lines = content.split("\n")
            total_lines = len(lines)
            start = (line_offset or 1) - 1
            limit = n_lines or 1000
            if start < 0:
                start = 0
            if start >= total_lines:
                return f"Error: line_offset {line_offset or 1} is beyond the file's total lines ({total_lines})"
            end = min(start + limit, total_lines)
            selected_lines = lines[start:end]
            formatted_lines = []
            for i, line in enumerate(selected_lines, start=start + 1):
                if len(line) > self._max_line_length:
                    line = line[: self._max_line_length] + " [truncated]"
                formatted_lines.append(f"{i:>6}\t{line}")
            result = "\n".join(formatted_lines)
            if end < total_lines or line_offset is not None or n_lines is not None:
                result = f"[Lines {start + 1}-{end} of {total_lines}]\n{result}"
            return result
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """Tool to write content to a file."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates parent directories if needed."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write"
                }
            },
            "required": ["path", "content"]
        }
    
    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to {file_path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """Tool to edit a file by replacing text."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "edit_file"
    
    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The file path to edit"},
                "old_text": {"type": "string", "description": "The exact text to find and replace"},
                "new_text": {"type": "string", "description": "The text to replace with"},
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, replace all occurrences of old_text; if false, only the first.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    async def execute(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        **kwargs: Any
    ) -> str:
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
            if not file_path.exists():
                return f"Error: File not found: {path}"

            content = file_path.read_text(encoding="utf-8")

            if old_text not in content:
                return self._not_found_message(old_text, content, path)

            count = content.count(old_text)
            if replace_all:
                new_content = content.replace(old_text, new_text)
                file_path.write_text(new_content, encoding="utf-8")
                return f"Successfully edited {path} - replaced {count} occurrences"
            if count > 1:
                return (
                    f"Warning: old_text appears {count} times. "
                    "Provide more context to make it unique, or set replace_all=true to replace all."
                )
            new_content = content.replace(old_text, new_text, 1)
            file_path.write_text(new_content, encoding="utf-8")
            return f"Successfully edited {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @staticmethod
    def _not_found_message(old_text: str, content: str, path: str) -> str:
        """Build a helpful error when old_text is not found."""
        lines = content.splitlines(keepends=True)
        old_lines = old_text.splitlines(keepends=True)
        window = len(old_lines)

        best_ratio, best_start = 0.0, 0
        for i in range(max(1, len(lines) - window + 1)):
            ratio = difflib.SequenceMatcher(None, old_lines, lines[i : i + window]).ratio()
            if ratio > best_ratio:
                best_ratio, best_start = ratio, i

        if best_ratio > 0.5:
            diff = "\n".join(difflib.unified_diff(
                old_lines, lines[best_start : best_start + window],
                fromfile="old_text (provided)", tofile=f"{path} (actual, line {best_start + 1})",
                lineterm="",
            ))
            return f"Error: old_text not found in {path}.\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
        return f"Error: old_text not found in {path}. No similar text found. Verify the file content."


class ListDirTool(Tool):
    """Tool to list directory contents."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "list_dir"
    
    @property
    def description(self) -> str:
        return "List the contents of a directory."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            dir_path = _resolve_path(path, self._workspace, self._allowed_dir)
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"

            items = []
            for item in sorted(dir_path.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")

            if not items:
                return f"Directory {path} is empty"

            return "\n".join(items)
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
