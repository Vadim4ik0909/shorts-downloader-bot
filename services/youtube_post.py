import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, Tuple
import aiohttp

from config import TEMP_DIR
from services.models import DownloadResult, MediaItem

logger = logging.getLogger(__name__)


async def handle_youtube_community_post(url: str) -> Tuple[Optional[DownloadResult], Optional[str]]:
    """
    Обробляє дописи спільноти YouTube (/post/... або /community...).
    Повертає (DownloadResult, None) якщо знайдено фото,
    або (None, error_message) з точним поясненням для користувача.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 404:
                    return None, "❌ **Цей допис або відео було видалено автором із YouTube (404 Not Found).**"
                if resp.status != 200:
                    return None, f"⚠️ YouTube повернув статус {resp.status} на цей допис."

                html = await resp.text()

        # Шукаємо ytInitialData з даними допису
        match = re.search(r"var ytInitialData\s*=\s*({.+?});</script>", html)
        img_urls = []
        post_text = "Допис зі спільноти YouTube"

        if match:
            try:
                data = json.loads(match.group(1))
                data_str = json.dumps(data)
                # Шукаємо всі високоякісні зображення з CDN YouTube (yt3.ggpht.com)
                found = re.findall(r"https://yt3\.ggpht\.com/[a-zA-Z0-9_\-=]+", data_str)
                for u in found:
                    # Ігноруємо аватарки каналів (зазвичай малого розміру)
                    if "=s" in u and ("=s88" in u or "=s48" in u or "=s176" in u):
                        continue
                    # Замінюємо розмір на максимальний (=s0 означає оригінальну роздільну здатність)
                    clean_u = re.sub(r"=s\d+.*", "=s0", u)
                    if clean_u not in img_urls:
                        img_urls.append(clean_u)
            except Exception as e:
                logger.warning(f"Помилка парсингу ytInitialData: {e}")

        # Якщо знайдено зображення в пості — завантажуємо їх як нестиснені документи
        if img_urls:
            session_id = uuid.uuid4().hex[:8]
            work_dir = TEMP_DIR / f"yt_post_{session_id}"
            work_dir.mkdir(parents=True, exist_ok=True)
            items = []

            async with aiohttp.ClientSession() as dl_session:
                for idx, img_url in enumerate(img_urls[:10], start=1):
                    async with dl_session.get(img_url, timeout=aiohttp.ClientTimeout(total=20)) as img_resp:
                        if img_resp.status == 200:
                            p = work_dir / f"photo_{idx:02d}.jpg"
                            p.write_bytes(await img_resp.read())
                            items.append(
                                MediaItem(
                                    media_type="document",
                                    file_path=p,
                                    caption=post_text if idx == 1 else None
                                )
                            )

            if items:
                return DownloadResult(title=post_text, items=items, temp_dir=work_dir, source="youtube_community"), None

        # Якщо це текстовий пост або опитування без фотографій
        return None, (
            "ℹ️ **Це публікація зі вкладки «Спільнота» YouTube (Community Post), а не відео-шортс.**\n\n"
            "У цьому дописі немає відеофайлу. Надішліть посилання безпосередньо на відео або шортс!"
        )

    except Exception as e:
        logger.error(f"Помилка обробки YouTube community post: {e}", exc_info=True)
        return None, "❌ Не вдалося обробити допис зі спільноти YouTube."
