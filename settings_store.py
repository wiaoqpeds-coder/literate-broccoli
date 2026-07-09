import json
import os

SETTINGS_FILE = "settings.json"

MODE_AUTOCOMMENT = "autocomment"   # комментирует посты канала в группе обсуждений
MODE_CHAT = "chat"                 # отвечает на обычные сообщения людей в группе


def _defaults() -> dict:
    return {
        "enabled": True,             # общий переключатель — работает ли бот вообще
        "mode": MODE_AUTOCOMMENT,    # текущий режим: autocomment или chat
        "interval": 1,               # автокомментинг: раз в N постов канала
        "chat_interval": 5,          # чат-режим: раз в N сообщений людей
        "counters": {},              # счётчики постов по группам (режим autocomment)
        "chat_counters": {},         # счётчики сообщений по группам (режим chat)
        "dm_enabled": False,         # отдельный переключатель для личных чатов
        "dm_interval": 1,            # личные чаты: раз в N сообщений (1 = на каждое)
        "dm_counters": {},           # счётчики сообщений по личным чатам
    }


def _load() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return _defaults()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except (json.JSONDecodeError, FileNotFoundError):
        data = {}

    defaults = _defaults()
    for key, value in defaults.items():
        data.setdefault(key, value)

    # поддержка старого имени поля из предыдущей версии
    if "autocomment_enabled" in data and "enabled" not in data:
        data["enabled"] = data["autocomment_enabled"]

    return data


def _save(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================================================
#                 ОБЩИЙ ПЕРЕКЛЮЧАТЕЛЬ ВКЛ/ВЫКЛ
# =========================================================

def is_enabled() -> bool:
    return bool(_load().get("enabled", True))


def set_enabled(value: bool) -> None:
    data = _load()
    data["enabled"] = value
    _save(data)


# =========================================================
#                          РЕЖИМ
# =========================================================

def get_mode() -> str:
    return _load().get("mode", MODE_AUTOCOMMENT)


def set_mode(mode: str) -> bool:
    if mode not in (MODE_AUTOCOMMENT, MODE_CHAT):
        return False
    data = _load()
    data["mode"] = mode
    _save(data)
    return True


# =========================================================
#         ИНТЕРВАЛ РЕЖИМА "АВТОКОММЕНТИНГ" (посты канала)
# =========================================================

def get_interval() -> int:
    return int(_load().get("interval", 1))


def set_interval(n: int) -> bool:
    """Задаёт интервал (каждый N-й пост). Возвращает False, если n < 1."""
    if n < 1:
        return False
    data = _load()
    data["interval"] = n
    _save(data)
    return True


def bump_and_should_comment(chat_id: int) -> bool:
    """
    Увеличивает счётчик постов канала для конкретной группы на 1.
    Если счётчик достиг интервала — сбрасывает его и возвращает True
    (пора комментировать). Иначе — False.
    """
    data = _load()
    counters = data.setdefault("counters", {})
    key = str(chat_id)
    counters[key] = counters.get(key, 0) + 1

    interval = max(1, int(data.get("interval", 1)))
    if counters[key] >= interval:
        counters[key] = 0
        _save(data)
        return True

    _save(data)
    return False


# =========================================================
#      ИНТЕРВАЛ РЕЖИМА "ЧАТ" (обычные сообщения людей)
# =========================================================

def get_chat_interval() -> int:
    return int(_load().get("chat_interval", 5))


def set_chat_interval(n: int) -> bool:
    """Задаёт интервал (раз в N сообщений людей). Возвращает False, если n < 1."""
    if n < 1:
        return False
    data = _load()
    data["chat_interval"] = n
    _save(data)
    return True


def bump_and_should_reply_chat(chat_id: int) -> bool:
    """
    Увеличивает счётчик обычных сообщений людей для конкретной группы на 1.
    Если счётчик достиг chat_interval — сбрасывает его и возвращает True
    (пора ответить). Иначе — False.
    """
    data = _load()
    counters = data.setdefault("chat_counters", {})
    key = str(chat_id)
    counters[key] = counters.get(key, 0) + 1

    interval = max(1, int(data.get("chat_interval", 5)))
    if counters[key] >= interval:
        counters[key] = 0
        _save(data)
        return True

    _save(data)
    return False


# =========================================================
#                 ЛИЧНЫЕ ЧАТЫ (DM)
# =========================================================

def is_dm_enabled() -> bool:
    return bool(_load().get("dm_enabled", False))


def set_dm_enabled(value: bool) -> None:
    data = _load()
    data["dm_enabled"] = value
    _save(data)


def get_dm_interval() -> int:
    return int(_load().get("dm_interval", 1))


def set_dm_interval(n: int) -> bool:
    """Задаёт интервал для личных чатов (раз в N сообщений). Возвращает False, если n < 1."""
    if n < 1:
        return False
    data = _load()
    data["dm_interval"] = n
    _save(data)
    return True


def bump_and_should_reply_dm(chat_id: int) -> bool:
    """
    Увеличивает счётчик сообщений для конкретного личного чата на 1.
    Если счётчик достиг dm_interval — сбрасывает его и возвращает True
    (пора ответить). При dm_interval=1 отвечает на каждое сообщение.
    """
    data = _load()
    counters = data.setdefault("dm_counters", {})
    key = str(chat_id)
    counters[key] = counters.get(key, 0) + 1

    interval = max(1, int(data.get("dm_interval", 1)))
    if counters[key] >= interval:
        counters[key] = 0
        _save(data)
        return True

    _save(data)
    return False
