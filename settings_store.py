import json
import os

SETTINGS_FILE = "settings.json"

MODE_AUTOCOMMENT = "autocomment"
MODE_CHAT = "chat"


def _defaults() -> dict:
    return {
        "enabled": True,
        "mode": MODE_AUTOCOMMENT,
        "interval": 1,
        "chat_interval": 5,
        "counters": {},
        "chat_counters": {},
        "dm_enabled": False,
        "dm_interval": 1,
        "dm_counters": {},
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

    if "autocomment_enabled" in data and "enabled" not in data:
        data["enabled"] = data["autocomment_enabled"]

    return data


def _save(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_enabled() -> bool:
    return bool(_load().get("enabled", True))


def set_enabled(value: bool) -> None:
    data = _load()
    data["enabled"] = value
    _save(data)


def get_mode() -> str:
    return _load().get("mode", MODE_AUTOCOMMENT)


def set_mode(mode: str) -> bool:
    if mode not in (MODE_AUTOCOMMENT, MODE_CHAT):
        return False
    data = _load()
    data["mode"] = mode
    _save(data)
    return True


def get_interval() -> int:
    return int(_load().get("interval", 1))


def set_interval(n: int) -> bool:
    if n < 1:
        return False
    data = _load()
    data["interval"] = n
    _save(data)
    return True


def bump_and_should_comment(chat_id: int) -> bool:
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


def get_chat_interval() -> int:
    return int(_load().get("chat_interval", 5))


def set_chat_interval(n: int) -> bool:
    if n < 1:
        return False
    data = _load()
    data["chat_interval"] = n
    _save(data)
    return True


def bump_and_should_reply_chat(chat_id: int) -> bool:
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


def is_dm_enabled() -> bool:
    return bool(_load().get("dm_enabled", False))


def set_dm_enabled(value: bool) -> None:
    data = _load()
    data["dm_enabled"] = value
    _save(data)


def get_dm_interval() -> int:
    return int(_load().get("dm_interval", 1))


def set_dm_interval(n: int) -> bool:
    if n < 1:
        return False
    data = _load()
    data["dm_interval"] = n
    _save(data)
    return True


def bump_and_should_reply_dm(chat_id: int) -> bool:
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
