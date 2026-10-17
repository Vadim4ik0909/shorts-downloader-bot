import logging
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedVideo,
    InputTextMessageContent,
)

from services import extract_first_url, get_cached_media

logger = logging.getLogger(__name__)

router = Router()


@router.inline_query()
async def inline_query_handler(query: InlineQuery):
    text = query.query.strip()
    url = extract_first_url(text)

    # 1. Якщо користувач ще не ввів посилання — показуємо підказку
    if not url:
        results = [
            InlineQueryResultArticle(
                id="hint",
                title="🔍 Вставте посилання на Shorts, TikTok або Instagram",
                description="Наприклад: @shorts_METIOS_bot https://youtube.com/shorts/...",
                input_message_content=InputTextMessageContent(
                    message_text="Надішліть посилання боту @shorts_METIOS_bot для завантаження відео або фото!"
                )
            )
        ]
        await query.answer(results=results, cache_time=5, is_personal=True)
        return

    # 2. Якщо відео вже є в кеші — пропонуємо відправити його миттєво в будь-який чат!
    cached = get_cached_media(url)
    if cached and cached.items:
        results = []
        for idx, item in enumerate(cached.items):
            if item.media_type == "video":
                results.append(
                    InlineQueryResultCachedVideo(
                        id=f"v_{idx}_{item.file_id[:10]}",
                        video_file_id=item.file_id,
                        title=f"🎬 {cached.title[:50]}",
                        caption=(item.caption or cached.title or "")[:1000]
                    )
                )
            elif item.media_type == "photo":
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=f"p_{idx}_{item.file_id[:10]}",
                        photo_file_id=item.file_id,
                        title=f"📸 {cached.title[:50]}",
                        caption=(item.caption or cached.title or "")[:1000]
                    )
                )

        if results:
            await query.answer(results=results, cache_time=300, is_personal=False)
            return

    # 3. Якщо відео ще немає в кеші — пропонуємо відкрити бота для першого завантаження
    results = [
        InlineQueryResultArticle(
            id="download_prompt",
            title="📥 Медіа ще не завантажено",
            description="Натисніть кнопку нижче, щоб відкрити бота і завантажити це відео",
            input_message_content=InputTextMessageContent(
                message_text=f"Завантажити медіа за посиланням: {url}\nчерез @shorts_METIOS_bot"
            )
        )
    ]
    await query.answer(
        results=results,
        cache_time=5,
        is_personal=True,
        switch_pm_text="⚡️ Відкрити бота для завантаження",
        switch_pm_parameter="start"
    )
