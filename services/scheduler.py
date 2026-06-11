import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Bot
from telegram.error import TelegramError

from services.broadcast import broadcast_message
from services.db import (
    claim_due_scheduled_broadcast,
    mark_scheduled_broadcast_failed,
    mark_scheduled_broadcast_sent,
    save_broadcast,
)

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
CHECK_INTERVAL_SEC = 30


def parse_broadcast_schedule(text: str) -> datetime | str | None:
    """
    Разбирает время рассылки.
    Возвращает 'now', datetime (MSK) или None при ошибке.
    """
    raw = text.strip()
    lowered = raw.lower()

    if lowered in ("сейчас", "now", "немедленно"):
        return "now"

    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=MSK)
        except ValueError:
            pass

    try:
        parsed = datetime.strptime(raw, "%H:%M").time()
        now = datetime.now(MSK)
        scheduled = now.replace(
            hour=parsed.hour,
            minute=parsed.minute,
            second=0,
            microsecond=0,
        )
        if scheduled <= now:
            scheduled += timedelta(days=1)
        return scheduled
    except ValueError:
        return None


def format_schedule_msk(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MSK)
    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M МСК")


async def execute_scheduled_broadcast(bot: Bot, item: dict) -> None:
    """Отправляет одну отложенную рассылку."""
    broadcast_id = item["id"]
    try:
        success, failed = await broadcast_message(
            bot,
            source_chat_id=item["admin_chat_id"],
            source_message_id=item["message_id"],
        )
        mark_scheduled_broadcast_sent(broadcast_id, success, failed)
        save_broadcast(message_text=f"[scheduled #{broadcast_id}]")
        logger.info(
            "Отложенная рассылка #%s выполнена: %s успешно, %s ошибок",
            broadcast_id,
            success,
            failed,
        )
        try:
            await bot.send_message(
                chat_id=item["created_by"],
                text=(
                    f"Отложенная рассылка #{broadcast_id} отправлена.\n\n"
                    f"Доставлено: {success}\nОшибок: {failed}"
                ),
            )
        except TelegramError:
            pass
    except Exception as exc:
        mark_scheduled_broadcast_failed(broadcast_id, str(exc))
        logger.exception("Ошибка отложенной рассылки #%s: %s", broadcast_id, exc)
        try:
            await bot.send_message(
                chat_id=item["created_by"],
                text=f"Отложенная рассылка #{broadcast_id} не удалась: {exc}",
            )
        except TelegramError:
            pass


async def broadcast_scheduler_loop(bot: Bot) -> None:
    """Периодически проверяет и отправляет отложенные рассылки."""
    logger.info("Планировщик рассылок запущен")
    while True:
        try:
            while True:
                item = claim_due_scheduled_broadcast()
                if not item:
                    break
                await execute_scheduled_broadcast(bot, item)
        except Exception:
            logger.exception("Ошибка в планировщике рассылок")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
