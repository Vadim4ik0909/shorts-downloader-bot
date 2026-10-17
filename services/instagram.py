import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Optional
import aiohttp
import yt_dlp

from config import COOKIES_FILE, TEMP_DIR
from services.compressor import compress_video_if_needed
from services.models import DownloadResult, MediaItem

logger = logging.getLogger(__name__)


async def download_instagram(url: str) -> Optional[DownloadResult]:
    """
    Спеціалізований завантажувач для Instagram (Reels, пости з фото, каруселі).
    Витягує фото в максимальній оригінальній якості та конвертує в JPG.
    """
    session_id = uuid.uuid4().hex[:8]
    work_dir = TEMP_DIR / f"ig_{session_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
    }
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    try:
        def _extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ie = ydl.get_info_extractor("Instagram")
                return ie.extract(url)

        res = await asyncio.to_thread(_extract)
        if not res:
            return None

        title = res.get("title") or "Instagram Media"
        entries = res.get("entries")
        raw_items = list(entries) if entries is not None else [res]

        if not raw_items:
            return None

        headers = res.get("http_headers") or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        items = []
        async with aiohttp.ClientSession(headers=headers) as session:
            for idx, raw_item in enumerate(raw_items, start=1):
                # 1. Якщо це відео
                if raw_item.get("formats"):
                    formats = [f for f in raw_item["formats"] if f.get("url")]
                    if formats:
                        best_video_url = formats[-1]["url"]
                        video_path = work_dir / f"{idx:02d}_video.mp4"
                        async with session.get(best_video_url, timeout=aiohttp.ClientTimeout(total=60)) as v_resp:
                            if v_resp.status == 200:
                                video_path.write_bytes(await v_resp.read())
                                final_video_path = await compress_video_if_needed(video_path)
                                items.append(
                                    MediaItem(
                                        media_type="video",
                                        file_path=final_video_path,
                                        caption=title if len(items) == 0 else None,
                                        duration=raw_item.get("duration"),
                                        width=raw_item.get("width"),
                                        height=raw_item.get("height")
                                    )
                                )

                # 2. Якщо це фото (пост або слайд каруселі)
                elif raw_item.get("thumbnails"):
                    # Беремо останній thumbnail (максимальна якість/роздільність Instagram CDN)
                    best_thumb = raw_item["thumbnails"][-1]
                    img_url = best_thumb.get("url")
                    if img_url:
                        raw_img_path = work_dir / f"{idx:02d}_raw"
                        jpg_img_path = work_dir / f"{idx:02d}_photo.jpg"

                        async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=30)) as img_resp:
                            if img_resp.status == 200:
                                raw_img_path.write_bytes(await img_resp.read())

                                # Конвертуємо через ffmpeg у максимальну якість JPG (-q:v 1) для гарантованого перегляду
                                proc = await asyncio.create_subprocess_exec(
                                    "ffmpeg", "-y", "-i", str(raw_img_path), "-q:v", "1", str(jpg_img_path),
                                    stdout=asyncio.subprocess.DEVNULL,
                                    stderr=asyncio.subprocess.DEVNULL
                                )
                                await proc.communicate()

                                if not jpg_img_path.exists():
                                    raw_img_path.rename(jpg_img_path)
                                else:
                                    raw_img_path.unlink(missing_ok=True)

                                # Відправляємо як 'document' (файл без стиснення Telegram)
                                items.append(
                                    MediaItem(
                                        media_type="document",
                                        file_path=jpg_img_path,
                                        caption=title if len(items) == 0 else None
                                    )
                                )

        if not items:
            logger.warning(f"Не вдалося витягти медіаелементи для Instagram: {url}")
            return None

        return DownloadResult(
            title=title,
            items=items,
            temp_dir=work_dir,
            source="instagram_direct"
        )

    except Exception as e:
        logger.error(f"Помилка при завантаженні Instagram {url}: {e}", exc_info=True)
        return None
