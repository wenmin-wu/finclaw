"""Google Search AI 多轮对话工具，纯 Playwright 实现（无需 Chrome 插件）。"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool

GOOGLE_AI_SEARCH_URL = "https://www.google.com/search?udm=50"

# 与 google-ai-search 扩展 content.js 保持一致的选择器
TEXTAREA_SELECTORS = [
    'textarea.ITIRGe[jsname="qyBLR"]',
    'textarea[placeholder*="Ask"]',
    'textarea.ITIRGe',
    'textarea[jsname="qyBLR"]',
    "textarea",
]
SUBMIT_BUTTON_SELECTORS = [
    'button[data-xid="input-plate-send-button"]',
    'button[aria-label="Send"]',
    'button[jsname="H9tDt"][aria-label="Send"]',
]


def _html_to_text(html: str) -> str:
    """Strip HTML to plain text (no extra deps)."""
    if not html:
        return ""
    # Remove script/style
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _send_message_and_wait(
    page: Any,
    message: str,
    response_index: int,
    timeout_ms: int,
) -> str:
    """在已打开的 Google Search AI 页面上发送一条消息并等待第 response_index 条回复完成，返回该条回复的文本。"""
    # 1) 找输入框
    textarea = None
    for sel in TEXTAREA_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                box = await el.bounding_box()
                if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                    textarea = el
                    break
        except Exception:
            continue
    if not textarea:
        raise RuntimeError("Could not find message input textarea on Google Search AI page")

    # 2) 清空并输入
    await textarea.fill("")
    await textarea.press_sequentially(message, delay=10)
    await page.wait_for_timeout(200)

    # 3) 找发送按钮并点击
    submit_btn = None
    for sel in SUBMIT_BUTTON_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                box = await el.bounding_box()
                if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                    disabled = await el.get_attribute("disabled")
                    if disabled is None:
                        submit_btn = el
                        break
        except Exception:
            continue
    if not submit_btn:
        raise RuntimeError("Could not find Send button on Google Search AI page")

    await page.wait_for_timeout(500)
    await submit_btn.click()
    await page.wait_for_timeout(300)

    # 4) 等待第 response_index 条回复完成（.zkL70c 中出现可用的 thumbs down 按钮）
    poll_interval_ms = 500
    elapsed = 0
    while elapsed < timeout_ms:
        done = await page.evaluate(
            """
            (responseIndex) => {
                const containers = document.querySelectorAll('.zkL70c');
                let validCount = 0;
                for (const el of containers) {
                    const btn = el.querySelector('button[aria-label*="Thumbs down"], button[aria-label*="thumbs down"], button[aria-label*="Negative feedback"], button[data-snt="-1"]');
                    if (btn && btn.offsetParent !== null && !btn.disabled) {
                        validCount++;
                        if (validCount === responseIndex) return true;
                    }
                }
                return false;
            }
            """,
            response_index,
        )
        if done:
            break
        await page.wait_for_timeout(poll_interval_ms)
        elapsed += poll_interval_ms

    if elapsed >= timeout_ms:
        raise RuntimeError(f"Response #{response_index} did not complete within {timeout_ms/1000}s")

    # 5) 提取第 response_index 条回复内容（.pWvJNd）
    raw = await page.evaluate(
        """
        (responseIndex) => {
            const elements = document.querySelectorAll('.pWvJNd');
            let validCount = 0;
            for (const el of elements) {
                if (el && el.innerHTML && el.innerHTML.trim().length > 50) {
                    validCount++;
                    if (validCount === responseIndex) {
                        const clone = el.cloneNode(true);
                        clone.querySelectorAll('.VlQBpc, [data-snt], button[aria-label*="Share"], button[aria-label*="feedback"]').forEach(n => n.remove());
                        return clone.innerHTML;
                    }
                }
            }
            return null;
        }
        """,
        response_index,
    )

    if not raw:
        raise RuntimeError(f"Could not find response #{response_index} content (.pWvJNd)")
    return _html_to_text(raw)


async def _ensure_dedicated_tab(
    context: Any | None,
    page: Any | None,
    browser: Any,
    url: str,
    timeout_ms: int,
) -> tuple[Any, Any, int]:
    """确保有一个专用于 Google Chat 的 context 和 tab（page）；若没有则新建。返回 (context, page, next_response_index)。"""
    if page is not None and context is not None:
        try:
            if not page.is_closed():
                current = page.url
                if "google.com/search" in current and "udm=50" in current:
                    count = await page.evaluate(
                        """
                        () => {
                            const containers = document.querySelectorAll('.zkL70c');
                            let n = 0;
                            containers.forEach(el => {
                                const btn = el.querySelector('button[data-snt="-1"], button[aria-label*="Thumbs down"]');
                                if (btn && btn.offsetParent !== null && !btn.disabled) n++;
                            });
                            return n;
                        }
                        """
                    )
                    return context, page, count + 1
        except Exception:
            pass
        try:
            if page and not page.is_closed():
                await page.close()
        except Exception:
            pass

    # Dedicated context for Google Chat only (one tab in it)
    if context is None:
        context = await browser.new_context()
    new_page = await context.new_page()
    await new_page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    await new_page.wait_for_selector("textarea", timeout=timeout_ms)
    return context, new_page, 1


async def _run_google_ai_chat(
    message: str,
    end_conversation: bool,
    response_timeout: int,
    headless: bool,
    use_cdp: bool,
    cdp_port: int,
    *,
    _playwright: Any | None = None,
    _browser: Any | None = None,
    _context: Any | None = None,
    _page: Any | None = None,
) -> tuple[str, Any | None, Any | None, Any | None, Any | None]:
    """
    执行一轮或结束对话。返回 (response_text, playwright, browser, context, page)。
    使用专用于 Google Chat 的 context 和 tab，不与其它用途混用。
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return (
            "Error: google_ai_chat 需要 Playwright。请安装: pip install playwright && playwright install chromium",
            None,
            None,
            None,
            None,
        )

    timeout_ms = response_timeout * 1000
    p = _playwright
    browser = _browser
    context = _context
    page = _page

    if browser is None:
        if p is None:
            p = await async_playwright().__aenter__()
        if use_cdp:
            cdp_url = f"http://127.0.0.1:{cdp_port}"
            try:
                browser = await p.chromium.connect_over_cdp(cdp_url, timeout=15000)
            except Exception as e:
                return (
                    f"Error: 无法连接 Chrome 调试端口 {cdp_port}。请确认已开启调试或使用 tools.chromeDebug。{e}",
                    p,
                    None,
                    None,
                    None,
                )
        else:
            browser = await p.chromium.launch(headless=headless)

    try:
        if end_conversation:
            if page:
                try:
                    if not page.is_closed():
                        await page.goto(GOOGLE_AI_SEARCH_URL, wait_until="domcontentloaded", timeout=15000)
                        await page.close()
                except Exception:
                    pass
                page = None
            return "Conversation ended. You can start a new one with the next message.", p, browser, context, page

        context, page, response_index = await _ensure_dedicated_tab(
            context, page, browser, GOOGLE_AI_SEARCH_URL, timeout_ms
        )
        text = await _send_message_and_wait(page, message, response_index, timeout_ms)
        return text, p, browser, context, page
    except Exception as e:
        logger.exception("Google AI Chat error")
        return f"Error: {e}", p, browser, context, page


