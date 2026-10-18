import os
from pathlib import Path
from dotenv import load_dotenv

# Завантаження змінних середовища з файлу .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Максимальний розмір файлу для завантаження в Telegram (за замовчуванням 50 МБ)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Опціональний шлях до cookies або передача cookies текстом через YOUTUBE_COOKIES
COOKIES_FILE = os.getenv("COOKIES_FILE", "").strip()
YOUTUBE_COOKIES_TEXT = os.getenv("YOUTUBE_COOKIES", "").strip()

def normalize_netscape_cookies(text: str) -> str:
    """Нормалізує текст cookies, перетворюючи пробіли на табуляції для стандарту Netscape."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            lines.append(line)
            continue
        parts = line.split()
        if len(parts) >= 7:
            # 7 колонок: domain, flag, path, secure, expiration, name, value
            domain, flag, path, secure, expiration, name = parts[:6]
            value = " ".join(parts[6:])
            lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}")
        else:
            lines.append(line)
    res = "\n".join(lines)
    if not res.startswith("# Netscape"):
        res = "# Netscape HTTP Cookie File\n" + res
    return res


if YOUTUBE_COOKIES_TEXT:
    raw_cookies = YOUTUBE_COOKIES_TEXT.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    clean_cookies = normalize_netscape_cookies(raw_cookies)
    cookies_path = BASE_DIR / "cookies.txt"
    try:
        cookies_path.write_text(clean_cookies, encoding="utf-8")
        COOKIES_FILE = str(cookies_path)
    except Exception:
        pass

if COOKIES_FILE and not os.path.isabs(COOKIES_FILE):
    COOKIES_FILE = str(BASE_DIR / COOKIES_FILE)

# Валідація cookies: якщо файл пошкоджений, відключаємо його, щоб не ламати запити
if COOKIES_FILE and os.path.exists(COOKIES_FILE):
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"cookiefile": COOKIES_FILE, "quiet": True}) as _:
            pass
    except Exception:
        COOKIES_FILE = None
else:
    COOKIES_FILE = None

# Опціональний проксі для обходу блокувань дата-центрів
PROXY = os.getenv("PROXY", "").strip() or None
