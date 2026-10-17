import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN
from handlers import commands_router, inline_router, media_router
from services import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


async def set_main_menu(bot: Bot):
    """Встановлює список команд у меню Telegram."""
    main_menu_commands = [
        BotCommand(command="/start", description="Запустити або перезапустити бота"),
        BotCommand(command="/help", description="Довідка та інструкція"),
    ]
    await bot.set_my_commands(main_menu_commands)


async def main():
    if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error(
            "ПОМИЛКА: Не вказано токен бота у файлі .env!\n"
            "1. Створіть файл .env у корені проєкту (скопіювавши .env.example).\n"
            "2. Отримайте токен у Telegram через @BotFather.\n"
            "3. Впишіть BOT_TOKEN=ваш_токен у файл .env."
        )
        sys.exit(1)

    # Ініціалізація бази даних SQLite для кешування
    init_db()
    logger.info("Базу даних SQLite для кешування успішно ініціалізовано.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Реєстрація роутерів
    dp.include_router(commands_router)
    dp.include_router(inline_router)
    dp.include_router(media_router)

    await set_main_menu(bot)

    logger.info("Бот успішно запущений і готовий до роботи!")
    # Видаляємо всі повідомлення, надіслані боту, поки він був офлайн
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")
