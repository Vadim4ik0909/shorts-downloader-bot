import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Callable, Optional, Tuple
import yt_dlp

from config import COOKIES_FILE, PROXY, TEMP_DIR
from services.compressor import compress_video_if_needed
from services.models import DownloadResult, MediaItem

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg"}


def format_diagnostic_error(err: Exception) -> str:
    """Формує зрозуміле діагностичне повідомлення про причину збою."""
    err_str = str(err).lower()
    if any(k in err_str for k in ["does not look like a netscape format cookies file", "cookie", "cookiefile"]):
        return (
            "🍪 **Помилка у форматі кукісів `YOUTUBE_COOKIES`!**\n\n"
            "YouTube не зміг розпізнати передані cookies. Будь ласка, скопіюйте їх заново з розширення кнопкою **Copy**."
        )
    if any(k in err_str for k in ["this video is unavailable", "not found", "404", "does not exist"]):
        return "❌ **Це відео або пост було видалено автором із платформи (404 Not Found).**"
    if any(k in err_str for k in ["private video", "sign in if you've been granted access"]):
        return "🔒 **Це відео є приватним. Доступ закрито автором.**"
    if any(k in err_str for k in ["sign in to confirm your age", "age-restricted", "confirm you're 18"]):
        return "🔞 **Це відео має вікові обмеження (18+) і вимагає входу через Google-акаунт.**"
    if any(k in err_str for k in ["confirm you're not a bot", "bot", "too many requests", "429"]):
        return (
            "⚠️ **YouTube тимчасово обмежив запит через анти-бот фільтр дата-центру.**\n\n"
            "💡 **Рішення:**\n"
            "• Зачекайте 1-2 хвилини та повторіть спробу.\n"
            "• Або оновіть кукі у змінній `YOUTUBE_COOKIES` на Railway."
        )
    clean_err = str(err).replace("ERROR: ", "").strip()
    return (
        f"❌ **Не вдалося завантажити контент за цим посиланням.**\n\n"
        f"🔍 **Причина помилки:**\n`{clean_err[:300]}`"
    )


def _run_ytdlp(
    url: str,
    work_dir: Path,
    loop: asyncio.AbstractEventLoop,
    on_progress: Optional[Callable[[float, float, float, Optional[float]], None]] = None
) -> Optional[dict]:
    """Синхронна функція для виконання yt-dlp з підтримкою прогрес-хука та мульти-клієнтного fallback."""
    is_youtube = any(domain in url.lower() for domain in ["youtube.com", "youtu.be"])

    def ytdlp_progress_hook(d):
        if on_progress and d.get("status") == "downloading":
            downloaded = float(d.get("downloaded_bytes") or 0)
            total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
            speed = d.get("speed")
            if total > 0:
                percent = (downloaded / total) * 100.0
                try:
                    asyncio.run_coroutine_threadsafe(
                        on_progress(percent, downloaded, total, speed),
                        loop
                    )
                except Exception:
                    pass

    # Стратегії клієнтів для YouTube з підтримкою обходу блокувань (включаючи web_safari, web_embedded та mweb)
    strategies = [
        {"player_client": ["web_safari", "web_embedded"]},
        {"player_client": ["web_embedded"]},
        {"player_client": ["mweb"], "formats": ["missing_pot"]},
        {"player_client": ["android", "ios"], "formats": ["missing_pot"]},
        {"player_client": ["visionos", "android"], "formats": ["missing_pot"]},
        {"player_client": ["web"], "formats": ["missing_pot"]},
        {"formats": ["missing_pot"]},
        None,
    ] if is_youtube else [None]

    # Найкраща перевірена практика:
    # 1. Спочатку завантажуємо анонімно (None) через web_safari / web_embedded.
    #    Це працює для 99% шортсів блискавично, без ризику блокування сесії 'The page needs to be reloaded'.
    # 2. Якщо відео приватне або 18+ (потрібна авторизація) — використовуємо COOKIES_FILE як резерв.
    cookie_attempts = [None]
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        cookie_attempts.append(COOKIES_FILE)

    last_error = None
    for cookie_file in cookie_attempts:
        for strategy in strategies:
            ydl_opts = {
                "outtmpl": str(work_dir / "%(autonumber)02d_%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": is_youtube,
                "merge_output_format": "mp4",
                "format": "bestvideo+bestaudio/best",
                "progress_hooks": [ytdlp_progress_hook],
                "remote_components": ["ejs:github"],
            }

            if PROXY:
                ydl_opts["proxy"] = PROXY

            if is_youtube and strategy:
                ydl_opts["extractor_args"] = {
                    "youtube": strategy
                }

            if cookie_file and os.path.exists(cookie_file):
                ydl_opts["cookiefile"] = cookie_file

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        return info
            except Exception as e:
                last_error = e
                logger.warning(f"Стратегія {strategy} (cookies={bool(cookie_file)}) завершилась помилкою: {e}. Пробуємо наступну...")

    if last_error:
        raise last_error
    return None


async def download_with_ytdlp(
    url: str,
    on_progress: Optional[Callable[[float, float, float, Optional[float]], None]] = None
) -> Tuple[Optional[DownloadResult], Optional[str]]:
    """
    Асинхронне завантаження медіа за допомогою yt-dlp з поверненням діагностичного повідомлення.
    """
    session_id = uuid.uuid4().hex[:8]
    work_dir = TEMP_DIR / f"ytdlp_{session_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    loop = asyncio.get_running_loop()

    try:
        info = await asyncio.to_thread(_run_ytdlp, url, work_dir, loop, on_progress)
        if not info:
            return None, "❌ Не вдалося отримати інформацію про медіа."

        title = info.get("title") or "Завантажене медіа"
        if not title and "entries" in info and info["entries"]:
            first_entry = info["entries"][0]
            if first_entry:
                title = first_entry.get("title") or "Завантажене медіа"

        downloaded_files = sorted(
            [f for f in work_dir.iterdir() if f.is_file()],
            key=lambda x: x.name
        )

        if not downloaded_files:
            return None, "❌ Жодного файлу не було завантажено."

        items = []
        for file_path in downloaded_files:
            ext = file_path.suffix.lower()

            if ext in VIDEO_EXTENSIONS:
                final_video_path = await compress_video_if_needed(file_path)

                duration = info.get("duration")
                width = info.get("width")
                height = info.get("height")
                items.append(
                    MediaItem(
                        media_type="video",
                        file_path=final_video_path,
                        caption=title,
                        width=width,
                        height=height,
                        duration=int(duration) if duration else None
                    )
                )
            elif ext in IMAGE_EXTENSIONS:
                items.append(
                    MediaItem(
                        media_type="document",
                        file_path=file_path,
                        caption=title if len(items) == 0 else None
                    )
                )
            elif ext in AUDIO_EXTENSIONS:
                items.append(
                    MediaItem(
                        media_type="audio",
                        file_path=file_path,
                        caption=title
                    )
                )

        if not items:
            return None, "❌ Не знайдено підтримуваних відео або фото у файлі."

        return DownloadResult(
            title=title,
            items=items,
            temp_dir=work_dir,
            source="yt-dlp"
        ), None

    except Exception as e:
        logger.error(f"Помилка при роботі yt-dlp для {url}: {e}", exc_info=True)
        return None, format_diagnostic_error(e)
