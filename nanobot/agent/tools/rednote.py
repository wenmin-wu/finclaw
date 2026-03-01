"""小红书（RedNote）笔记阅读工具，通过 Playwright 连接 Chrome 调试端口获取正文与图片。"""

from __future__ import annotations

import base64
import re
from typing import Any

import httpx
from loguru import logger

from nanobot.agent.tools.base import Tool

NOTE_CONTAINER = ".note-container"
MEDIA_CONTAINER = ".media-container"


def _extract_redbook_url(share_text: str) -> str:
    """从输入中解析 xhslink 或 xiaohongshu 链接。"""
    if share_text.startswith(("http://", "https://")):
        return share_text.strip()
    xhslink = re.search(r"https?://xhslink\.com/[a-zA-Z0-9/]+", share_text, re.I)
    if xhslink:
        return xhslink.group(0)
    xhs = re.search(r"https?://(?:www\.)?xiaohongshu\.com/[^\s,]+", share_text, re.I)
    if xhs:
        return xhs.group(0)
    return "https://" + share_text.strip() if share_text.strip() else ""


async def _fetch_image_as_base64(url: str, page_url: str, timeout: float = 15.0) -> str | None:
    """拉取图片 URL 并返回 data URL。"""
    if not url or not url.strip():
        return None
    u = url.strip()
    if u.startswith("data:"):
        return u
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        from urllib.parse import urljoin
        u = urljoin(page_url, u)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            r = await client.get(u)
            r.raise_for_status()
            raw = r.content
            ctype = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    except Exception as e:
        logger.warning("RedNote: failed to fetch image %s: %s", u[:80], e)
        return None
    if not raw:
        return None
    if "image" not in ctype:
        ctype = "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{ctype};base64,{b64}"


async def _get_note_detail_via_playwright(cdp_url: str, url: str) -> dict[str, Any] | str:
    """通过 CDP 连接 Chrome，打开笔记页并提取标题、正文、作者、图片等。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return (
            "Error: read_rednote 需要 Playwright 库连接已开启调试的 Chrome。"
            "仅需安装：pip install playwright（连接本机 Chrome 时无需执行 playwright install chromium）。"
        )

    target_url = _extract_redbook_url(url)
    if not target_url.startswith(("http://", "https://")):
        return "Error: 无效的小红书链接"

    script = """
    () => {
        const article = document.querySelector('.note-container');
        if (!article) return null;
        const titleEl = article.querySelector('#detail-title') || article.querySelector('.title');
        const title = titleEl ? titleEl.textContent.trim() : '';
        const contentBlock = article.querySelector('.note-scroller');
        if (!contentBlock) return { title, content: '', tags: [], author: '', imgs: [], likes: 0, comments: 0 };
        const contentSpan = contentBlock.querySelector('.note-content .note-text span');
        const content = contentSpan ? contentSpan.textContent.trim() : '';
        const tags = Array.from(contentBlock.querySelectorAll('.note-content .note-text a')).map(a => (a.textContent || '').trim().replace('#', ''));
        const authorEl = article.querySelector('.author-container .info .username');
        const author = authorEl ? authorEl.textContent.trim() : '';
        const interact = document.querySelector('.interact-container');
        const likesStr = interact ? (interact.querySelector('.like-wrapper .count') || {}).textContent || '' : '';
        const commentsStr = interact ? (interact.querySelector('.chat-wrapper .count') || {}).textContent || '' : '';
        const imgs = Array.from(document.querySelectorAll('.media-container img')).map(img => img.src || img.getAttribute('src') || '').filter(Boolean);
        const likes = likesStr.includes('万') ? parseFloat(likesStr.replace('万','').trim()) * 10000 : parseFloat(likesStr.replace(/[^\\d.]/g,'')) || 0;
        const comments = commentsStr.includes('万') ? parseFloat(commentsStr.replace('万','').trim()) * 10000 : parseFloat(commentsStr.replace(/[^\\d.]/g,'')) || 0;
        return { title, content, tags, author, imgs, likes, comments };
    }
    """

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url, timeout=15000)
        except Exception as e:
            return f"Error: 无法连接 Chrome（{cdp_url}）。请确认已开启调试模式或本程序已自动启动 Chrome。{e}"

        try:
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = await browser.new_context()
            page = await context.new_page()
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_selector(NOTE_CONTAINER, timeout=25000)
                await page.wait_for_selector(MEDIA_CONTAINER, timeout=10000)
            except Exception as e:
                await page.close()
                return f"Error: 页面加载失败或笔记不存在: {e}"

            try:
                data = await page.evaluate(script)
            finally:
                await page.close()

            if not data:
                return "Error: 未找到笔记内容（页面结构可能已变化）。"
            data["url"] = target_url
            return data
        finally:
            await browser.close()


class ReadRedNoteTool(Tool):
    """
    阅读小红书笔记：返回标题、正文、作者、标签、点赞/评论数及配图（以图片形式供模型分析）。

    通过 Playwright 连接本机 Chrome 调试端口（端口在 config 的 tools.chromeDebug.cdpPort 中配置）。
    若由本程序自动启动 Chrome，会使用独立用户目录，首次使用需在该浏览器中登录小红书。
    """

    def __init__(self, cdp_port: int = 19327, max_images: int = 20):
        self.cdp_port = cdp_port
        self.max_images = max(0, max_images)

    @property
    def name(self) -> str:
        return "read_rednote"

    @property
    def description(self) -> str:
        return (
            "阅读小红书（RedNote）笔记：返回标题、正文、作者、标签、点赞/评论数及配图。"
            "传入笔记链接（xhslink.com 或 xiaohongshu.com）。"
            "使用本机 Chrome 调试端口连接，端口在 config 的 tools.chromeDebug.cdpPort 中配置。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "小红书笔记完整链接（如 https://www.xiaohongshu.com/explore/... 或 https://xhslink.com/...）",
                },
            },
            "required": ["url"],
        }

    async def execute(self, *, url: str, **kwargs: Any) -> str | list[dict[str, Any]]:
        cdp_url = f"http://127.0.0.1:{self.cdp_port}"
        result = await _get_note_detail_via_playwright(cdp_url, url)
        if isinstance(result, str):
            return result

        title = (result.get("title") or "").strip()
        content = (result.get("content") or "").strip()
        author = (result.get("author") or "").strip()
        tags = result.get("tags") or []
        imgs = result.get("imgs") or []
        likes = result.get("likes") or 0
        comments = result.get("comments") or 0
        page_url = result.get("url") or url

        text_parts = [f"标题: {title}"]
        if author:
            text_parts.append(f"作者: {author}")
        if tags:
            text_parts.append(f"标签: {', '.join(tags)}")
        if likes or comments:
            text_parts.append(f"点赞: {likes}  |  评论: {comments}")
        text_parts.append("")
        text_parts.append("正文:")
        text_parts.append(content)
        text_block = "\n".join(text_parts)

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": text_block}]

        for img_url in imgs[: self.max_images]:
            data_url = await _fetch_image_as_base64(img_url, page_url)
            if data_url:
                content_parts.append({"type": "image_url", "image_url": {"url": data_url}})

        if len(content_parts) == 1:
            return text_block
        return content_parts
