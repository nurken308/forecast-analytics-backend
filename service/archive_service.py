import json
from pathlib import Path
from datetime import datetime

ARCHIVE_PATH = Path("storage/forecast_archive.json")


def load_archive() -> dict:
    if not ARCHIVE_PATH.exists():
        return {}

    try:
        with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_to_archive(segment_id: str, quarter: str, payload: dict):
    ARCHIVE_PATH.parent.mkdir(exist_ok=True)

    archive = load_archive()

    key = f"{segment_id}_{quarter}"

    archive[key] = {
        "segment_id": segment_id,
        "quarter": quarter,
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "data": payload,
    }

    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    return archive[key]


def get_archive():
    return load_archive()