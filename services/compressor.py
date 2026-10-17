import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Цільовий ліміт для Telegram (47 МБ з запасом для заголовків)
TARGET_MAX_SIZE_BYTES = 47 * 1024 * 1024


async def get_video_duration(video_path: Path) -> Optional[float]:
    """Визначає тривалість відео у секундах за допомогою ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0 and stdout:
            return float(stdout.decode().strip())
    except Exception as e:
        logger.warning(f"Не вдалося отримати тривалість відео через ffprobe: {e}")
    return None


async def compress_video_if_needed(video_path: Path) -> Path:
    """
    Перевіряє розмір відео. Якщо він перевищує ліміт Telegram (50 МБ),
    виконує інтелектуальне стиснення через ffmpeg до розміру ~45 МБ.
    """
    file_size = video_path.stat().st_size
    if file_size <= TARGET_MAX_SIZE_BYTES:
        return video_path

    logger.info(f"Файл {video_path.name} ({file_size / (1024 * 1024):.2f} MB) перевищує ліміт. Починаємо стиснення...")

    duration = await get_video_duration(video_path)
    if not duration or duration <= 0:
        duration = 60.0  # Дефолтне значення, якщо ffprobe не визначив тривалість

    # Розрахунок бітрейту під цільовий розмір 45 МБ
    target_total_bits = 45 * 1024 * 1024 * 8
    target_total_bps = target_total_bits / duration

    audio_bps = 128 * 1000
    video_bps = max(150_000, int(target_total_bps - audio_bps))
    max_rate = int(video_bps * 1.25)
    buf_size = int(video_bps * 2)

    compressed_path = video_path.with_name(f"compressed_{video_path.stem}.mp4")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-c:v", "libx264",
        "-b:v", str(video_bps),
        "-maxrate", str(max_rate),
        "-bufsize", str(buf_size),
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(compressed_path)
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode == 0 and compressed_path.exists():
            new_size = compressed_path.stat().st_size
            logger.info(
                f"Відео успішно стиснуто: {file_size / (1024 * 1024):.2f} MB -> "
                f"{new_size / (1024 * 1024):.2f} MB"
            )
            # Видаляємо оригінальний великий файл
            try:
                video_path.unlink()
            except Exception:
                pass
            return compressed_path
        else:
            logger.error(f"Помилка ffmpeg при стисненні: {stderr.decode()[-500:]}")
    except Exception as e:
        logger.error(f"Виняток при стисненні відео: {e}", exc_info=True)

    return video_path
