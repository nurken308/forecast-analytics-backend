from __future__ import annotations

import numpy as np
import pandas as pd

from service.work_calendar_service import (
    get_shifted_peak_dates,
    is_kz_holiday,
)


# ============================================================
# 1. БАЗОВЫЕ НАСТРОЙКИ
# ============================================================

DATE_COL = "base_ymd"
TARGET_COL = "prosrochka_1"


LEVEL_LIFT = 1.12
AR_ALPHA = 0.38
MATURITY_WEIGHT = 0.15


# Контрольные платежные пики.
PEAK_STRENGTH = {
    2: 1.18,
    5: 1.28,
    10: 1.45,
    15: 1.35,
    20: 1.85,
    25: 1.70,
}


# Ограничение уровня на календарный день после пика.
POST_PEAK_DAY1 = {
    2: 0.93,
    5: 0.93,
    10: 0.93,
    15: 0.93,
    20: 0.92,
    25: 0.93,
}


# Для бизнес-сегментов задолженность в выходные
# не должна существенно снижаться относительно пятницы.
#
# 5 — суббота;
# 6 — воскресенье.
BUSINESS_WEEKEND_FLOOR = {
    5: 0.98,
    6: 0.97,
}

# Верхняя граница, чтобы историческая weekday-сезонность
# не создавала искусственный рост в выходные.
BUSINESS_WEEKEND_CEILING = {
    5: 1.02,
    6: 1.02,
}

SOFT_WEEKEND_PEAK_ENTITIES = {
    "bk_soft",
    "vkl_soft",
}


# Накопление просрочки в SOFT-сегментах,
# когда контрольный пик приходится на пятницу
# или на последний рабочий день перед выходными.
SOFT_WEEKEND_ACCUMULATION = {
    "bk_soft": {
        5: 1.05,  # суббота относительно пятницы
        6: 0.95,  # воскресенье относительно субботы
    },
    "vkl_soft": {
        5: 1.05,
        6: 0.93,
    },
}
# Для Розницы используется обычное снижение в выходные.
RETAIL_WEEKEND_COEFFICIENT = {
    5: 0.97,
    6: 0.95,
}


# Дополнительные структурные параметры.
MID_MONTH_FLOOR = 1.02
END_MONTH_COEFFICIENT = 0.95

GENERAL_HOLIDAY_COEFFICIENT = 0.94
NAURYZ_COEFFICIENT = 0.90
WOMENS_DAY_COEFFICIENT = 0.97

LEVEL_CORRECTION_MIN = 0.85
LEVEL_CORRECTION_MAX = 1.15


# ============================================================
# 2. MATURITY
# ============================================================

MATURITY_CONFIG = {
    "retail": {
        "a": 0.9526,
        "b": -0.5490,
        "mob": 22,
    },

    "bk": {
        "a": 3.8968,
        "b": -0.4736,
        "mob": 13,
    },

    "bk_soft": {
        "a": 3.8968,
        "b": -0.4736,
        "mob": 13,
    },

    "vkl": {
        "a": 0.6997,
        "b": 1.0432,
        "mob": 15,
    },

    "vkl_soft": {
        "a": 0.6997,
        "b": 1.0432,
        "mob": 15,
    },

    "rb_z_ip": {
        "a": 3.8968,
        "b": -0.4736,
        "mob": 13,
    },

    "rb_z_ip_soft": {
        "a": 0.6997,
        "b": 1.0432,
        "mob": 15,
    },

    "rb_z_too": {
        "a": 4.8688,
        "b": -3.3355,
        "mob": 15,
    },

    "rb_bz_ip": {
        "a": 1.1094,
        "b": 1.2738,
        "mob": 15,
    },

    "rb_bz_too": {
        "a": 1.1094,
        "b": 1.2738,
        "mob": 15,
    },
}


# ============================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def safe_float(
    value,
    default: float = 0.0,
) -> float:
    """
    Безопасно преобразует значение в float.
    """

    if value is None:
        return float(default)

    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)

    if not np.isfinite(result):
        return float(default)

    return result


def normalize_entity_id(
    entity_id: str,
) -> str:
    """
    Нормализует идентификатор Daily entity.
    """

    normalized = str(
        entity_id or ""
    ).strip().lower()

    if not normalized:
        raise ValueError(
            "entity_id не может быть пустым."
        )

    return normalized


