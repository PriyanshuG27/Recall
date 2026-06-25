"""
backend/services/telegram_downloader.py
========================================
Robust Telegram file download service with streaming and retries.
"""

import os
import logging
import asyncio
import httpx
from backend.config import settings

logger = logging.getLogger(__name__)

async def get_telegram_file_info(file_id: str) -> tuple[str, int]:
    """
    Retrieves the file_path and file_size from Telegram getFile API.
    Retries on network/timeout errors up to 3 times.
    """
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in configuration.")

    get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(get_file_url)
                resp.raise_for_status()
                result = resp.json().get("result", {})
                file_path = result.get("file_path")
                file_size = result.get("file_size", 0)
                if not file_path:
                    raise ValueError("Telegram getFile returned empty file_path.")
                return file_path, file_size
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError) as err:
            logger.warning("Timeout/Network error fetching file info for file_id %s on attempt %d/%d: %s", file_id, attempt, max_retries, err)
            if attempt == max_retries:
                raise
            await asyncio.sleep(attempt)
        except Exception as err:
            logger.error("Error fetching file info for file_id %s on attempt %d/%d: %s", file_id, attempt, max_retries, err)
            if attempt == max_retries:
                raise
            await asyncio.sleep(attempt)
    raise RuntimeError("Unreachable")

async def download_telegram_file_robust(file_id: str, local_path: str, max_size_bytes: int) -> str:
    """
    Downloads a file from Telegram API and saves it locally.
    Uses streaming and retries on timeouts/errors up to 3 times.
    Returns the file_path from Telegram (useful for determining extension/filename).
    """
    file_path, file_size = await get_telegram_file_info(file_id)
    if file_size > max_size_bytes:
        raise ValueError(f"File size {file_size} exceeds limit of {max_size_bytes} bytes.")
        
    bot_token = settings.TELEGRAM_BOT_TOKEN
    download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # Create a client with a generous read timeout for the file download stream
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=30.0)) as client:
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    with open(local_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                logger.info("Successfully downloaded file_id %s to %s on attempt %d", file_id, local_path, attempt)
                return file_path
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError) as err:
            logger.warning("Timeout/Network error streaming file_id %s on attempt %d/%d: %s", file_id, attempt, max_retries, err)
            if attempt == max_retries:
                raise
            await asyncio.sleep(attempt)
        except Exception as err:
            logger.error("Unexpected error streaming file_id %s on attempt %d/%d: %s", file_id, attempt, max_retries, err)
            if attempt == max_retries:
                raise
            await asyncio.sleep(attempt)
    raise RuntimeError("Unreachable")
