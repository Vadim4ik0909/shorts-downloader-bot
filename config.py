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

# Опціональний шлях до cookies
COOKIES_FILE = os.getenv("COOKIES_FILE", "").strip()
if COOKIES_FILE and not os.path.isabs(COOKIES_FILE):
    COOKIES_FILE = str(BASE_DIR / COOKIES_FILE)
if not COOKIES_FILE or not os.path.exists(COOKIES_FILE):
    COOKIES_FILE = None