def normalize_history(
    rows,
) -> pd.DataFrame:
    """
    Преобразует ORM-строки ezmes или список словарей
    в DataFrame:

        base_ymd | prosrochka_1
    """

    data = []

    for row in rows:
        if isinstance(row, dict):
            base_ymd = row.get(
                "base_ymd"
            )

            target = row.get(
                "prosrochka_1"
            )
        else:
            base_ymd = getattr(
                row,
                "base_ymd",
                None,
            )

            target = getattr(
                row,
                "prosrochka_1",
                None,
            )

        base_ymd = str(
            base_ymd or ""
        ).strip()

        if (
            len(base_ymd) != 8
            or not base_ymd.isdigit()
        ):
            continue

        parsed_date = pd.to_datetime(
            base_ymd,
            format="%Y%m%d",
            errors="coerce",
        )

        if pd.isna(parsed_date):
            continue

        data.append(
            {
                DATE_COL: (
                    parsed_date.normalize()
                ),
                TARGET_COL: safe_float(
                    target
                ),
            }
        )

    if not data:
        return pd.DataFrame(
            columns=[
                DATE_COL,
                TARGET_COL,
            ]
        )

    result = pd.DataFrame(
        data
    )

    result = (
        result
        .groupby(
            DATE_COL,
            as_index=False,
        )[TARGET_COL]
        .sum()
        .sort_values(
            DATE_COL
        )
        .reset_index(
            drop=True
        )
    )

    return result


# ============================================================
# 4. MATURITY-ФУНКЦИИ
# ============================================================

def maturity_effect(
    mob: int,
    a: float,
    b: float,
) -> float:
    """
    Risk = A * ln(MOB) + B
    """

    mob = max(
        int(mob),
        1,
    )

    return float(
        a * np.log(mob) + b
    )


def maturity_adjustment(
    entity_id: str,
) -> float:
    """
    Рассчитывает небольшой maturity-сдвиг
    от текущего MOB к следующему MOB.
    """

    entity_id = normalize_entity_id(
        entity_id
    )

    cfg = MATURITY_CONFIG.get(
        entity_id
    )

    if cfg is None:
        return 1.0

    current_effect = maturity_effect(
        mob=cfg["mob"],
        a=cfg["a"],
        b=cfg["b"],
    )

    next_effect = maturity_effect(
        mob=cfg["mob"] + 1,
        a=cfg["a"],
        b=cfg["b"],
    )

    if (
        not np.isfinite(current_effect)
        or current_effect == 0
    ):
        return 1.0

    adjustment = (
        1
        + MATURITY_WEIGHT
        * (
            (
                next_effect
                - current_effect
            )
            / current_effect
        )
    )

    if not np.isfinite(
        adjustment
    ):
        return 1.0

    return float(
        adjustment
    )


# ============================================================
# 5. СЕЗОННОСТЬ
# ============================================================

def build_dom_pattern(
    history: pd.DataFrame,
) -> pd.Series:
    """
    Строит нормированную сезонность
    по дню месяца.
    """

    if history.empty:
        return pd.Series(
            dtype=float
        )

    data = history.copy()

    data["dom"] = (
        data[DATE_COL].dt.day
    )

    dom_mean = data.groupby(
        "dom"
    )[TARGET_COL].mean()

    dom_average = safe_float(
        dom_mean.mean()
    )

    if (
        dom_mean.empty
        or dom_average == 0
    ):
        return pd.Series(
            dtype=float
        )

    trend = dom_mean.rolling(
        window=5,
        center=True,
        min_periods=1,
    ).mean()

    clipped = np.minimum(
        dom_mean,
        trend * 1.08,
    )

    clipped_mean = safe_float(
        clipped.mean()
    )

    if clipped_mean == 0:
        return pd.Series(
            1.0,
            index=clipped.index,
            dtype=float,
        )

    return (
        clipped
        / clipped_mean
    )


def build_weekday_pattern(
    history: pd.DataFrame,
) -> pd.Series:
    """
    Строит нормированную сезонность
    по дням недели.
    """

    if history.empty:
        return pd.Series(
            dtype=float
        )

    data = history.copy()

    data["dow"] = (
        data[DATE_COL]
        .dt.dayofweek
    )

    dow_mean = data.groupby(
        "dow"
    )[TARGET_COL].mean()

    dow_average = safe_float(
        dow_mean.mean()
    )

    if (
        dow_mean.empty
        or dow_average == 0
    ):
        return pd.Series(
            dtype=float
        )

    return (
        dow_mean
        / dow_average
    )


# ============================================================
# 6. BASELINE И ГРАНИЦЫ МЕСЯЦА
# ============================================================

