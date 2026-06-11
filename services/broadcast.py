import asyncio
import json
import logging
from telegram import Bot, Message
from telegram.error import TelegramError

from services.content import format_admin_text

logger = logging.getLogger(__name__)

SEND_DELAY = 0.02


def extract_broadcast_payload(message: Message) -> dict:
    """Сериализует сообщение админа для рассылки с последующим форматированием."""
    if message.text is not None:
        return {"type": "text", "text": message.text}

    caption = message.caption or ""
    if message.photo:
        return {"type": "photo", "text": caption, "file_id": message.photo[-1].file_id}
    if message.video:
        return {"type": "video", "text": caption, "file_id": message.video.file_id}
    if message.audio:
        return {"type": "audio", "text": caption, "file_id": message.audio.file_id}
    if message.voice:
        return {"type": "voice", "text": caption, "file_id": message.voice.file_id}
    if message.document:
        return {"type": "document", "text": caption, "file_id": message.document.file_id}

    raise ValueError("Неподдерживаемый тип сообщения для рассылки")


def payload_from_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Не удалось разобрать payload рассылки: %s", raw[:100])
        return None


async def _send_to_user(
    bot: Bot,
    user_id: int,
    payload: dict | None,
    source_chat_id: int | None,
    source_message_id: int | None,
) -> None:
    """Отправка с fallback: payload → copy_message."""
    if payload is not None:
        try:
            await send_broadcast_payload(bot, user_id, payload)
            return
        except TelegramError as exc:
            logger.warning(
                "Payload-рассылка не удалась для %s (%s), пробуем copy_message",
                user_id,
                exc,
            )
    if source_chat_id is not None and source_message_id is not None:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=source_chat_id,
            message_id=source_message_id,
        )
        return
    raise TelegramError("Нет способа доставить рассылку этому пользователю")


async def send_broadcast_payload(bot: Bot, user_id: int, payload: dict) -> None:
    """Отправляет одному пользователю контент рассылки с форматированием маркеров."""
    raw_text = payload.get("text") or ""
    plain, entities = format_admin_text(raw_text) if raw_text else ("", [])

    content_type = payload["type"]
    file_id = payload.get("file_id")

    if content_type == "text":
        await bot.send_message(
            chat_id=user_id,
            text=plain,
            entities=entities or None,
        )
        return

    caption_kwargs = {}
    if plain:
        caption_kwargs["caption"] = plain
        if entities:
            caption_kwargs["caption_entities"] = entities

    if content_type == "photo":
        await bot.send_photo(chat_id=user_id, photo=file_id, **caption_kwargs)
    elif content_type == "video":
        await bot.send_video(chat_id=user_id, video=file_id, **caption_kwargs)
    elif content_type == "audio":
        await bot.send_audio(chat_id=user_id, audio=file_id, **caption_kwargs)
    elif content_type == "voice":
        await bot.send_voice(chat_id=user_id, voice=file_id, **caption_kwargs)
    elif content_type == "document":
        await bot.send_document(chat_id=user_id, document=file_id, **caption_kwargs)
    else:
        raise ValueError(f"Неизвестный тип рассылки: {content_type}")


async def broadcast_message(
    bot: Bot,
    source_message: Message | None = None,
    *,
    payload: dict | None = None,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
    user_ids: list[int] | None = None,
) -> tuple[int, int, list[int]]:
    """
    Рассылает сообщение подписчикам.
    Если передан payload — применяет format_admin_text к тексту/подписи.
    При ошибке — fallback через copy_message.
    """
    if source_message is not None:
        source_chat_id = source_message.chat_id
        source_message_id = source_message.message_id
        if payload is None:
            try:
                payload = extract_broadcast_payload(source_message)
            except ValueError:
                payload = None

    if payload is None and (source_chat_id is None or source_message_id is None):
        raise ValueError("Нужен payload или source_message / chat_id+message_id")

    if user_ids is None:
        from services.db import get_subscribed_users
        user_ids = get_subscribed_users()

    if not user_ids:
        logger.warning("Нет пользователей для рассылки.")
        return 0, 0, []

    logger.info(
        "Начинаю рассылку %s пользователям: %s (тип: %s)",
        len(user_ids),
        user_ids,
        payload.get("type") if payload else "copy",
    )

    success = 0
    failed = 0
    delivered_to: list[int] = []

    for user_id in user_ids:
        try:
            await _send_to_user(
                bot,
                user_id,
                payload,
                source_chat_id,
                source_message_id,
            )
            success += 1
            delivered_to.append(user_id)
            if success % 10 == 0:
                logger.info(f"Отправлено {success}/{len(user_ids)}")
        except TelegramError as e:
            logger.warning(f"Не удалось отправить {user_id}: {e}")
            failed += 1
        await asyncio.sleep(SEND_DELAY)

    logger.info(f"Рассылка завершена: {success} успешно, {failed} ошибок.")
    return success, failed, delivered_to
