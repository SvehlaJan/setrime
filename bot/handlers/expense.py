from __future__ import annotations

import io
import logging
import traceback
from datetime import date
from typing import Any

from PIL import Image
from telegram import Poll, Update
from telegram.ext import ContextTypes

from bot.handlers.auth import authorized
from bot.models import Currency, Expense, ParsedExpense, PendingExpense
from bot.services.categories import CategoryCache
from bot.services.llm_parser import LLMParser
from bot.services.sheets import SheetsService

logger = logging.getLogger(__name__)

# Maximum options in a Telegram poll
MAX_POLL_OPTIONS = 10


class ExpenseHandler:
    """Handles text and image messages for expense tracking, including
    the follow-up question flow with Telegram polls."""

    def __init__(
        self,
        sheets: SheetsService,
        llm: LLMParser,
        category_cache: CategoryCache,
        allowed_user_ids: list[int],
        default_currency: Currency,
    ) -> None:
        self._sheets = sheets
        self._llm = llm
        self._categories = category_cache
        self._allowed_user_ids = allowed_user_ids
        self._default_currency = default_currency
        # poll_id -> PendingExpense (for mapping poll answers back)
        self._pending_polls: dict[str, PendingExpense] = {}
        # user_id -> PendingExpense (for text-based follow-ups)
        self._pending_text: dict[int, PendingExpense] = {}

    def _cleanup_expired(self) -> None:
        """Remove expired pending expenses."""
        expired_polls = [
            pid for pid, pe in self._pending_polls.items() if pe.is_expired()
        ]
        for pid in expired_polls:
            del self._pending_polls[pid]

        expired_text = [
            uid for uid, pe in self._pending_text.items() if pe.is_expired()
        ]
        for uid in expired_text:
            del self._pending_text[uid]

    async def handle_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle a text message that might be an expense."""
        if not update.message or not update.message.text or not update.effective_user:
            return

        user = update.effective_user
        if user.id not in self._allowed_user_ids:
            return

        text = update.message.text.strip()
        if text.startswith("/"):
            return  # ignore commands

        self._cleanup_expired()

        # Check if this is a reply to a follow-up question
        if user.id in self._pending_text:
            await self._handle_text_followup(update, context, text)
            return

        # Parse the expense from text
        chat_id = update.effective_chat.id if update.effective_chat else 0
        await self._parse_and_process(
            update, context, user.id, chat_id, text=text
        )

    async def handle_image(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle a photo message (banking screenshot)."""
        if not update.message or not update.message.photo or not update.effective_user:
            return

        user = update.effective_user
        if user.id not in self._allowed_user_ids:
            return

        self._cleanup_expired()
        chat_id = update.effective_chat.id if update.effective_chat else 0

        # Download the highest-resolution photo
        photo = update.message.photo[-1]
        try:
            file = await context.bot.get_file(photo.file_id)
            bio = io.BytesIO()
            await file.download_to_memory(bio)
            bio.seek(0)
            image = Image.open(bio)
        except Exception as exc:
            error_msg = f"Failed to download image: {exc}\n{traceback.format_exc()}"
            logger.error(error_msg)
            await self._send_error(update, "Failed to download image", str(exc))
            return

        caption = update.message.caption
        await self._parse_and_process(
            update, context, user.id, chat_id, image=image, caption=caption
        )

    async def handle_poll_answer(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle a poll answer (user selected a category)."""
        if not update.poll_answer:
            return

        poll_answer = update.poll_answer
        poll_id = poll_answer.poll_id
        user_id = poll_answer.user.id if poll_answer.user else None

        if poll_id not in self._pending_polls:
            logger.debug("Received answer for unknown poll %s", poll_id)
            return

        pending = self._pending_polls.pop(poll_id)

        if not poll_answer.option_ids:
            logger.warning("Poll answer with no selection for poll %s", poll_id)
            return

        selected_index = poll_answer.option_ids[0]
        categories = self._categories.categories

        if selected_index < 0 or selected_index >= len(categories):
            logger.error(
                "Invalid poll option index %d (have %d categories)",
                selected_index,
                len(categories),
            )
            return

        selected_category = categories[selected_index]
        pending.parsed.category = selected_category

        logger.info(
            "User %s selected category '%s' via poll",
            user_id,
            selected_category,
        )

        # Try to close the poll
        if pending.message_id:
            try:
                await context.bot.stop_poll(
                    chat_id=pending.chat_id,
                    message_id=pending.message_id,
                )
            except Exception:
                pass  # poll may already be closed or message deleted

        # Now try to finalize the expense
        await self._finalize_expense(pending, context)

    async def _parse_and_process(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        chat_id: int,
        text: str | None = None,
        image: Image.Image | None = None,
        caption: str | None = None,
    ) -> None:
        """Parse an expense from text or image, then process it."""
        categories = self._categories.categories

        try:
            if image is not None:
                parsed = await self._llm.parse_image(
                    image, categories, caption=caption
                )
            elif text is not None:
                parsed = await self._llm.parse_text(text, categories)
            else:
                return
        except Exception as exc:
            error_msg = f"Failed to parse expense: {exc}"
            logger.error("%s\n%s", error_msg, traceback.format_exc())
            await self._send_error(
                update,
                "Failed to parse expense",
                str(exc),
                "Please try again or rephrase your message.",
            )
            return

        logger.info("Parsed expense: %s", parsed.model_dump_json())

        # Fill in defaults
        if parsed.date is None:
            parsed.date = date.today()
        if parsed.currency is None:
            parsed.currency = self._default_currency

        pending = PendingExpense(
            user_id=user_id,
            chat_id=chat_id,
            parsed=parsed,
        )

        # Check what's missing and ask follow-up questions
        await self._check_and_ask(update, context, pending)

    async def _check_and_ask(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        pending: PendingExpense,
    ) -> None:
        """Check for missing fields and ask follow-up questions."""
        parsed = pending.parsed

        if parsed.amount is None:
            # Ask for amount
            self._pending_text[pending.user_id] = pending
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "I couldn't determine the amount.\n"
                        "Please reply with the amount (e.g., `250` or `49.90`)."
                    ),
                    parse_mode="Markdown",
                )
            return

        if parsed.description is None:
            # Ask for description
            self._pending_text[pending.user_id] = pending
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="What was this expense for? (e.g., merchant name or description)",
                )
            return

        if parsed.category is None:
            # Send a category poll
            await self._send_category_poll(update, context, pending)
            return

        # All fields present — finalize
        await self._finalize_expense(pending, context)

    async def _handle_text_followup(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
    ) -> None:
        """Handle a text reply to a follow-up question."""
        user_id = update.effective_user.id if update.effective_user else 0
        pending = self._pending_text.pop(user_id, None)
        if pending is None:
            return

        parsed = pending.parsed

        if parsed.amount is None:
            # Try to parse the amount
            try:
                amount = float(text.replace(",", ".").replace(" ", ""))
                if amount <= 0:
                    raise ValueError("Amount must be positive")
                parsed.amount = amount
            except ValueError:
                self._pending_text[user_id] = pending
                if update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Could not parse `{text}` as a number. Please try again.",
                        parse_mode="Markdown",
                    )
                return
        elif parsed.description is None:
            parsed.description = text.strip()

        # Check if more fields are still missing
        await self._check_and_ask(update, context, pending)

    async def _send_category_poll(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        pending: PendingExpense,
    ) -> None:
        """Send a Telegram poll for category selection."""
        categories = self._categories.categories

        if not categories:
            # No categories available — ask as text
            self._pending_text[pending.user_id] = pending
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="No categories loaded. Please type the category name:",
                )
            return

        if len(categories) > MAX_POLL_OPTIONS:
            # Telegram polls max out at 10 options — truncate and note
            poll_options = categories[:MAX_POLL_OPTIONS]
            logger.warning(
                "More than %d categories (%d), showing first %d in poll",
                MAX_POLL_OPTIONS,
                len(categories),
                MAX_POLL_OPTIONS,
            )
        else:
            poll_options = categories

        # Build the question with expense context
        desc = pending.parsed.description or "expense"
        amount_str = (
            f"{pending.parsed.amount:.2f} {pending.parsed.currency}"
            if pending.parsed.amount and pending.parsed.currency
            else "unknown amount"
        )
        question = f"Category for: {desc} ({amount_str})?"
        # Telegram poll question max 300 chars
        if len(question) > 300:
            question = question[:297] + "..."

        chat_id = pending.chat_id
        try:
            message = await context.bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=poll_options,
                is_anonymous=False,
                allows_multiple_answers=False,
                type=Poll.REGULAR,
            )
            poll_id = message.poll.id if message.poll else None
            if poll_id:
                pending.poll_id = poll_id
                pending.message_id = message.message_id
                self._pending_polls[poll_id] = pending
                logger.info(
                    "Sent category poll %s for user %d with %d options",
                    poll_id,
                    pending.user_id,
                    len(poll_options),
                )
        except Exception as exc:
            logger.error("Failed to send category poll: %s", exc)
            # Fallback: ask as text
            self._pending_text[pending.user_id] = pending
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"Could not send poll ({exc}).\n"
                    "Please type the category name:"
                ),
            )

    async def _finalize_expense(
        self,
        pending: PendingExpense,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Validate and write the completed expense to Google Sheets."""
        parsed = pending.parsed

        # Build the validated expense
        try:
            expense = Expense(
                date=parsed.date or date.today(),
                amount=parsed.amount or 0.0,
                currency=parsed.currency or "CZK",
                category=parsed.category or "Unknown",
                description=parsed.description or "Unknown",
            )
        except Exception as exc:
            error_msg = f"Invalid expense data: {exc}"
            logger.error(error_msg)
            await context.bot.send_message(
                chat_id=pending.chat_id,
                text=f"❌ Error: {error_msg}",
            )
            return

        # Write to Google Sheets
        try:
            row_num = self._sheets.append_expense(expense)
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Failed to write expense: %s\n%s", exc, tb)
            suggestion = "Please try again."
            if "not found" in str(exc).lower():
                suggestion = (
                    f"Please create the tab '{expense.tab_name()}' "
                    "in the spreadsheet, then try again."
                )
            await context.bot.send_message(
                chat_id=pending.chat_id,
                text=(
                    f"❌ Error: Failed to write to Google Sheet.\n"
                    f"Details: {exc}\n"
                    f"Suggestion: {suggestion}"
                ),
            )
            return

        # Send confirmation
        confirmation = (
            f"✅ Expense recorded (row {row_num}):\n"
            f"  📅 Date: {expense.date.strftime('%d.%m.%Y')}\n"
            f"  📁 Category: {expense.category}\n"
            f"  📝 Description: {expense.description}\n"
            f"  💰 Amount: {expense.amount:.2f} {expense.currency}\n"
            f"  📄 Sheet: {expense.tab_name()}"
        )
        await context.bot.send_message(
            chat_id=pending.chat_id,
            text=confirmation,
        )

        logger.info(
            "Expense added: user=%d date=%s amount=%.2f currency=%s "
            "category=%s description='%s' sheet='%s' row=%d",
            pending.user_id,
            expense.date.isoformat(),
            expense.amount,
            expense.currency,
            expense.category,
            expense.description,
            expense.tab_name(),
            row_num,
        )

    @staticmethod
    async def _send_error(
        update: Update,
        title: str,
        details: str,
        suggestion: str = "Please try again.",
    ) -> None:
        """Send a formatted error message to the user."""
        if update.effective_chat:
            await update.effective_chat.send_message(
                text=(
                    f"❌ Error: {title}\n"
                    f"Details: {details}\n"
                    f"Suggestion: {suggestion}"
                ),
            )