def get_month_bounds(
    last_fact_date: pd.Timestamp,
):
    """
    Возвращает начало и конец месяца последнего факта.
    """

    month_start = (
        last_fact_date
        .replace(day=1)
        .normalize()
    )

    month_end = (
        month_start
        + pd.offsets.MonthEnd(0)
    ).normalize()

    return (
        month_start,
        month_end,
    )


def get_baseline(
    history_before_month: pd.DataFrame,
    all_history: pd.DataFrame,
) -> float:
    """
    Основной baseline:
    последнее значение предыдущего месяца.

    Fallback:
    последний доступный факт.
    """

    if not history_before_month.empty:
        previous_month = (
            history_before_month[
                DATE_COL
            ]
            .dt.to_period("M")
            .max()
        )

        previous_month_rows = (
            history_before_month.loc[
                history_before_month[
                    DATE_COL
                ].dt.to_period("M")
                == previous_month
            ]
            .sort_values(
                DATE_COL
            )
        )

        if not previous_month_rows.empty:
            baseline = safe_float(
                previous_month_rows
                .iloc[-1][TARGET_COL]
            )

            if baseline > 0:
                return baseline

    if not all_history.empty:
        baseline = safe_float(
            all_history
            .sort_values(DATE_COL)
            .iloc[-1][TARGET_COL]
        )

        if baseline > 0:
            return baseline

        fallback = safe_float(
            all_history[
                TARGET_COL
            ].tail(7).mean()
        )

        if fallback > 0:
            return fallback

    raise ValueError(
        "Нет корректных данных "
        "для определения baseline."
    )


# ============================================================
# 7. ПРАЗДНИЧНЫЕ КОЭФФИЦИЕНТЫ
# ============================================================

def is_nauryz_period(
    forecast_date: pd.Timestamp,
) -> bool:
    """
    Специальный период Наурыза:
    21–25 марта.
    """

    return (
        forecast_date.month == 3
        and 21 <= forecast_date.day <= 25
    )


def is_womens_day(
    forecast_date: pd.Timestamp,
) -> bool:
    """
    Международный женский день.
    """

    return (
        forecast_date.month == 3
        and forecast_date.day == 8
    )


def apply_holiday_coefficient(
    forecast_date: pd.Timestamp,
    value: float,
) -> float:
    """
    Применяет праздничный коэффициент.

    Наурыз имеет отдельный более сильный эффект.
    """

    forecast_date = (
        pd.Timestamp(
            forecast_date
        ).normalize()
    )

    if is_nauryz_period(
        forecast_date
    ):
        return (
            value
            * NAURYZ_COEFFICIENT
        )

    if is_womens_day(
        forecast_date
    ):
        return (
            value
            * WOMENS_DAY_COEFFICIENT
        )

    if is_kz_holiday(
        forecast_date
    ):
        return (
            value
            * GENERAL_HOLIDAY_COEFFICIENT
        )

    return value


# ============================================================
# 8. ВЫХОДНЫЕ
# ============================================================


def apply_weekend_logic(
    entity_id: str,
    forecast_date: pd.Timestamp,
    value: float,
    last_friday_value: float | None,
    previous_value: float | None,
    peak_before_weekend: bool,
) -> float:
    """
    Сегментная логика выходных.

    retail:
        обычное снижение.

    Обычные бизнес-сегменты:
        уровень около пятницы.

    bk_soft / vkl_soft:
        если пик приходится на четверг или пятницу,
        в субботу формируется накопление,
        в воскресенье сохраняется большая часть субботнего уровня.
    """

    entity_id = normalize_entity_id(entity_id)

    dow = pd.Timestamp(forecast_date).dayofweek

    if dow not in (5, 6):
        return value

    if entity_id == "retail":
        return (
            value
            * RETAIL_WEEKEND_COEFFICIENT[dow]
        )

    if last_friday_value is None:
        return value

    if (
        entity_id in SOFT_WEEKEND_PEAK_ENTITIES
        and peak_before_weekend
    ):
        accumulation_cfg = (
            SOFT_WEEKEND_ACCUMULATION[
                entity_id
            ]
        )

        if dow == 5:
            return float(
                last_friday_value
                * accumulation_cfg[5]
            )

        if dow == 6:
            reference_value = (
                previous_value
                if previous_value is not None
                else last_friday_value
            )

            return float(
                reference_value
                * accumulation_cfg[6]
            )

    weekend_floor = (
        last_friday_value
        * BUSINESS_WEEKEND_FLOOR[dow]
    )

    weekend_ceiling = (
        last_friday_value
        * BUSINESS_WEEKEND_CEILING[dow]
    )

    return float(
        np.clip(
            value,
            weekend_floor,
            weekend_ceiling,
        )
    )


