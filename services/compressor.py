import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import json
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Цільовий ліміт для Telegram (47 МБ з запасом для заголовків)
TARGET_MAX_SIZE_BYTES = 47 * 1024 * 1024


async def get_video_metadata(video_path: Path) -> Dict:
    """Визначає точні параметри відео (ширина, висота, тривалість, кодек) через ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,codec_name",
        "-of", "json",
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
            data = json.loads(stdout.decode())
            streams = data.get("streams", [])
            if streams:
                s = streams[0]
                dur_str = s.get("duration")
                dur = float(dur_str) if dur_str and dur_str != "N/A" else None
                return {
                    "width": s.get("width"),
                    "height": s.get("height"),
                    "duration": dur,
                    "vcodec": s.get("codec_name"),
                }
    except Exception as e:
        logger.warning(f"ffprobe не зміг отримати метадані: {e}")
    return {}


async def ensure_telegram_compatible_high_quality(video_path: Path) -> Tuple[Path, Dict]:
    """
    Гарантує максимальну якість відео для Telegram:
    1. Визначає точні габарити (width, height, duration) для передачі в Telegram API.
    2. Якщо розмір > 47 МБ — оптимізує бітрейт без втрати роздільної здатності.
    3. Якщо кодек не h264 (наприклад, av01 або vp9 або webm), конвертує в H.264 High Profile
       з візуально безвтратним CRF 18 та AAC 192k, щоб Telegram не знижував якість до 360p.
    """
    meta = await get_video_metadata(video_path)
    file_size = video_path.stat().st_size
    vcodec = (meta.get("vcodec") or "").lower()
    needs_transcode = vcodec in ("av1", "av01", "vp9", "vp8", "hevc", "h265") or video_path.suffix.lower() == ".webm"

    # Випадок 1: Відео перевищує ліміт 47 МБ — необхідне розумне стиснення
    if file_size > TARGET_MAX_SIZE_BYTES:
        logger.info(f"Файл {video_path.name} ({file_size / (1024 * 1024):.2f} MB) перевищує ліміт. Починаємо стиснення...")
        duration = meta.get("duration") or 60.0

        target_total_bits = 45 * 1024 * 1024 * 8
        target_total_bps = target_total_bits / duration

        audio_bps = 128 * 1000
        video_bps = max(200_000, int(target_total_bps - audio_bps))
        max_rate = int(video_bps * 1.25)
        buf_size = int(video_bps * 2)

        compressed_path = video_path.with_name(f"optimized_{video_path.stem}.mp4")

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
            await proc.communicate()
            if proc.returncode == 0 and compressed_path.exists():
                try:
                    video_path.unlink()
                except Exception:
                    pass
                new_meta = await get_video_metadata(compressed_path)
                return compressed_path, new_meta
        except Exception as e:
            logger.error(f"Помилка при стисненні: {e}", exc_info=True)

    # Випадок 2: Кодек не H.264 (наприклад, AV1 або VP9), через що Telegram перекодовує відео в 360p
    elif needs_transcode:
        logger.info(f"Конвертуємо {vcodec} в нативний H.264 для 100% якості в Telegram...")
        h264_path = video_path.with_name(f"h264_{video_path.stem}.mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-c:v", "libx264",
            "-crf", "18",  # Візуально безвтратна якість (1:1 з оригіналом)
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(h264_path)
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0 and h264_path.exists():
                try:
                    video_path.unlink()
                except Exception:
                    pass
                new_meta = await get_video_metadata(h264_path)
                return h264_path, new_meta
        except Exception as e:
            logger.warning(f"Не вдалося перекодувати в h264: {e}")

    return video_path, meta


async def compress_video_if_needed(video_path: Path) -> Path:
    """Зворотна сумісність: викликає ensure_telegram_compatible_high_quality та повертає оптимізований шлях."""
    final_path, _ = await ensure_telegram_compatible_high_quality(video_path)
    return final_path
