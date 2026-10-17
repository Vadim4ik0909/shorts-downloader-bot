import asyncio
import logging
from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import (
    FSInputFile,
    InputMediaDocument,
    InputMediaPhoto,
    Message,
)

from services import (
    CachedItem,
    ProgressThrottler,
    cleanup_result,
    download_media,
    download_queue_slot,
    extract_first_url,
    get_cached_media,
    render_progress_bar,
    save_cached_media,
)

logger = logging.getLogger(__name__)

router = Router()


async def _keep_chat_action_alive(bot: Bot, chat_id: int, action: ChatAction, stop_event: asyncio.Event):
    """Періодично надсилає статус 'завантаження відео/документа' під час очікування."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=action)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass


@router.message(F.text)
async def handle_link(message: Message, bot: Bot):
    text = message.text or ""
    url = extract_first_url(text)

    if not url:
        return

    # 1. ШВИДКЕ ВІДПРАВЛЕННЯ З КЕШУ (МИТТЄВО БЕЗ СКАЧУВАННЯ)
    cached = get_cached_media(url)
    if cached and cached.items:
        logger.info(f"Миттєва відправка з кешу для {url}")
        videos = [i for i in cached.items if i.media_type == "video"]
        documents = [i for i in cached.items if i.media_type in ("document", "photo")]
        audios = [i for i in cached.items if i.media_type == "audio"]

        for v in videos:
            caption = (v.caption or cached.title or "")[:1000]
            await message.reply_video(
                video=v.file_id,
                caption=caption if caption else None,
                duration=v.duration,
                width=v.width,
                height=v.height,
                supports_streaming=True
            )

        if documents:
            if len(documents) == 1:
                caption = (documents[0].caption or cached.title or "")[:1000]
                await message.reply_document(document=documents[0].file_id, caption=caption if caption else None)
            else:
                chunk_size = 10
                for chunk_idx in range(0, len(documents), chunk_size):
                    chunk = documents[chunk_idx:chunk_idx + chunk_size]
                    media_group = [
                        InputMediaDocument(
                            media=doc.file_id,
                            caption=((doc.caption or cached.title or "")[:1000]) if (chunk_idx == 0 and idx == 0) else None
                        )
                        for idx, doc in enumerate(chunk)
                    ]
                    await message.reply_media_group(media=media_group)

        for a in audios:
            await message.reply_audio(audio=a.file_id, caption=(a.caption or "Музична доріжка")[:1000])

        return

    # 2. НОВЕ ЗАВАНТАЖЕННЯ (З ЧЕРГОЮ ТА ПРОГРЕС-БАРОМ)
    status_msg = await message.reply("⏳ Підготовка до завантаження...")

    stop_action_event = asyncio.Event()
    action_task = asyncio.create_task(
        _keep_chat_action_alive(bot, message.chat.id, ChatAction.UPLOAD_DOCUMENT, stop_action_event)
    )

    result = None
    try:
        async def on_queue_waiting(position: int):
            try:
                await status_msg.edit_text(
                    f"⏳ **Ви в черзі на завантаження** (позиція: {position})\n"
                    f"Зачекайте, поки звільниться слот сервера..."
                )
            except Exception:
                pass

        async with download_queue_slot(on_waiting=on_queue_waiting):
            throttler = ProgressThrottler(interval_seconds=2.0)

            async def on_progress(percent: float, downloaded: float, total: float, speed: float):
                progress_text = render_progress_bar(percent, downloaded, total, speed)
                if throttler.should_update(progress_text):
                    try:
                        await status_msg.edit_text(progress_text, parse_mode="Markdown")
                    except Exception:
                        pass

            result = await download_media(url, on_progress=on_progress)

        if not result or not result.items:
            await status_msg.edit_text(
                "❌ **Не вдалося завантажити контент за цим посиланням.**\n\n"
                "Можливі причини:\n"
                "• Відео/пост є приватним або видаленим\n"
                "• Платформа тимчасово обмежила доступ"
            )
            return

        videos = [item for item in result.items if item.media_type == "video"]
        # Фотографії та документи надсилаємо як нестиснені оригінальні файли для максимальної якості
        documents = [item for item in result.items if item.media_type in ("document", "photo")]
        audios = [item for item in result.items if item.media_type == "audio"]

        cached_items_to_save = []

        # 1. Відправка відео
        for video_item in videos:
            if video_item.file_path.exists():
                caption = (video_item.caption or result.title or "")[:1000]
                video_file = FSInputFile(video_item.file_path)
                sent_msg = await message.reply_video(
                    video=video_file,
                    caption=caption if caption else None,
                    duration=video_item.duration,
                    width=video_item.width,
                    height=video_item.height,
                    supports_streaming=True
                )
                if sent_msg.video:
                    cached_items_to_save.append(
                        CachedItem(
                            media_type="video",
                            file_id=sent_msg.video.file_id,
                            caption=caption,
                            duration=video_item.duration,
                            width=video_item.width,
                            height=video_item.height
                        )
                    )

        # 2. Відправка фотографій у вигляді файлів/документів (100% оригінальна якість без стиснення Telegram)
        if documents:
            if len(documents) == 1:
                doc_file = FSInputFile(documents[0].file_path)
                caption = (documents[0].caption or result.title or "")[:1000]
                sent_msg = await message.reply_document(document=doc_file, caption=caption if caption else None)
                if sent_msg.document:
                    cached_items_to_save.append(
                        CachedItem(
                            media_type="document",
                            file_id=sent_msg.document.file_id,
                            caption=caption
                        )
                    )
            else:
                chunk_size = 10
                for chunk_idx in range(0, len(documents), chunk_size):
                    chunk = documents[chunk_idx:chunk_idx + chunk_size]
                    media_group = []

                    for idx, doc_item in enumerate(chunk):
                        if doc_item.file_path.exists():
                            caption = ((doc_item.caption or result.title or "")[:1000]) if (chunk_idx == 0 and idx == 0) else None
                            media_group.append(
                                InputMediaDocument(
                                    media=FSInputFile(doc_item.file_path),
                                    caption=caption
                                )
                            )

                    if media_group:
                        sent_msgs = await message.reply_media_group(media=media_group)
                        for s_msg in sent_msgs:
                            if s_msg.document:
                                cached_items_to_save.append(
                                    CachedItem(
                                        media_type="document",
                                        file_id=s_msg.document.file_id
                                    )
                                )

        # 3. Відправка аудіо
        for audio_item in audios:
            if audio_item.file_path.exists():
                caption = (audio_item.caption or "Музична доріжка")[:1000]
                sent_msg = await message.reply_audio(
                    audio=FSInputFile(audio_item.file_path),
                    caption=caption
                )
                if sent_msg.audio:
                    cached_items_to_save.append(
                        CachedItem(
                            media_type="audio",
                            file_id=sent_msg.audio.file_id,
                            caption=caption
                        )
                    )

        # Збереження в SQLite кеш
        if cached_items_to_save:
            save_cached_media(url, result.title, cached_items_to_save)

        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Помилка при обробці посилання {url}: {e}", exc_info=True)
        try:
            await status_msg.edit_text("❌ Сталася внутрішня помилка під час обробки медіа.")
        except Exception:
            pass
    finally:
        stop_action_event.set()
        await action_task
        cleanup_result(result)