# ============================================================
# 9. ОСНОВНАЯ МОДЕЛЬ
# ============================================================


def build_daily_model_forecast(
    rows,
    entity_id: str,
) -> pd.DataFrame:
    """
    Строит прогноз на весь месяц последнего доступного факта.

    Возвращает DataFrame:

        period_date
        forecast_value
    """

    entity_id = normalize_entity_id(
        entity_id
    )

    history = normalize_history(
        rows
    )

    if history.empty:
        raise ValueError(
            "Нет истории для построения "
            f"daily forecast: {entity_id}"
        )

    if entity_id not in MATURITY_CONFIG:
        raise ValueError(
            "Нет maturity config для "
            f"daily entity: {entity_id}"
        )

    last_fact_date = (
        history[DATE_COL]
        .max()
        .normalize()
    )

    (
        forecast_month_start,
        forecast_month_end,
    ) = get_month_bounds(
        last_fact_date
    )

    history_before_month = history.loc[
        history[DATE_COL]
        < forecast_month_start
    ].copy()

    baseline = get_baseline(
        history_before_month=(
            history_before_month
        ),
        all_history=history,
    )

    pattern_source = (
        history_before_month
        if not history_before_month.empty
        else history
    )

    dom_ratio = build_dom_pattern(
        pattern_source
    )

    dow_ratio = build_weekday_pattern(
        pattern_source
    )

    maturity_factor = maturity_adjustment(
        entity_id
    )

    # ВАЖНО:
    # передаем entity_id, чтобы bk_soft и vkl_soft
    # использовали отложенный пик.
    shifted_peaks = get_shifted_peak_dates(
        month_start=forecast_month_start,
        segment_id=entity_id,
    )

    actual_peak_date_to_base_day = {
        pd.Timestamp(
            actual_date
        ).normalize(): base_day
        for (
            base_day,
            actual_date,
        ) in shifted_peaks.items()
    }

    shifted_peak_dates = set(
        actual_peak_date_to_base_day.keys()
    )

    forecast_dates = pd.date_range(
        start=forecast_month_start,
        end=forecast_month_end,
        freq="D",
    )

    forecasts: list[float] = []

    # Последнее рассчитанное значение пятницы.
    # Используется для business weekend floor.
    last_friday_value: float | None = None

    for forecast_date in forecast_dates:
        normalized_date = (
            forecast_date.normalize()
        )

        dom = forecast_date.day
        dow = forecast_date.dayofweek

        structural_value = baseline

        structural_value *= (
            LEVEL_LIFT
        )

        structural_value *= (
            maturity_factor
        )

        structural_value *= safe_float(
            dom_ratio.get(
                dom,
                1.0,
            ),
            default=1.0,
        )

        structural_value *= safe_float(
            dow_ratio.get(
                dow,
                1.0,
            ),
            default=1.0,
        )

        # ====================================================
        # ПЛАТЕЖНЫЙ ПИК
        # ====================================================

        if (
            normalized_date
            in actual_peak_date_to_base_day
        ):
            base_peak_day = (
                actual_peak_date_to_base_day[
                    normalized_date
                ]
            )

            peak_strength = (
                PEAK_STRENGTH[
                    base_peak_day
                ]
            )

            structural_value = max(
                structural_value,
                baseline * peak_strength,
            )

        # ====================================================
        # КАЛЕНДАРНЫЙ ДЕНЬ ПОСЛЕ ПИКА
        # ====================================================

        for (
            base_peak_day,
            actual_peak_date,
        ) in shifted_peaks.items():
            actual_peak_date = (
                pd.Timestamp(
                    actual_peak_date
                ).normalize()
            )

            day_after_peak = (
                actual_peak_date
                + pd.Timedelta(days=1)
            )

            if (
                normalized_date
                == day_after_peak
            ):
                structural_value = min(
                    structural_value,
                    baseline
                    * PEAK_STRENGTH[
                        base_peak_day
                    ]
                    * POST_PEAK_DAY1[
                        base_peak_day
                    ],
                )

        # ====================================================
        # ПОДДЕРЖКА УРОВНЯ 5–15
        # ====================================================

        if (
            5 <= dom <= 15
            and normalized_date
            not in shifted_peak_dates
        ):
            structural_value = max(
                structural_value,
                baseline
                * MID_MONTH_FLOOR,
            )

        # ====================================================
        # СНИЖЕНИЕ К КОНЦУ МЕСЯЦА
        # ====================================================

        if (
            dom >= 23
            and normalized_date
            not in shifted_peak_dates
        ):
            structural_value *= (
                END_MONTH_COEFFICIENT
            )

        # ====================================================
        # АВТОРЕГРЕССИЯ
        # ====================================================

        if forecasts:
            forecast_value = (
                AR_ALPHA
                * forecasts[-1]
                + (
                    1 - AR_ALPHA
                )
                * structural_value
            )
        else:
            forecast_value = (
                structural_value
            )

        # ====================================================
        # ПРАЗДНИКИ
        # ====================================================

        forecast_value = (
            apply_holiday_coefficient(
                forecast_date=(
                    normalized_date
                ),
                value=forecast_value,
            )
        )

        # ====================================================
        # ВЫХОДНЫЕ
        # ====================================================
        peak_before_weekend = False

        if entity_id in SOFT_WEEKEND_PEAK_ENTITIES:
            previous_day = (
                normalized_date
                - pd.Timedelta(days=1)
            )

            two_days_before = (
                normalized_date
                - pd.Timedelta(days=2)
            )

            peak_before_weekend = (
                previous_day in shifted_peak_dates
                or two_days_before in shifted_peak_dates
            )
        forecast_value = (
            apply_weekend_logic(
                entity_id=entity_id,
                forecast_date=normalized_date,
                value=forecast_value,
                last_friday_value=last_friday_value,
                previous_value=(
                    forecasts[-1]
                    if forecasts
                    else None
                ),
                peak_before_weekend=(
                    peak_before_weekend
                ),
            )
        )

        if not np.isfinite(
            forecast_value
        ):
            forecast_value = baseline

        forecast_value = max(
            float(forecast_value),
            0.0,
        )

        # Запоминаем финальное рассчитанное
        # значение пятницы.
        if dow == 4:
            last_friday_value = (
                forecast_value
            )

        forecasts.append(
            forecast_value
        )

    forecast_array = np.array(
        forecasts,
        dtype=float,
    )

    # ========================================================
    # ЯКОРЯ НАЧАЛА МЕСЯЦА
    # ========================================================

    if len(forecast_array) > 0:
        forecast_array[0] = (
            baseline
        )

    if len(forecast_array) > 1:
        forecast_array[1] = max(
            forecast_array[1],
            baseline
            * PEAK_STRENGTH[2],
        )

    actual_peak_5 = shifted_peaks.get(
        5
    )

    if actual_peak_5 is not None:
        index_5 = (
            pd.Timestamp(
                actual_peak_5
            ).day
            - 1
        )

        if (
            0
            <= index_5
            < len(forecast_array)
        ):
            forecast_array[
                index_5
            ] = max(
                forecast_array[
                    index_5
                ],
                baseline * 1.20,
            )

    forecast_df = pd.DataFrame(
        {
            "period_date": [
                forecast_date.strftime(
                    "%Y-%m-%d"
                )
                for forecast_date
                in forecast_dates
            ],
            "forecast_value": (
                np.round(
                    forecast_array,
                    2,
                )
            ),
        }
    )

    # ========================================================
    # КОРРЕКТИРОВКА ПО ФАКТАМ ТЕКУЩЕГО МЕСЯЦА
    # ========================================================

    current_month_fact = history.loc[
        (
            history[DATE_COL]
            >= forecast_month_start
        )
        & (
            history[DATE_COL]
            <= last_fact_date
        )
    ][
        [
            DATE_COL,
            TARGET_COL,
        ]
    ].copy()

    if not current_month_fact.empty:
        comparison = (
            forecast_df.copy()
        )

        comparison[
            "date_join"
        ] = pd.to_datetime(
            comparison[
                "period_date"
            ],
            errors="coerce",
        )

        comparison = comparison.merge(
            current_month_fact.rename(
                columns={
                    DATE_COL: (
                        "date_join"
                    ),
                    TARGET_COL: (
                        "fact_value"
                    ),
                }
            ),
            on="date_join",
            how="inner",
        )

        forecast_mean = safe_float(
            comparison[
                "forecast_value"
            ].mean()
        )

        fact_mean = safe_float(
            comparison[
                "fact_value"
            ].mean()
        )

        if (
            not comparison.empty
            and forecast_mean != 0
            and fact_mean > 0
        ):
            correction = (
                fact_mean
                / forecast_mean
            )

            correction = float(
                np.clip(
                    correction,
                    LEVEL_CORRECTION_MIN,
                    LEVEL_CORRECTION_MAX,
                )
            )

            forecast_df[
                "forecast_value"
            ] = (
                forecast_df[
                    "forecast_value"
                ]
                * correction
            ).round(2)

    return forecast_df