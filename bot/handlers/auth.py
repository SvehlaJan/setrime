from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def check_authorized(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    allowed_user_ids: list[int],
) -> bool:
    """Check if the user is authorized. Sends a rejection message if not.

    Returns True if authorized, False otherwise.
    """
    user = update.effective_user
    if user is not None and user.id in allowed_user_ids:
        return True

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
    return False
