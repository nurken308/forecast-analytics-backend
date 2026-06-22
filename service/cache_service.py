import json
from pathlib import Path
from datetime import datetime, timedelta

CACHE_PATH = Path("storage/forecasts_cache.json")


def load_cache():
    if not CACHE_PATH.exists():
        return {}

    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # если файл сломан — просто очищаем
        return {}


def save_segment_cache(segment_id: str, payload: dict) -> dict:
    CACHE_PATH.parent.mkdir(exist_ok=True)

    cache = load_cache()

    cache[segment_id] = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "data": payload,
    }

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    return cache[segment_id]


def get_segment_cache(segment_id: str):
    cache = load_cache()
    return cache.get(segment_id)


def is_cache_recent(segment_id: str, minutes: int = 10) -> bool:
    item = get_segment_cache(segment_id)

    if not item:
        return False

    updated_at = datetime.fromisoformat(item["updated_at"])
    return datetime.now() - updated_at < timedelta(minutes=minutes)