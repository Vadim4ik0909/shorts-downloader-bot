from handlers.commands import router as commands_router
from handlers.inline import router as inline_router
from handlers.media import router as media_router

__all__ = ["commands_router", "media_router", "inline_router"]
