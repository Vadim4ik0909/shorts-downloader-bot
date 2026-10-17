import asyncio
import logging
from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import FSInputFile, InputMediaPhoto, Message

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
    """Періодично надсилає статус 'завантаження відео/фото' під час очікування."""
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
        photos = [i for i in cached.items if i.media_type == "photo"]
        videos = [i for i in cached.items if i.media_type == "video"]
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

        if photos:
            if len(photos) == 1:
                caption = (photos[0].caption or cached.title or "")[:1000]
                await message.reply_photo(photo=photos[0].file_id, caption=caption if caption else None)
            else:
                chunk_size = 10
                for chunk_idx in range(0, len(photos), chunk_size):
                    chunk = photos[chunk_idx:chunk_idx + chunk_size]
                    media_group = [
                        InputMediaPhoto(
                            media=p.file_id,
                            caption=((p.caption or cached.title or "")[:1000]) if (chunk_idx == 0 and idx == 0) else None
                        )
                        for idx, p in enumerate(chunk)
                    ]
                    await message.reply_media_group(media=media_group)

        for a in audios:
            await message.reply_audio(audio=a.file_id, caption=(a.caption or "Музична доріжка")[:1000])

        return

    # 2. НОВЕ ЗАВАНТАЖЕННЯ (З ЧЕРГОЮ ТА ПРОГРЕС-БАРОМ)
    status_msg = await message.reply("⏳ Підготовка до завантаження...")

    stop_action_event = asyncio.Event()
    action_task = asyncio.create_task(
        _keep_chat_action_alive(bot, message.chat.id, ChatAction.UPLOAD_VIDEO, stop_action_event)
    )

    result = None
    try:
        # Функція сповіщення про позицію в черзі
        async def on_queue_waiting(position: int):
            try:
                await status_msg.edit_text(
                    f"⏳ **Ви в черзі на завантаження** (позиція: {position})\n"
                    f"Зачекайте, поки звільниться слот сервера..."
                )
            except Exception:
                pass

        # Вхід у чергу завантажень
        async with download_queue_slot(on_waiting=on_queue_waiting):
            throttler = ProgressThrottler(interval_seconds=2.0)

            # Оновлення прогрес-бару в реальному часі
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
                "• Відео є приватним або видаленим\n"
                "• Платформа тимчасово обмежила доступ"
            )
            return

        photos = [item for item in result.items if item.media_type == "photo"]
        videos = [item for item in result.items if item.media_type == "video"]
        audios = [item for item in result.items if item.media_type == "audio"]

        cached_items_to_save = []

        # Відправка відео
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

        # Відправка фото
        if photos:
            if len(photos) == 1:
                photo_file = FSInputFile(photos[0].file_path)
                caption = (photos[0].caption or result.title or "")[:1000]
                sent_msg = await message.reply_photo(photo=photo_file, caption=caption if caption else None)
                if sent_msg.photo:
                    cached_items_to_save.append(
                        CachedItem(
                            media_type="photo",
                            file_id=sent_msg.photo[-1].file_id,
                            caption=caption
                        )
                    )
            else:
                chunk_size = 10
                for chunk_idx in range(0, len(photos), chunk_size):
                    chunk = photos[chunk_idx:chunk_idx + chunk_size]
                    media_group = []

                    for idx, photo_item in enumerate(chunk):
                        if photo_item.file_path.exists():
                            caption = ((photo_item.caption or result.title or "")[:1000]) if (chunk_idx == 0 and idx == 0) else None
                            media_group.append(
                                InputMediaPhoto(
                                    media=FSInputFile(photo_item.file_path),
                                    caption=caption
                                )
                            )

                    if media_group:
                        sent_msgs = await message.reply_media_group(media=media_group)
                        for s_msg in sent_msgs:
                            if s_msg.photo:
                                cached_items_to_save.append(
                                    CachedItem(
                                        media_type="photo",
                                        file_id=s_msg.photo[-1].file_id
                                    )
                                )

        # Відправка аудіо
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

        # Зберігаємо file_id у SQLite кеш для миттєвої відправки наступного разу!
        if cached_items_to_save:
            save_cached_media(url, result.title, cached_items_to_save)

        # Очищення повідомлення статусу
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
