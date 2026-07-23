import json
import os
import random

PHRASES_FILE = "phrases.json"

# Фразы по умолчанию — используются при первом запуске (если phrases.json ещё нет),
# либо чтобы "доукомплектовать" уже существующий файл с меньшим числом фраз до 10.
# При доукомплектовании ВСЕ фразы (старые и новые) выравниваются на 10% каждая
# и включаются — то есть после обновления сразу равная вероятность у всех 10.
DEFAULT_PHRASES = [
    {"text": "1", "enabled": True, "weight": 10},
    {"text": "🔥", "enabled": True, "weight": 10},
    {"text": "👍", "enabled": True, "weight": 10},
    {"text": "😁", "enabled": True, "weight": 10},
    {"text": "+", "enabled": True, "weight": 10},
    {"text": "😂", "enabled": True, "weight": 10},
    {"text": "🎉", "enabled": True, "weight": 10},
    {"text": "❤️", "enabled": True, "weight": 10},
    {"text": "👏", "enabled": True, "weight": 10},
    {"text": "🙌", "enabled": True, "weight": 10},
]


def _load() -> list:
    if not os.path.exists(PHRASES_FILE):
        data = [dict(p) for p in DEFAULT_PHRASES]
        _save(data)
        return data

    try:
        with open(PHRASES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data:
                data = [dict(p) for p in DEFAULT_PHRASES]
    except (json.JSONDecodeError, FileNotFoundError):
        data = [dict(p) for p in DEFAULT_PHRASES]

    for p in data:
        p.setdefault("weight", 1)
        p.setdefault("enabled", True)

    # Доукомплектовываем существующий файл до 10 фраз. Как и просили — все 10
    # (и старые, и новые) становятся равными: по 10% и включены.
    if len(data) < len(DEFAULT_PHRASES):
        for extra in DEFAULT_PHRASES[len(data):]:
            data.append({"text": extra["text"], "enabled": True, "weight": 10})
        for p in data:
            p["weight"] = 10
            p["enabled"] = True
        _save(data)

    return data


def _save(data: list):
    with open(PHRASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_phrases() -> list:
    """Возвращает список всех фраз: [{"text":..., "enabled":..., "weight":...}, ...]"""
    return _load()


def add_phrase(text: str, weight: int = 0, enabled: bool = True) -> int:
    """Добавляет новую фразу в конец списка. Возвращает её номер (с 1)."""
    data = _load()
    data.append({"text": text, "enabled": enabled, "weight": max(0, weight)})
    _save(data)
    return len(data)


def remove_phrase(index: int) -> bool:
    """Удаляет фразу по номеру. Нельзя удалить последнюю оставшуюся фразу."""
    data = _load()
    if index < 1 or index > len(data):
        return False
    if len(data) <= 1:
        return False
    data.pop(index - 1)
    _save(data)
    return True


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
