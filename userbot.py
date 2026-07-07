"""
Юзербот: работает от имени вашего личного Telegram-аккаунта.
Пишет одну из включённых фраз в комментарии под постами, автоматически
пересланными из канала в привязанную группу обсуждений — но ТОЛЬКО в тех
группах, которые вы явно подключили через самокоманду /addgroup.

Все команды пишутся ВАМИ, от своего аккаунта, в любом чате (например,
в "Избранном"), и начинаются со слэша /. Полный список — команда /help.

Запуск: python userbot.py
Требуются переменные окружения: API_ID, API_HASH, SESSION_STRING
"""

import asyncio
import logging
import os
import random

from telethon import TelegramClient, events, utils
from telethon.sessions import StringSession
from telethon.tl.types import Channel

import groups_store as store
import phrases_store as phrases

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError(
        "Не заданы переменные окружения API_ID / API_HASH / SESSION_STRING.\n"
        "Сначала запустите generate_session.py локально, чтобы их получить."
    )

API_ID = int(API_ID)

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

HELP_TEXT = (
    "🤖 Команды юзербота (пишутся вами, от своего аккаунта):\n\n"
    "— Группы —\n"
    "/addgroup @username — подключить группу обсуждений\n"
    "/removegroup @username — отключить группу\n"
    "/mygroups — список подключённых групп\n\n"
    "— Фразы для автокомментария —\n"
    "/phrases — показать все фразы и их статус (вкл/выкл)\n"
    "/setphrase <номер> <текст> — изменить текст фразы\n"
    "/enable <номер> — включить фразу\n"
    "/disable <номер> — выключить фразу\n\n"
    "— Прочее —\n"
    "/status — проверить, что юзербот работает\n"
    "/help — показать этот список команд"
)


def normalize_username(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("@"):
        raw = raw[1:]
    return raw


def is_automatic_channel_forward(message) -> bool:
    """
    Определяет, что сообщение — это автоматически пересланный пост канала
    в привязанную группу обсуждений (а не ручная пересылка от пользователя).

    Признак: у сообщения есть fwd_from.channel_post, а автор сообщения в группе —
    сам канал (Channel), а не обычный пользователь.
    """
    if not message.fwd_from:
        return False
    if not getattr(message.fwd_from, "channel_post", None):
        return False
    sender = message.sender
    return isinstance(sender, Channel)


# =========================================================
#         САМОКОМАНДЫ (пишете их сами, от своего лица)
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/addgroup(?:\s+(.+))?$'))
async def cmd_addgroup(event):
    arg = event.pattern_match.group(1)
    if not arg:
        await event.edit("Использование: /addgroup @username_группы")
        return

    username = normalize_username(arg)

    try:
        entity = await client.get_entity(username)
    except Exception:
        await event.edit(f"❌ Не удалось найти группу @{username}. Проверьте юзернейм.")
        return

    if not isinstance(entity, Channel) or not entity.megagroup:
        await event.edit(f"❌ @{username} — это не группа обсуждений (супергруппа).")
        return

    store.add_group(utils.get_peer_id(entity), username)
    await event.edit(f"✅ Группа @{username} подключена. Буду комментировать посты канала здесь.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/removegroup(?:\s+(.+))?$'))
async def cmd_removegroup(event):
    arg = event.pattern_match.group(1)
    if not arg:
        await event.edit("Использование: /removegroup @username_группы")
        return

    username = normalize_username(arg)
    removed = store.remove_group_by_username(username)

    if removed:
        await event.edit(f"✅ Группа @{username} отключена.")
    else:
        await event.edit(f"Группа @{username} не найдена среди подключённых.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/mygroups$'))
async def cmd_mygroups(event):
    groups = store.list_groups()
    if not groups:
        await event.edit("Подключённых групп пока нет. Используйте /addgroup @username")
        return

    lines = [f"• @{info['username']}" for info in groups.values()]
    await event.edit("📋 Подключённые группы:\n" + "\n".join(lines))


# =========================================================
#              УПРАВЛЕНИЕ ФРАЗАМИ
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/phrases$'))
async def cmd_phrases(event):
    data = phrases.list_phrases()
    lines = []
    for i, p in enumerate(data, start=1):
        mark = "✅" if p.get("enabled") else "⛔"
        lines.append(f"{mark} {i}. {p['text']}")

    text = "📋 Фразы для автокомментария:\n" + "\n".join(lines)
    text += (
        "\n\nИзменить текст: /setphrase <номер> <текст>"
        "\nВключить: /enable <номер>"
        "\nВыключить: /disable <номер>"
    )
    await event.edit(text)


@client.on(events.NewMessage(outgoing=True, pattern=r'^/setphrase\s+(\d+)\s+(.+)$'))
async def cmd_setphrase(event):
    idx = int(event.pattern_match.group(1))
    text = event.pattern_match.group(2).strip()

    if phrases.set_phrase(idx, text):
        await event.edit(f"✅ Фраза №{idx} изменена на: {text}")
    else:
        total = len(phrases.list_phrases())
        await event.edit(f"❌ Нет фразы №{idx}. Всего фраз: {total} (номера от 1 до {total}).")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/enable\s+(\d+)$'))
async def cmd_enable(event):
    idx = int(event.pattern_match.group(1))
    if phrases.set_enabled(idx, True):
        text = phrases.list_phrases()[idx - 1]["text"]
        await event.edit(f"✅ Фраза №{idx} («{text}») включена.")
    else:
        await event.edit(f"❌ Нет фразы №{idx}.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/disable\s+(\d+)$'))
async def cmd_disable(event):
    idx = int(event.pattern_match.group(1))
    if phrases.set_enabled(idx, False):
        text = phrases.list_phrases()[idx - 1]["text"]
        await event.edit(f"✅ Фраза №{idx} («{text}») выключена.")
    else:
        await event.edit(f"❌ Нет фразы №{idx}.")


# =========================================================
#                      ПРОЧЕЕ
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/status$'))
async def cmd_status(event):
    groups = store.list_groups()
    enabled_count = len(phrases.get_enabled_texts())
    await event.edit(
        f"✅ Юзербот работает.\n"
        f"Подключено групп: {len(groups)}\n"
        f"Включено фраз: {enabled_count}"
    )


@client.on(events.NewMessage(outgoing=True, pattern=r'^/help$'))
async def cmd_help(event):
    await event.edit(HELP_TEXT)


# =========================================================
#              АВТОКОММЕНТИРОВАНИЕ ПОСТОВ КАНАЛА
# =========================================================

@client.on(events.NewMessage())
async def auto_comment(event):
    # реагируем только в явно подключённых группах
    if not store.is_allowed(event.chat_id):
        return

    if not is_automatic_channel_forward(event.message):
        return

    texts = phrases.get_enabled_texts()
    if not texts:
        logger.warning("Нет ни одной включённой фразы — комментарий не отправлен.")
        return

    text = random.choice(texts)

    try:
        await event.message.reply(text)
        logger.info(f"Оставлен комментарий '{text}' в чате {event.chat_id}")
    except Exception as e:
        logger.warning(f"Не удалось ответить в чате {event.chat_id}: {e}")


async def main():
    await client.start()
    me = await client.get_me()
    logger.info(f"Юзербот запущен под аккаунтом: {me.first_name} (id {me.id})")
    logger.info("Ожидаю новые посты в подключённых группах...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
