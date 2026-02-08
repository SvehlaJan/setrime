from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CommandHandler as TGCommandHandler,
    MessageHandler,
    PollAnswerHandler,
    filters,
)

from bot.config import AppConfig, setup_logging
from bot.handlers.commands import CommandHandler
from bot.handlers.expense import ExpenseHandler
from bot.services.categories import CategoryCache
from bot.services.llm_parser import LLMParser
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point: configure and start the Telegram bot."""
    # Load configuration
    config = AppConfig()
    setup_logging(config.log_level)

    if config.dry_run:
        logger.info("Starting Expense Bot in DRY RUN mode (no writes to Google Sheets)...")
    else:
        logger.info("Starting Expense Bot...")

    # Initialize services
    sheets = SheetsService(
        credentials_file=config.google_credentials_file,
        sheet_id=config.google_sheet_id,
    )

    llm = LLMParser(
        api_key=config.gemini_api_key,
        default_currency=config.default_currency,
    )

    category_cache = CategoryCache(sheets)
    # Pre-load categories
    try:
        cats = category_cache.refresh()
        logger.info("Loaded %d categories: %s", len(cats), ", ".join(cats))
    except Exception as exc:
        logger.warning("Could not pre-load categories: %s", exc)

    # Initialize handlers
    cmd_handler = CommandHandler(
        sheets=sheets,
        category_cache=category_cache,
        allowed_user_ids=config.allowed_user_ids,
    )

    expense_handler = ExpenseHandler(
        sheets=sheets,
        llm=llm,
        category_cache=category_cache,
        allowed_user_ids=config.allowed_user_ids,
        default_currency=config.default_currency,
        dry_run=config.dry_run,
    )

    # Build the Telegram application
    app = Application.builder().token(config.telegram_bot_token).build()

    # Register command handlers
    app.add_handler(TGCommandHandler("start", cmd_handler.start))
    app.add_handler(TGCommandHandler("help", cmd_handler.help))
    app.add_handler(TGCommandHandler("categories", cmd_handler.categories))
    app.add_handler(TGCommandHandler("summary", cmd_handler.summary))
    app.add_handler(TGCommandHandler("last", cmd_handler.last))
    app.add_handler(TGCommandHandler("undo", cmd_handler.undo))

    # Register expense handlers (text + image)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            expense_handler.handle_text,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            expense_handler.handle_image,
        )
    )

    # Register poll answer handler (for category selection)
    app.add_handler(PollAnswerHandler(expense_handler.handle_poll_answer))

    # Start polling
    logger.info(
        "Bot is running (long polling). Authorized users: %s",
        config.allowed_user_ids,
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
