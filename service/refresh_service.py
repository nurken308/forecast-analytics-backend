from service.oracle_sql_service import load_oracle_pivot
from service.cache_service import (
    save_segment_cache,
    get_segment_cache,
    is_cache_recent,
)
import pandas as pd

def refresh_forecast(segment_id: str, force: bool = False):
    if not force and is_cache_recent(segment_id, minutes=10):
        cached = get_segment_cache(segment_id)
        return {
            "source": "cache",
            "message": "Forecast was updated recently",
            **cached["data"],
        }

    df = load_oracle_pivot(segment_id)
    df = df.copy()

    for col in df.columns:
        df[col] = df[col].apply(lambda x: x.item() if hasattr(x, "item") else x)

    for col in df.columns:
        if "date" in col.lower() or "ymd" in col.lower():
            df[col] = df[col].astype(str)

    df = df.where(pd.notnull(df), None)

    rows = df.to_dict(orient="records")

    df = df.copy()

    for col in df.columns:
        if "date" in col.lower() or "ymd" in col.lower():
            df[col] = df[col].astype(str)

    df = df.where(pd.notnull(df), None)

    rows = df.to_dict(orient="records")

    payload = {
        "segment_id": segment_id,
        "source": "oracle",
        "forecast": rows,
        "r2_adj": None,
        "actual_comparison": [],
    }

    save_segment_cache(segment_id, payload)

    return payload


def get_saved_forecast(segment_id: str):
    cached = get_segment_cache(segment_id)

    if not cached:
        return {
            "segment_id": segment_id,
            "source": "empty_cache",
            "forecast": [],
            "r2_adj": None,
            "actual_comparison": [],
        }

    return cached["data"]