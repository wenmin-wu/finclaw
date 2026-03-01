"""百度文心助手（chat.baidu.com/search）多轮对话工具，纯 Playwright + 专用 tab。"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool

BAIDU_CHAT_URL = "https://chat.baidu.com/search"

# agent-browser 探测（CDP 19327）：输入框 textarea，Enter 发送，回复在 p.marklang-paragraph。
# 生成状态：生成中 = .ci-submit-pause（图2）；生成结束 = #ci-submit-button-ai.ci-submit-button-ai-active（图1）。据此判断何时拼接完整回复。
TEXTAREA_SELECTORS = [
    "textarea.ci-textarea",
    "textarea.ci-scroll-style",
    "textarea",
]
RESPONSE_PARAGRAPH_SELECTOR = "p.marklang-paragraph"
# 生成结束 = 出现图1（发送按钮）；生成中 = 出现图2（暂停按钮）
SELECTOR_GENERATION_DONE = "#ci-submit-button-ai.ci-submit-button-ai-active"  # 图1
SELECTOR_GENERATING = ".ci-submit-pause"  # 图2


async def _send_message_and_wait(
    page: Any,
    message: str,
    response_index: int,
    timeout_ms: int,
) -> str:
    """在已打开的百度文心页面上发送一条消息（Enter 提交），等待第 response_index 条回复并返回其文本。"""
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
        raise RuntimeError("Could not find message input (textarea) on Baidu chat page")

    # 2) 清空并输入（ElementHandle 无 press_sequentially，用 fill 即可）
    await textarea.fill(message)
    await page.wait_for_timeout(200)

    # 3) 用 Enter 提交（百度文心无独立发送按钮，Enter 发送）
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(500)

    # 4) 等待本条回复出现并流式结束（一条回复可能对应多个 p.marklang-paragraph）
    # 结束条件：出现图1（#ci-submit-button-ai.ci-submit-button-ai-active）即生成结束；或段落数连续稳定 3 次兜底
    start_index = response_index - 1  # 本条回复从第 start_index 个段落开始（0-based）
    poll_interval_ms = 500
    stable_checks = 3  # 兜底：连续 3 次 count 不变认为流式结束
    elapsed = 0
    last_count = 0
    prev_count = -1
    stable_count = 0

    while elapsed < timeout_ms:
        result = await page.evaluate(
            """
            () => {
                const count = document.querySelectorAll('p.marklang-paragraph').length;
                const generationDone = !!document.querySelector('#ci-submit-button-ai.ci-submit-button-ai-active');
                return [count, generationDone];
            }
            """
        )
        count = result[0] if isinstance(result, (list, tuple)) else result
        button_done = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else False
        last_count = count
        if count > start_index:
            if count == prev_count:
                stable_count += 1
            else:
                stable_count = 0
            prev_count = count
            # 至少有一条新段落，且（图1 出现 = 生成结束 或 段落数连续稳定兜底）
            if button_done or stable_count >= stable_checks:
                text = await page.evaluate(
                    """
                    (startIdx, endIdx) => {
                        const els = document.querySelectorAll('p.marklang-paragraph');
                        const parts = [];
                        for (let i = startIdx; i < endIdx && i < els.length; i++) {
                            const t = (els[i].textContent || els[i].innerText || '').trim();
                            if (t) parts.push(t);
                        }
                        return parts.join('\\n\\n');
                    }
                    """,
                    start_index,
                    count,
                )
                if text:
                    return text
        else:
            stable_count = 0
        await page.wait_for_timeout(poll_interval_ms)
        elapsed += poll_interval_ms

    # 超时前若已有新段落，仍返回已抓到的内容，避免完全丢回复
    if last_count > start_index:
        text = await page.evaluate(
            """
            (startIdx, endIdx) => {
                const els = document.querySelectorAll('p.marklang-paragraph');
                const parts = [];
                for (let i = startIdx; i < endIdx && i < els.length; i++) {
                    const t = (els[i].textContent || els[i].innerText || '').trim();
                    if (t) parts.push(t);
                }
                return parts.join('\\n\\n');
            }
            """,
            start_index,
            last_count,
        )
        if text:
            return text
    raise RuntimeError(
        f"Response #{response_index} did not appear within {timeout_ms/1000}s (found {last_count} paragraphs)"
    )


async def _ensure_dedicated_tab(
    context: Any | None,
    page: Any | None,
    browser: Any,
    url: str,
    timeout_ms: int,
) -> tuple[Any, Any, int]:
    """确保有专用于百度文心的 context 和 tab；若没有则新建。返回 (context, page, next_response_index)。"""
    if page is not None and context is not None:
        try:
            if not page.is_closed():
                current = page.url
                if "chat.baidu.com" in current and "search" in current:
                    count = await page.evaluate(
                        """
                        () => document.querySelectorAll('p.marklang-paragraph').length;
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

    if context is None:
        context = await browser.new_context()
    new_page = await context.new_page()
    await new_page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    await new_page.wait_for_selector("textarea", timeout=timeout_ms)
    return context, new_page, 1


async def _run_baidu_ai_chat(
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
    """执行一轮或结束对话。返回 (response_text, playwright, browser, context, page)。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return (
            "Error: baidu_ai_chat 需要 Playwright。请安装: pip install playwright && playwright install chromium",
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
                    f"Error: 无法连接 Chrome 调试端口 {cdp_port}。请先运行 nanobot gateway（会按 tools.chromeDebug 自动启动 Chrome）或手动以 --remote-debugging-port={cdp_port} 启动 Chrome。{e}",
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
                        await page.goto(BAIDU_CHAT_URL, wait_until="domcontentloaded", timeout=15000)
                        await page.close()
                except Exception:
                    pass
                page = None
            return "Conversation ended. You can start a new one with the next message.", p, browser, context, page

        context, page, response_index = await _ensure_dedicated_tab(
            context, page, browser, BAIDU_CHAT_URL, timeout_ms
        )
        text = await _send_message_and_wait(page, message, response_index, timeout_ms)
        return text, p, browser, context, page
    except Exception as e:
        logger.exception("Baidu AI Chat error")
        return f"Error: {e}", p, browser, context, page


class BaiduAIChatTool(Tool):
    """
    与百度文心助手（https://chat.baidu.com/search）多轮对话。
    纯 Playwright，专用 context + 单 tab。输入框为 textarea，Enter 发送，回复从 p.marklang-paragraph 提取。
    """

    def __init__(
        self,
        response_timeout: int = 90,
        headless: bool = True,
        use_cdp: bool = False,
        cdp_port: int = 9222,
    ):
        self.response_timeout = max(30, response_timeout)
        self.headless = headless
        self.use_cdp = use_cdp
        self.cdp_port = cdp_port
        self._lock = asyncio.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    @property
    def name(self) -> str:
        return "baidu_ai_chat"

    @property
    def description(self) -> str:
        return (
            "与百度文心助手（chat.baidu.com/search）多轮对话。"
            "传入 message 发送一条消息并返回 AI 的回复；同一会话内多次调用延续同一对话。"
            "若 end_conversation 为 true 则结束当前对话。"
            "当 tools.baiduAiChat.useCdp=true（默认）时连接本机 Chrome 调试端口（与 gateway 自动启动的 Chrome 共用），在该浏览器内开专用 tab 访问百度文心。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要发送给百度文心的文本（end_conversation 为 true 时可留空）",
                },
                "end_conversation": {
                    "type": "boolean",
                    "description": "若为 true 则结束当前对话并清空页面",
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
            out, self._playwright, self._browser, self._context, self._page = await _run_baidu_ai_chat(
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
