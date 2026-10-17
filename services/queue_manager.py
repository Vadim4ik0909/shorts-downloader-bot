import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Максимальна кількість одночасних важких завантажень
MAX_CONCURRENT_DOWNLOADS = 3
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
_waiting_count = 0


@asynccontextmanager
async def download_queue_slot(on_waiting: Optional[Callable[[int], None]] = None):
    """
    Асинхронний контекстний менеджер для черги завдань.
    Якщо всі слоти зайняті, повідомляє користувача про його позицію в черзі.
    """
    global _waiting_count

    # Перевіряємо, чи є вільний слот одразу
    if _semaphore.locked():
        _waiting_count += 1
        pos = _waiting_count
        if on_waiting:
            try:
                res = on_waiting(pos)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.warning(f"Помилка виклику on_waiting: {e}")

        try:
            await _semaphore.acquire()
        finally:
            _waiting_count = max(0, _waiting_count - 1)
    else:
        await _semaphore.acquire()

    try:
        yield
    finally:
        _semaphore.release()
