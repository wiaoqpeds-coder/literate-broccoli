import json
import os

GROUPS_FILE = "allowed_groups.json"


def _load() -> dict:
    if not os.path.exists(GROUPS_FILE):
        return {}
    try:
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save(data: dict):
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_group(chat_id: int, username: str):
    data = _load()
    data[str(chat_id)] = {"username": username}
    _save(data)


def remove_group_by_username(username: str) -> bool:
    data = _load()
    key_to_remove = None
    for chat_id, info in data.items():
        if info.get("username") == username:
            key_to_remove = chat_id
            break
    if key_to_remove is None:
        return False
    del data[key_to_remove]
    _save(data)
    return True


def remove_group_by_chat_id(chat_id) -> bool:
    """Отключает группу по chat_id (используется веб-панелью)."""
    data = _load()
    key = str(chat_id)
    if key not in data:
        return False
    del data[key]
    _save(data)
    return True


def is_allowed(chat_id: int) -> bool:
    data = _load()
    return str(chat_id) in data


def list_groups() -> dict:
    return _load()
