from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 **Привіт! Я бот для завантаження відео та фотографій.**\n\n"
        "Я можу скачувати:\n"
        "🎬 **YouTube Shorts**\n"
        "📱 **TikTok** (відео та фото-слайдшоу)\n"
        "📸 **Instagram** (Reels, пости та каруселі фото)\n"
        "🐦 **Twitter (X)**, Pinterest та багато інших!\n\n"
        "💡 **Як користуватися:**\n"
        "Просто надішли мені посилання на пост, відео або шортс — і я відправлю медіа прямо в цей чат!\n\n"
        "Якщо в TikTok або Instagram пост містить **фотографії**, я надішлю їх усі у вигляді фотоальбому."
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "ℹ️ **Довідка по використанню бота:**\n\n"
        "1. Скопіюйте посилання на відео або фото з будь-якого додатку чи сайту.\n"
        "2. Надішліть це посилання сюди.\n"
        "3. Зачекайте кілька секунд, поки бот завантажить і відправить контент.\n\n"
        "⚠️ **Обмеження:**\n"
        "• Telegram Bot API обмежує розмір надсилання файлів до 50 МБ (більшість шортсів та рілсів вкладаються в 10-30 МБ).\n"
        "• Приватні акаунти або відео з обмеженнями за віком можуть не завантажуватися без додаткових налаштувань."
    )
    await message.answer(text, parse_mode="Markdown")
