from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def authorized(allowed_user_ids: list[int]) -> Callable[[F], F]:
    """Decorator that restricts handler access to whitelisted user IDs."""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(
            update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any
        ) -> Any:
            user = update.effective_user
            if user is None or user.id not in allowed_user_ids:
                user_id = user.id if user else "unknown"
                username = user.username if user else "unknown"
                logger.warning(
                    "Unauthorized access attempt: user_id=%s username=%s",
                    user_id,
                    username,
                )
                if update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Sorry, you are not authorized to use this bot.",
                    )
                return None
            return await func(update, context, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
