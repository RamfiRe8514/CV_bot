import asyncio
import logging
from telegram import Bot, Message
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# Задержка между отправками (сек) - минимальная для избежания flood
SEND_DELAY = 0.02


async def broadcast_message(
    bot: Bot,
    source_message: Message | None = None,
    *,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
    user_ids: list[int] | None = None,
) -> tuple[int, int]:
    """
    Пересылает сообщение указанным пользователям.
    Если user_ids не передан — использует только подписанных пользователей.
    Возвращает (успешно, ошибок).
    """
    if source_message is not None:
        source_chat_id = source_message.chat_id
        source_message_id = source_message.message_id

    if source_chat_id is None or source_message_id is None:
        raise ValueError("Нужно передать source_message или source_chat_id/source_message_id")

    if user_ids is None:
        from services.db import get_subscribed_users
        user_ids = get_subscribed_users()

    if not user_ids:
        logger.warning("Нет пользователей для рассылки.")
        return 0, 0

    logger.info(f"Начинаю рассылку {len(user_ids)} пользователям...")

    success = 0
    failed = 0

    for user_id in user_ids:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            success += 1
            if success % 10 == 0:
                logger.info(f"Отправлено {success}/{len(user_ids)}")
        except TelegramError as e:
            logger.warning(f"Не удалось отправить {user_id}: {e}")
            failed += 1
        await asyncio.sleep(SEND_DELAY)

    logger.info(f"Рассылка завершена: {success} успешно, {failed} ошибок.")
    return success, failed
