import pandas as pd


DAILY_ENTITY_CONFIG = {
    "retail": {
        "display_name": "Розница",
        "column": "segment1",
        "value": "4.Розница",
    },

    "vkl": {
        "display_name": "ВКЛ",
        "column": "products",
        "value": "ВКЛ",
    },
    "vkl_soft": {
        "display_name": "ВКЛ_СОФТ",
        "column": "products",
        "value": "ВКЛ",
        "ptflo_blng": "SOFT",
    },

    "bk": {
        "display_name": "БК",
        "column": "products",
        "value": "БК",
    },
    "bk_soft": {
        "display_name": "БК_СОФТ",
        "column": "products",
        "value": "БК",
        "ptflo_blng": "SOFT",
    },

    "rb_z_ip": {
        "display_name": "РБ З ИП",
        "column": "products",
        "value": "РБ ЗАЛОГОВЫЙ ИП",
    },
    "rb_z_ip_soft": {
        "display_name": "РБ З ИП(с)",
        "column": "products",
        "value": "РБ ЗАЛОГОВЫЙ ИП (с)",
    },
    "rb_z_too": {
        "display_name": "РБ З ТОО",
        "column": "products",
        "value": "РБ ЗАЛОГОВЫЙ ТОО",
    },

    "rb_bz_ip": {
        "display_name": "РБ БЗ ИП",
        "column": "products",
        "value": "РБ БЗ ИП",
    },
    "rb_bz_too": {
        "display_name": "РБ БЗ ТОО",
        "column": "products",
        "value": "РБ БЗ ТОО",
    },
}


DAILY_ENTITIES = list(DAILY_ENTITY_CONFIG.keys())


def normalize_daily_raw(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    required_cols = [
        "base_ymd",
        "segment1",
        "products",
        "ptflo_blng",
        "od",
        "prosrochka_1",
    ]

    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Нет обязательной колонки в daily raw: {col}")

    df["base_ymd"] = (
        df["base_ymd"]
        .astype(str)
        .str.extract(r"(\d{8})")[0]
    )

    df = df.dropna(subset=["base_ymd"]).copy()

    df["segment1"] = df["segment1"].astype(str).str.strip()
    df["products"] = df["products"].astype(str).str.strip()
    df["ptflo_blng"] = df["ptflo_blng"].astype(str).str.strip().str.upper()

    df["od"] = pd.to_numeric(df["od"], errors="coerce").fillna(0)
    df["prosrochka_1"] = pd.to_numeric(
        df["prosrochka_1"],
        errors="coerce",
    ).fillna(0)

    return df


def filter_daily_entity(df: pd.DataFrame, entity_id: str) -> pd.DataFrame:
    if entity_id not in DAILY_ENTITY_CONFIG:
        raise ValueError(f"Unknown daily entity_id: {entity_id}")

    cfg = DAILY_ENTITY_CONFIG[entity_id]

    filter_col = cfg["column"].lower()
    filter_value = str(cfg["value"]).strip()

    if filter_col not in df.columns:
        raise KeyError(f"Нет колонки для фильтрации: {filter_col}")

    temp = df.loc[
        df[filter_col].astype(str).str.strip() == filter_value
    ].copy()

    if "ptflo_blng" in cfg:
        soft_value = str(cfg["ptflo_blng"]).strip().upper()

        temp = temp.loc[
            temp["ptflo_blng"] == soft_value
        ].copy()

    if temp.empty:
        return pd.DataFrame(
            columns=["base_ymd", "od", "prosrochka_1"]
        )

    result = (
        temp
        .groupby("base_ymd", as_index=False)[["od", "prosrochka_1"]]
        .sum()
        .sort_values("base_ymd")
        .reset_index(drop=True)
    )

    return result


def build_daily_entity_rows(df: pd.DataFrame, entity_id: str) -> list[dict]:
    normalized = normalize_daily_raw(df)
    entity_df = filter_daily_entity(normalized, entity_id)

    rows = []

    for _, row in entity_df.iterrows():
        rows.append(
            {
                "base_ymd": str(row["base_ymd"]),
                "od": float(row["od"]),
                "prosrochka_1": float(row["prosrochka_1"]),
            }
        )

    return rows