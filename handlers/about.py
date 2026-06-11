import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from config import get_about_text
from services.content import load_practicums, PRAC_IMAGE_PATH, format_admin_text
from keyboards.main_menu import get_main_menu_keyboard

logger = logging.getLogger(__name__)


async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_about_text()

    if not text:
        text = "Информация о нас пока не добавлена."

    plain_text, entities = format_admin_text(text)

    await update.message.reply_text(
        plain_text,
        entities=entities,
        reply_markup=get_main_menu_keyboard(),
    )


async def practicum_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает практикумы."""
    practicum_text = load_practicums()

    if practicum_text:
        plain_text, entities = format_admin_text(practicum_text)

        if os.path.exists(PRAC_IMAGE_PATH):
            with open(PRAC_IMAGE_PATH, "rb") as img:
                await update.message.reply_photo(
                    photo=img,
                    caption=plain_text,
                    caption_entities=entities,
                )
        else:
            await update.message.reply_text(plain_text, entities=entities)
    else:
        await update.message.reply_text(
            "Практикумы пока не добавлены. Следите за обновлениями!"
        )
