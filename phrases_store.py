import json
import os
import random

PHRASES_FILE = "phrases.json"

# Фразы по умолчанию (можно менять текст и вес через команды/панель)
DEFAULT_PHRASES = [
    {"text": "1", "enabled": True, "weight": 1},
    {"text": "🔥", "enabled": True, "weight": 1},
    {"text": "👍", "enabled": True, "weight": 1},
    {"text": "😁", "enabled": True, "weight": 1},
    {"text": "+", "enabled": True, "weight": 1},
]


def _load() -> list:
    if not os.path.exists(PHRASES_FILE):
        return [dict(p) for p in DEFAULT_PHRASES]
    try:
        with open(PHRASES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data:
                return [dict(p) for p in DEFAULT_PHRASES]
    except (json.JSONDecodeError, FileNotFoundError):
        return [dict(p) for p in DEFAULT_PHRASES]

    for p in data:
        p.setdefault("weight", 1)
    return data


def _save(data: list):
    with open(PHRASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_phrases() -> list:
    """Возвращает список всех фраз: [{"text":..., "enabled":..., "weight":...}, ...]"""
    return _load()


def set_phrase(index: int, text: str) -> bool:
    data = _load()
    if index < 1 or index > len(data):
        return False
    data[index - 1]["text"] = text
    _save(data)
    return True


def set_enabled(index: int, enabled: bool) -> bool:
    data = _load()
    if index < 1 or index > len(data):
        return False
    data[index - 1]["enabled"] = enabled
    _save(data)
    return True


def set_weight(index: int, weight: int) -> bool:
    data = _load()
    if index < 1 or index > len(data):
        return False
    if weight < 0:
        return False
    data[index - 1]["weight"] = weight
    _save(data)
    return True


def get_enabled_texts() -> list:
    data = _load()
    return [p["text"] for p in data if p.get("enabled")]


def pick_random_weighted():
    data = _load()
    enabled = [p for p in data if p.get("enabled")]
    if not enabled:
        return None
    weights = [max(0, p.get("weight", 1)) for p in enabled]
    if sum(weights) <= 0:
        return None
    texts = [p["text"] for p in enabled]
    return random.choices(texts, weights=weights, k=1)[0]
