import logging
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

from services.models import DownloadResult
from services.tiktok import download_tiktok
from services.ytdlp_service import download_with_ytdlp

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_+.~#?&/=]*")


def extract_first_url(text: str) -> Optional[str]:
    """Витягує перше посилання з текстового повідомлення."""
    if not text:
        return None
    match = URL_REGEX.search(text)
    return match.group(0) if match else None


async def download_media(
    url: str,
    on_progress: Optional[Callable[[float, float, float, Optional[float]], None]] = None
) -> Optional[DownloadResult]:
    """
    Головний диспетчер завантаження з підтримкою прогрес-бару.
    """
    url_lower = url.lower()

    # 1. Спеціальна обробка TikTok (підтримує відео та окремі фотографії слайдшоу)
    if any(domain in url_lower for domain in ["tiktok.com", "douyin.com"]):
        logger.info(f"Спроба завантажити TikTok через TikWM API: {url}")
        result = await download_tiktok(url)
        if result and result.items:
            return result
        logger.info("TikWM не зміг завантажити контент, перемикаємось на yt-dlp...")

    # 2. Завантаження через yt-dlp (YouTube Shorts, Instagram, TikTok fallback тощо)
    logger.info(f"Завантаження через yt-dlp: {url}")
    return await download_with_ytdlp(url, on_progress=on_progress)


def cleanup_result(result: Optional[DownloadResult]) -> None:
    """Безпечно видаляє тимчасову папку із завантаженими файлами."""
    if result and result.temp_dir and isinstance(result.temp_dir, Path):
        try:
            if result.temp_dir.exists():
                shutil.rmtree(result.temp_dir, ignore_errors=True)
                logger.info(f"Тимчасову директорію {result.temp_dir} успішно видалено")
        except Exception as e:
            logger.warning(f"Не вдалося видалити тимчасову директорію {result.temp_dir}: {e}")
