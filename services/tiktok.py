import logging
import uuid
from pathlib import Path
from typing import Optional
import aiohttp

from config import MAX_FILE_SIZE_BYTES, TEMP_DIR
from services.compressor import compress_video_if_needed
from services.models import DownloadResult, MediaItem

logger = logging.getLogger(__name__)

TIKWM_API_URL = "https://www.tikwm.com/api/"


async def download_tiktok(url: str) -> Optional[DownloadResult]:
    """
    Завантажує контент з TikTok (відео або фото-слайдшоу) за допомогою TikWM API.
    """
    session_id = uuid.uuid4().hex[:8]
    work_dir = TEMP_DIR / f"tiktok_{session_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(TIKWM_API_URL, params={"url": url}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    logger.warning(f"TikWM повернув HTTP статус {resp.status}")
                    return None
                data = await resp.json()

            if not data or data.get("code") != 0 or "data" not in data:
                logger.warning(f"Помилка від TikWM API: {data.get('msg')}")
                return None

            info = data["data"]
            title = info.get("title") or "TikTok"
            items = []

            # 1. Фото-слайдшоу
            images = info.get("images")
            if images and isinstance(images, list) and len(images) > 0:
                logger.info(f"Знайдено TikTok слайдшоу з {len(images)} фотографій")
                for idx, img_url in enumerate(images, start=1):
                    img_path = work_dir / f"photo_{idx:02d}.jpg"
                    async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=20)) as img_resp:
                        if img_resp.status == 200:
                            content = await img_resp.read()
                            img_path.write_bytes(content)
                            items.append(
                                MediaItem(
                                    media_type="photo",
                                    file_path=img_path,
                                    caption=title if idx == 1 else None
                                )
                            )

                music_url = info.get("music")
                if music_url:
                    music_path = work_dir / "music.mp3"
                    try:
                        async with session.get(music_url, timeout=aiohttp.ClientTimeout(total=20)) as m_resp:
                            if m_resp.status == 200:
                                music_path.write_bytes(await m_resp.read())
                                items.append(
                                    MediaItem(
                                        media_type="audio",
                                        file_path=music_path,
                                        caption=info.get("music_info", {}).get("title") or "Музика зі слайдшоу"
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"Не вдалося завантажити аудіо для TikTok: {e}")

                if items:
                    return DownloadResult(title=title, items=items, temp_dir=work_dir, source="tiktok_photos")

            # 2. Відео
            video_url = info.get("play") or info.get("wmplay")
            if video_url:
                video_path = work_dir / "video.mp4"
                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=30)) as v_resp:
                    if v_resp.status == 200:
                        content = await v_resp.read()
                        video_path.write_bytes(content)

                        # Автоматичне стиснення відео при необхідності
                        final_video_path = await compress_video_if_needed(video_path)

                        items.append(
                            MediaItem(
                                media_type="video",
                                file_path=final_video_path,
                                caption=title,
                                duration=info.get("duration")
                            )
                        )
                        return DownloadResult(title=title, items=items, temp_dir=work_dir, source="tiktok_video")

    except Exception as e:
        logger.error(f"Виняток при завантаженні через TikWM: {e}", exc_info=True)

    return None
