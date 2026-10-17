import time
from typing import Optional


def format_bytes(bytes_count: float) -> str:
    """Форматує байти в читабельний вигляд (КБ, МБ)."""
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} КБ"
    return f"{bytes_count / (1024 * 1024):.1f} МБ"


def render_progress_bar(
    percent: float,
    downloaded_bytes: float,
    total_bytes: float,
    speed: Optional[float] = None
) -> str:
    """
    Генерує візуальний прогрес-бар:
    ⏳ Завантаження: [▓▓▓▓▓░░░░░] 52% (8.4 МБ / 16.1 МБ) • ~2.1 МБ/с
    """
    percent = max(0.0, min(100.0, percent))
    total_blocks = 10
    filled_blocks = int(round((percent / 100.0) * total_blocks))
    empty_blocks = total_blocks - filled_blocks

    bar = "▓" * filled_blocks + "░" * empty_blocks
    downloaded_str = format_bytes(downloaded_bytes)
    total_str = format_bytes(total_bytes) if total_bytes > 0 else "..."

    speed_str = ""
    if speed and speed > 0:
        speed_str = f" • ~{format_bytes(speed)}/с"

    return f"⏳ **Завантаження:** [{bar}] {percent:.0f}%\n📦 `{downloaded_str} / {total_str}`{speed_str}"


class ProgressThrottler:
    """
    Клас для обмеження частоти оновлення повідомлень у Telegram,
    щоб уникнути помилки 429 Too Many Requests (Flood Control).
    """
    def __init__(self, interval_seconds: float = 2.5):
        self.interval = interval_seconds
        self.last_update_time = 0.0
        self.last_text = ""

    def should_update(self, new_text: str, force: bool = False) -> bool:
        now = time.time()
        if force or (now - self.last_update_time >= self.interval and new_text != self.last_text):
            self.last_update_time = now
            self.last_text = new_text
            return True
        return False
