"""
Юзербот: работает от имени вашего личного Telegram-аккаунта.

Два режима работы (переключаются командой /mode):

  autocomment — пишет одну из включённых фраз в комментарии под постами,
                автоматически пересланными из канала в группу обсуждений.
                Интервал: раз в N постов (/interval).

  chat        — отвечает одной из включённых фраз на обычные сообщения
                людей в группе. Интервал: раз в N сообщений (/chatinterval).

Работает только в группах, которые вы явно подключили через /addgroup.
Все команды пишутся ВАМИ, от своего аккаунта, в любом чате (например,
в "Избранном"), и начинаются со слэша /. Полный список — команда /help.

Запуск: python userbot.py
Требуются переменные окружения: API_ID, API_HASH, SESSION_STRING
"""

import asyncio
import logging
import os

from telethon import TelegramClient, events, utils
from telethon.sessions import StringSession
from telethon.tl.types import Channel, User

import groups_store as store
import dm_store as dms
import phrases_store as phrases
import settings_store as settings

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

MODE_LABELS = {
    settings.MODE_AUTOCOMMENT: "автокомментинг постов канала",
    settings.MODE_CHAT: "обычный чат (ответы на сообщения людей)",
}

HELP_TEXT = (
    "🤖 Команды юзербота (пишутся вами, от своего аккаунта):\n\n"
    "— Режим работы —\n"
    "/mode — показать текущий режим\n"
    "/mode autocomment — режим: комментировать посты канала\n"
    "/mode chat — режим: отвечать на обычные сообщения в группе\n"
    "/autoon — включить работу бота (в текущем режиме)\n"
    "/autooff — выключить работу бота полностью\n\n"
    "— Группы —\n"
    "/addgroup @username — подключить группу\n"
    "/removegroup @username — отключить группу\n"
    "/mygroups — список подключённых групп\n\n"
    "— Личные чаты —\n"
    "/adddm @username или /adddm 123456789 — подключить личный чат\n"
    "/removedm @username — отключить личный чат\n"
    "/mydms — список подключённых личных чатов\n"
    "/dmon / /dmoff — включить/выключить автоответы в личных чатах\n"
    "/dminterval — интервал для личных чатов (раз в N сообщений)\n"
    "/dminterval <N> — задать его (1 = отвечать на каждое)\n\n"
    "— Фразы —\n"
    "/phrases — показать фразы, статус и вероятность (%)\n"
    "/setphrase <номер> <текст> — изменить текст фразы\n"
    "/enable <номер> — включить фразу\n"
    "/disable <номер> — выключить фразу\n"
    "/setweight <номер> <вес> — задать вес фразы (влияет на % вероятности)\n\n"
    "— Интервалы —\n"
    "/interval — интервал для режима autocomment (раз в N постов)\n"
    "/interval <N> — задать его\n"
    "/chatinterval — интервал для режима chat (раз в N сообщений людей)\n"
    "/chatinterval <N> — задать его\n\n"
    "— Прочее —\n"
    "/status — текущее состояние\n"
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
    """
    if not message.fwd_from:
        return False
    if not getattr(message.fwd_from, "channel_post", None):
        return False
    sender = message.sender
    return isinstance(sender, Channel)


def phrases_status_text() -> str:
    data = phrases.list_phrases()
    enabled_weight_sum = sum(p.get("weight", 1) for p in data if p.get("enabled")) or 1

    lines = []
    for i, p in enumerate(data, start=1):
        mark = "✅" if p.get("enabled") else "⛔"
        weight = p.get("weight", 1)
        if p.get("enabled"):
            percent = weight / enabled_weight_sum * 100
            lines.append(f"{mark} {i}. {p['text']}  (вес {weight}, ~{percent:.1f}%)")
        else:
            lines.append(f"{mark} {i}. {p['text']}  (выключена)")
    return "\n".join(lines)


# =========================================================
#                    РЕЖИМ И ВКЛ/ВЫКЛ
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/mode(?:\s+(\w+))?$'))
async def cmd_mode(event):
    arg = event.pattern_match.group(1)

    if not arg:
        current = settings.get_mode()
        await event.edit(
            f"Текущий режим: <b>{MODE_LABELS.get(current, current)}</b>\n\n"
            "Изменить: /mode autocomment или /mode chat"
        )
        return

    if settings.set_mode(arg):
        label = MODE_LABELS.get(arg, arg)
        await event.edit(f"✅ Режим изменён: {label}")
    else:
        await event.edit("❌ Неизвестный режим. Доступно: autocomment, chat")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/autoon$'))
async def cmd_autoon(event):
    settings.set_enabled(True)
    mode = MODE_LABELS.get(settings.get_mode(), settings.get_mode())
    await event.edit(f"✅ Бот включён. Текущий режим: {mode}")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/autooff$'))
async def cmd_autooff(event):
    settings.set_enabled(False)
    await event.edit("⛔ Бот выключен полностью (в любом режиме).")


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
    await event.edit(f"✅ Группа @{username} подключена.")


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
#                 ЛИЧНЫЕ ЧАТЫ (DM)
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/adddm(?:\s+(.+))?$'))
async def cmd_adddm(event):
    arg = event.pattern_match.group(1)
    if not arg:
        await event.edit("Использование: /adddm @username или /adddm 123456789")
        return

    raw = arg.strip()

    try:
        if raw.lstrip('-').isdigit():
            entity = await client.get_entity(int(raw))
        else:
            entity = await client.get_entity(normalize_username(raw))
    except Exception:
        await event.edit(f"❌ Не удалось найти пользователя «{raw}». Проверьте username/ID.")
        return

    if not isinstance(entity, User):
        await event.edit("❌ Это не личный пользователь (не User).")
        return

    label = entity.username or entity.first_name or str(entity.id)
    dms.add_dm(utils.get_peer_id(entity), label)
    await event.edit(f"✅ Личный чат с «{label}» подключён.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/removedm(?:\s+(.+))?$'))
async def cmd_removedm(event):
    arg = event.pattern_match.group(1)
    if not arg:
        await event.edit("Использование: /removedm @username (или как указывали при добавлении)")
        return

    raw = normalize_username(arg.strip())
    removed = dms.remove_dm_by_label(raw)

    if removed:
        await event.edit(f"✅ Личный чат «{raw}» отключён.")
    else:
        await event.edit(f"Личный чат «{raw}» не найден среди подключённых.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/mydms$'))
async def cmd_mydms(event):
    data = dms.list_dms()
    if not data:
        await event.edit("Подключённых личных чатов пока нет. Используйте /adddm @username")
        return

    lines = [f"• {info['label']}" for info in data.values()]
    await event.edit("📋 Подключённые личные чаты:\n" + "\n".join(lines))


@client.on(events.NewMessage(outgoing=True, pattern=r'^/dmon$'))
async def cmd_dmon(event):
    settings.set_dm_enabled(True)
    await event.edit("✅ Автоответы в личных чатах включены.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/dmoff$'))
async def cmd_dmoff(event):
    settings.set_dm_enabled(False)
    await event.edit("⛔ Автоответы в личных чатах выключены.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/dminterval(?:\s+(\d+))?$'))
async def cmd_dminterval(event):
    arg = event.pattern_match.group(1)

    if not arg:
        current = settings.get_dm_interval()
        await event.edit(
            f"Интервал личных чатов: раз в {current} сообщений(-ие).\n"
            f"Изменить: /dminterval <N> (1 = отвечать на каждое, например /dminterval 3)"
        )
        return

    n = int(arg)
    if settings.set_dm_interval(n):
        await event.edit(f"✅ Личные чаты: отвечать раз в {n} сообщений(-ие).")
    else:
        await event.edit("❌ Интервал должен быть числом ≥ 1.")


# =========================================================
#              УПРАВЛЕНИЕ ФРАЗАМИ И ИХ ВЕСОМ
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/phrases$'))
async def cmd_phrases(event):
    text = "📋 Фразы:\n" + phrases_status_text()
    text += (
        "\n\nИзменить текст: /setphrase <номер> <текст>"
        "\nВключить/выключить: /enable <номер> | /disable <номер>"
        "\nИзменить вес (%): /setweight <номер> <вес>"
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


@client.on(events.NewMessage(outgoing=True, pattern=r'^/setweight\s+(\d+)\s+(\d+)$'))
async def cmd_setweight(event):
    idx = int(event.pattern_match.group(1))
    weight = int(event.pattern_match.group(2))

    if phrases.set_weight(idx, weight):
        text = phrases.list_phrases()[idx - 1]["text"]
        await event.edit(f"✅ Вес фразы №{idx} («{text}») установлен: {weight}\n\n" + phrases_status_text())
    else:
        total = len(phrases.list_phrases())
        await event.edit(f"❌ Нет фразы №{idx} или неверный вес. Всего фраз: {total}.")


# =========================================================
#                       ИНТЕРВАЛЫ
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/interval(?:\s+(\d+))?$'))
async def cmd_interval(event):
    arg = event.pattern_match.group(1)

    if not arg:
        current = settings.get_interval()
        await event.edit(
            f"Интервал автокомментинга: раз в {current} пост(ов).\n"
            f"Изменить: /interval <N>, например /interval 5"
        )
        return

    n = int(arg)
    if settings.set_interval(n):
        await event.edit(f"✅ Автокомментинг: раз в {n} пост(ов).")
    else:
        await event.edit("❌ Интервал должен быть числом ≥ 1.")


@client.on(events.NewMessage(outgoing=True, pattern=r'^/chatinterval(?:\s+(\d+))?$'))
async def cmd_chatinterval(event):
    arg = event.pattern_match.group(1)

    if not arg:
        current = settings.get_chat_interval()
        await event.edit(
            f"Интервал чат-режима: раз в {current} сообщений(-ие) людей.\n"
            f"Изменить: /chatinterval <N>, например /chatinterval 4"
        )
        return

    n = int(arg)
    if settings.set_chat_interval(n):
        await event.edit(f"✅ Чат-режим: отвечать раз в {n} сообщений(-ие) людей.")
    else:
        await event.edit("❌ Интервал должен быть числом ≥ 1.")


# =========================================================
#                      ПРОЧЕЕ
# =========================================================

@client.on(events.NewMessage(outgoing=True, pattern=r'^/status$'))
async def cmd_status(event):
    groups = store.list_groups()
    dm_chats = dms.list_dms()
    enabled_count = len(phrases.get_enabled_texts())
    state = "включён ✅" if settings.is_enabled() else "выключен ⛔"
    mode = MODE_LABELS.get(settings.get_mode(), settings.get_mode())
    dm_state = "включены ✅" if settings.is_dm_enabled() else "выключены ⛔"

    await event.edit(
        f"Бот (группы): {state}\n"
        f"Режим: {mode}\n"
        f"Интервал автокомментинга: раз в {settings.get_interval()} пост(ов)\n"
        f"Интервал чат-режима: раз в {settings.get_chat_interval()} сообщений(-ие)\n"
        f"Подключено групп: {len(groups)}\n\n"
        f"Личные чаты: {dm_state}\n"
        f"Интервал личных чатов: раз в {settings.get_dm_interval()} сообщений(-ие)\n"
        f"Подключено личных чатов: {len(dm_chats)}\n\n"
        f"Включено фраз: {enabled_count}"
    )


@client.on(events.NewMessage(outgoing=True, pattern=r'^/help$'))
async def cmd_help(event):
    await event.edit(HELP_TEXT)


# =========================================================
#     РЕЖИМ 1: АВТОКОММЕНТИРОВАНИЕ ПОСТОВ КАНАЛА
# =========================================================

@client.on(events.NewMessage())
async def auto_comment(event):
    if not store.is_allowed(event.chat_id):
        return
    if settings.get_mode() != settings.MODE_AUTOCOMMENT:
        return
    if not settings.is_enabled():
        return
    if not is_automatic_channel_forward(event.message):
        return
    if not settings.bump_and_should_comment(event.chat_id):
        return

    text = phrases.pick_random_weighted()
    if text is None:
        logger.warning("Нет ни одной включённой фразы — комментарий не отправлен.")
        return

    try:
        await event.message.reply(text)
        logger.info(f"[autocomment] Оставлен комментарий '{text}' в чате {event.chat_id}")
    except Exception as e:
        logger.warning(f"Не удалось ответить в чате {event.chat_id}: {e}")


# =========================================================
#     РЕЖИМ 2: ОТВЕТЫ НА ОБЫЧНЫЕ СООБЩЕНИЯ ЛЮДЕЙ В ГРУППЕ
# =========================================================

@client.on(events.NewMessage(incoming=True))
async def chat_reply(event):
    if not store.is_allowed(event.chat_id):
        return
    if settings.get_mode() != settings.MODE_CHAT:
        return
    if not settings.is_enabled():
        return

    message = event.message

    # не реагируем на пересланные посты канала — это задача режима autocomment
    if is_automatic_channel_forward(message):
        return

    # игнорируем сервисные сообщения и сообщения без текста
    if not (message.text or message.raw_text):
        return

    if not settings.bump_and_should_reply_chat(event.chat_id):
        return

    text = phrases.pick_random_weighted()
    if text is None:
        logger.warning("Нет ни одной включённой фразы — ответ не отправлен.")
        return

    try:
        await message.reply(text)
        logger.info(f"[chat] Ответил '{text}' в чате {event.chat_id}")
    except Exception as e:
        logger.warning(f"Не удалось ответить в чате {event.chat_id}: {e}")


# =========================================================
#              РЕЖИМ 3: АВТООТВЕТЫ В ЛИЧНЫХ ЧАТАХ
# =========================================================

@client.on(events.NewMessage(incoming=True))
async def dm_reply(event):
    if not event.is_private:
        return
    if not dms.is_allowed(event.chat_id):
        return
    if not settings.is_dm_enabled():
        return

    message = event.message
    if not (message.text or message.raw_text):
        return

    if not settings.bump_and_should_reply_dm(event.chat_id):
        return

    text = phrases.pick_random_weighted()
    if text is None:
        logger.warning("Нет ни одной включённой фразы — ответ в личку не отправлен.")
        return

    try:
        await message.reply(text)
        logger.info(f"[dm] Ответил '{text}' в личном чате {event.chat_id}")
    except Exception as e:
        logger.warning(f"Не удалось ответить в личном чате {event.chat_id}: {e}")


async def main():
    await client.start()
    me = await client.get_me()
    logger.info(f"Юзербот запущен под аккаунтом: {me.first_name} (id {me.id})")
    logger.info(f"Режим: {settings.get_mode()}, включён: {settings.is_enabled()}")
    logger.info(f"Интервал autocomment: {settings.get_interval()}, chat: {settings.get_chat_interval()}")
    logger.info(f"Личные чаты включены: {settings.is_dm_enabled()}, интервал: {settings.get_dm_interval()}")
    logger.info("Ожидаю новые сообщения в подключённых группах и личных чатах...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
