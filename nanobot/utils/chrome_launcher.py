"""启动 Chrome 调试模式进程，供 read_rednote 等工具通过 CDP 连接。"""

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger


def _find_chrome() -> str | None:
    """查找系统上的 Chrome 或 Chromium 可执行路径。"""
    if platform.system() == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif platform.system() == "Windows":
        candidates = [
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path.home() / "AppData" / "Local" / "Chromium" / "Application" / "chrome.exe",
        ]
        candidates = [str(p) for p in candidates]
    else:
        candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    for exe in candidates:
        if exe in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            path = shutil.which(exe)
            if path:
                return path
        else:
            if Path(exe).exists():
                return exe
    return None


def start_chrome_debug(
    port: int,
    user_data_dir: Path | None = None,
    headless: bool = False,
) -> subprocess.Popen[Any] | None:
    """
    启动 Chrome 并开启远程调试端口，供 Playwright CDP 连接。

    Args:
        port: 调试端口（如 19327），可在 config 中配置。
        user_data_dir: 可选，Chrome 用户数据目录，用于保持登录态（如小红书）。
        headless: 是否无头模式；默认 False，便于用户手动登录。

    Returns:
        子进程 Popen，调用方可在退出时 terminate；若启动失败返回 None。
    """
    chrome = _find_chrome()
    if not chrome:
        logger.warning(
            "Chrome/Chromium not found. Tools that use Chrome debug (e.g. read_rednote) need it. "
            "Install Chrome or set tools.chromeDebug.autoStartChrome=false and start Chrome manually with "
            "--remote-debugging-port={}",
            port,
        )
        return None

    args = [
        chrome,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if user_data_dir:
        user_data_dir = Path(user_data_dir).expanduser().resolve()
        user_data_dir.mkdir(parents=True, exist_ok=True)
        args.append(f"--user-data-dir={user_data_dir}")
    if headless:
        args.append("--headless=new")

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        logger.info("Chrome started for debug (port={}, pid={})", port, proc.pid)
        return proc
    except Exception as e:
        logger.warning("Failed to start Chrome: {}", e)
        return None