class GoogleAIChatTool(Tool):
    """
    与 Google Search AI（https://www.google.com/search?udm=50）进行多轮对话。
    纯 Playwright 实现，无需 Chrome 插件或独立服务器。
    使用专用于 Google Chat 的 browser context 与单个 tab，同一会话内多次调用复用该 tab 实现多轮对话。
    """

    def __init__(
        self,
        response_timeout: int = 90,
        headless: bool = True,
        use_cdp: bool = False,
        cdp_port: int = 19327,
    ):
        self.response_timeout = max(30, response_timeout)
        self.headless = headless
        self.use_cdp = use_cdp
        self.cdp_port = cdp_port
        self._lock = asyncio.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None  # Dedicated context for Google Chat only
        self._page: Any = None     # Dedicated tab in that context

    @property
    def name(self) -> str:
        return "google_ai_chat"

    @property
    def description(self) -> str:
        return (
            "与 Google Search AI 进行多轮对话（搜索增强对话）。"
            "传入 message 发送一条消息并返回 AI 的回复；同一会话内多次调用会延续同一对话。"
            "若 end_conversation 为 true 则结束当前对话。"
            "使用专用于 Google Chat 的独立 tab；浏览器由 Playwright 启动或通过 tools.googleAiChat.useCdp 连接本机 Chrome 调试端口。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要发送给 Google Search AI 的文本（end_conversation 为 true 时可留空）",
                },
                "end_conversation": {
                    "type": "boolean",
                    "description": "若为 true 则结束当前对话并清空页面，不发送 message",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(
        self,
        *,
        message: str = "",
        end_conversation: bool = False,
        **kwargs: Any,
    ) -> str:
        if not (message or "").strip() and not end_conversation:
            return "Error: message 不能为空（或设置 end_conversation=true 结束当前对话）"
        async with self._lock:
            out, self._playwright, self._browser, self._context, self._page = await _run_google_ai_chat(
                message=message.strip(),
                end_conversation=end_conversation,
                response_timeout=self.response_timeout,
                headless=self.headless,
                use_cdp=self.use_cdp,
                cdp_port=self.cdp_port,
                _playwright=self._playwright,
                _browser=self._browser,
                _context=self._context,
                _page=self._page,
            )
            return out
