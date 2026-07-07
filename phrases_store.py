import json
import os

PHRASES_FILE = "phrases.json"

# Фразы по умолчанию (можно менять текст через команду /setphrase)
DEFAULT_PHRASES = [
    {"text": "1", "enabled": True},
    {"text": "🔥", "enabled": True},
    {"text": "👍", "enabled": True},
    {"text": "😁", "enabled": True},
    {"text": "+", "enabled": True},
]


def _load() -> list:
    if not os.path.exists(PHRASES_FILE):
        return [dict(p) for p in DEFAULT_PHRASES]
    try:
        with open(PHRASES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data:
                return [dict(p) for p in DEFAULT_PHRASES]
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return [dict(p) for p in DEFAULT_PHRASES]


def _save(data: list):
    with open(PHRASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_phrases() -> list:
    """Возвращает список всех фраз: [{"text": ..., "enabled": ...}, ...]"""
    return _load()


def set_phrase(index: int, text: str) -> bool:
    """Меняет текст фразы №index (нумерация с 1). Возвращает False, если такого номера нет."""
    data = _load()
    if index < 1 or index > len(data):
        return False
    data[index - 1]["text"] = text
    _save(data)
    return True


def set_enabled(index: int, enabled: bool) -> bool:
    """Включает/выключает фразу №index. Возвращает False, если такого номера нет."""
    data = _load()
    if index < 1 or index > len(data):
        return False
    data[index - 1]["enabled"] = enabled
    _save(data)
    return True


def get_enabled_texts() -> list:
    """Возвращает тексты только включённых фраз — из них бот выбирает случайную."""
    data = _load()
    return [p["text"] for p in data if p.get("enabled")]
