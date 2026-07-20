from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.ezmes_repository import EzmesRepository
from repositories.forecast_repository import ForecastRepository
from service.daily_entity_service import build_daily_entity_rows
from service.daily_model_service import build_daily_model_forecast
from service.oracle_sql_service import load_oracle_daily_raw
from service.work_calendar_service import (
    get_recalculation_dates,
    get_shifted_peak_dates,
)


DAILY_FORECAST_TYPE = "daily"
DAILY_MODEL_NAME = "Daily structural forecast"


# ============================================================
# 1. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def ymd_to_date(base_ymd: str):
    return datetime.strptime(
        str(base_ymd),
        "%Y%m%d",
    ).date()


def date_to_period(dt) -> str:
    return dt.strftime("%Y-%m-%d")


def period_to_ymd(period: str) -> str:
    return datetime.strptime(
        period,
        "%Y-%m-%d",
    ).strftime("%Y%m%d")


def safe_float(value) -> float:
    if value is None:
        return 0.0

    return float(value)


def optional_float(value):
    if value is None:
        return None

    return float(value)


def get_processing_date(base_ymd: str):
    """
    Scheduler загружает base_ymd за предыдущий календарный день.

    Поэтому дата выполнения процесса:

        processing_date = base_ymd + 1 календарный день
    """

    return (
        ymd_to_date(base_ymd)
        + timedelta(days=1)
    )


def get_run_month(run):
    """
    Возвращает месяц первого значения run
    в формате YYYY-MM.
    """

    if run is None or not run.values:
        return None

    first_period = min(
        value.period_month
        for value in run.values
    )

    return first_period[:7]


def serialize_existing_value(value) -> dict:
    """
    Копирует старое значение без изменений.

    Используется, чтобы сохранить:
    - старый прогноз;
    - факт;
    - ошибку;
    - статус.
    """

    return {
        "period_month": value.period_month,
        "forecast_value": safe_float(
            value.forecast_value
        ),
        "fact_value": optional_float(
            value.fact_value
        ),
        "abs_error": optional_float(
            value.abs_error
        ),
        "pct_error": optional_float(
            value.pct_error
        ),
        "status": value.status,
    }


async def archive_existing_current_runs(
    segment_id: str,
    session: AsyncSession,
):
    """
    Архивирует все старые current/active run
    по выбранному Daily entity.

    Защищает от появления нескольких current
    при ручном вызове /build.
    """

    repo = ForecastRepository(
        session
    )

    runs = await repo.get_history(
        segment_id=segment_id,
        forecast_type=DAILY_FORECAST_TYPE,
    )

    archived_ids = []

    for run in runs:
        if run.status in (
            "current",
            "active",
        ):
            await repo.update_run_status(
                run_id=run.id,
                status="archived",
            )

            archived_ids.append(
                run.id
            )

    return archived_ids


# ============================================================
# 2. ORACLE → EZMES
# ============================================================

async def refresh_daily_fact_from_oracle_by_base_ymd(
    segment_id: str,
    base_ymd: str,
    session: AsyncSession,
):
    """
    Загружает весь Daily raw за дату из Oracle,
    выделяет нужную сущность и сохраняет ее в ezmes.
    """

    raw_df = load_oracle_daily_raw(
        base_ymd=base_ymd,
    )

    rows = build_daily_entity_rows(
        df=raw_df,
        entity_id=segment_id,
    )

    if not rows:
        return {
            "status": "not_found",
            "segment_id": segment_id,
            "base_ymd": base_ymd,
            "message": (
                "Oracle daily raw loaded, "
                "but entity rows are empty"
            ),
        }

    ezmes_repo = EzmesRepository(
        session
    )

    result = await ezmes_repo.upsert_history(
        segment_id=segment_id,
        rows=rows,
    )

    return {
        "status": "loaded",
        "segment_id": segment_id,
        "base_ymd": base_ymd,
        "rows": rows,
        "upsert_result": result,
    }


async def get_daily_fact_by_period(
    segment_id: str,
    period_date: str,
    session: AsyncSession,
):
    """
    Возвращает факт Daily entity из ezmes
    за указанную дату YYYY-MM-DD.
    """

    base_ymd = period_to_ymd(
        period_date
    )

    repo = EzmesRepository(
        session
    )

    row = await repo.get_by_base_ymd(
        segment_id=segment_id,
        base_ymd=base_ymd,
    )

    if row is None:
        return None

    return safe_float(
        row.prosrochka_1
    )

def build_daily_fact_map(rows) -> dict[str, float]:
    """
    Формирует словарь фактов из строк ezmes:

        {
            "2026-07-01": 12345.67,
            "2026-07-02": 12500.10,
        }
    """

    fact_map: dict[str, float] = {}

    for row in rows:
        if isinstance(row, dict):
            base_ymd = row.get("base_ymd")
            fact_value = row.get("prosrochka_1")
        else:
            base_ymd = getattr(
                row,
                "base_ymd",
                None,
            )

            fact_value = getattr(
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

        try:
            period_date = datetime.strptime(
                base_ymd,
                "%Y%m%d",
            ).strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            continue

        if fact_value is None:
            continue

        fact_map[period_date] = safe_float(
            fact_value
        )

    return fact_map
# ============================================================
# 3. ПОСТРОЕНИЕ НОВОГО DAILY RUN
# ============================================================

async def create_daily_run_from_model(
    segment_id: str,
    session: AsyncSession,
    parent_run_id: int | None = None,
    status: str = "current",
):
    """
    Строит модель на основе всей истории entity в ezmes
    и создает новый forecast_run.

    Для уже доступных дат сразу записывает:
    - fact_value;
    - abs_error;
    - pct_error;
    - status = fact_available.
    """

    ezmes_repo = EzmesRepository(
        session
    )

    forecast_repo = ForecastRepository(
        session
    )

    rows = await ezmes_repo.get_all(
        segment_id
    )

    if not rows:
        raise ValueError(
            "Нет данных ezmes для "
            f"segment_id={segment_id}"
        )

    forecast_df = build_daily_model_forecast(
        rows=rows,
        entity_id=segment_id,
    )

    if (
        forecast_df is None
        or forecast_df.empty
    ):
        raise ValueError(
            "Модель не сформировала прогноз "
            f"для segment_id={segment_id}"
        )

    fact_map = build_daily_fact_map(
        rows
    )

    values = []

    fact_values_count = 0

    for _, row in forecast_df.iterrows():
        period_date = str(
            row["period_date"]
        )

        forecast_value = round(
            float(
                row["forecast_value"]
            ),
            2,
        )

        fact_value = fact_map.get(
            period_date
        )

        if fact_value is not None:
            fact_value = round(
                float(fact_value),
                2,
            )

            abs_error = round(
                fact_value
                - forecast_value,
                2,
            )

            if forecast_value != 0:
                pct_error = round(
                    (
                        abs_error
                        / forecast_value
                    )
                    * 100,
                    4,
                )
            else:
                pct_error = None

            value_status = (
                "fact_available"
            )

            fact_values_count += 1
        else:
            abs_error = None
            pct_error = None
            value_status = "planned"

        values.append(
            {
                "period_month": period_date,
                "forecast_value": forecast_value,
                "fact_value": fact_value,
                "abs_error": abs_error,
                "pct_error": pct_error,
                "status": value_status,
            }
        )

    run = await forecast_repo.create_run(
        forecast_type=DAILY_FORECAST_TYPE,
        segment_id=segment_id,
        model_name=DAILY_MODEL_NAME,
        values=values,
        parent_run_id=parent_run_id,
        status=status,
    )

    return {
        "run": run,
        "values": values,
        "forecast_df": forecast_df,
        "fact_values_count": (
            fact_values_count
        ),
    }

async def build_daily_forecast(
    segment_id: str,
    session: AsyncSession,
):
    """
    Ручное первоначальное построение.

    Перед созданием нового current архивирует
    старые current/active run.
    """

    archived_run_ids = (
        await archive_existing_current_runs(
            segment_id=segment_id,
            session=session,
        )
    )

    created = await create_daily_run_from_model(
        segment_id=segment_id,
        session=session,
        parent_run_id=None,
        status="current",
    )

    run = created["run"]
    values = created["values"]
    fact_values_count = created[
    "fact_values_count"
    ]

    return {
        "status": "success",
        "message": (
            "Daily structural forecast created"
        ),
        "segment_id": segment_id,
        "run_id": run.id,
        "forecast_type": DAILY_FORECAST_TYPE,
        "from_date": values[0][
            "period_month"
        ],
        "to_date": values[-1][
            "period_month"
        ],
        "values_count": len(values),
        "archived_run_ids": (
            archived_run_ids
        ),
        "fact_values_count": fact_values_count,
    }


# ============================================================
# 4. ЧТЕНИЕ CURRENT / HISTORY
# ============================================================

async def get_current_daily_forecast(
    segment_id: str,
    session: AsyncSession,
):
    repo = ForecastRepository(
        session
    )

    return await repo.get_latest_current_run(
        segment_id=segment_id,
        forecast_type=DAILY_FORECAST_TYPE,
    )


async def get_daily_forecast_history(
    segment_id: str,
    session: AsyncSession,
):
    repo = ForecastRepository(
        session
    )

    return await repo.get_history(
        segment_id=segment_id,
        forecast_type=DAILY_FORECAST_TYPE,
    )


# ============================================================
# 5. ЧАСТИЧНЫЙ ПЕРЕСЧЕТ ПОСЛЕ ПИКА
# ============================================================

async def recalculate_daily_forecast_from_date(
    current_run,
    segment_id: str,
    recalculation_period: str,
    trigger_fact_period: str,
    session: AsyncSession,
):
    """
    Создает новый current run после контрольного пика.

    До recalculation_period:
        старый прогноз, факт, ошибки
        и статус сохраняются.

    С recalculation_period:
        используется новый структурный прогноз,
        дополнительно скорректированный по отклонению
        факта от старого прогноза
        на trigger_fact_period.
    """

    ezmes_repo = EzmesRepository(
        session
    )

    forecast_repo = ForecastRepository(
        session
    )

    history_rows = await ezmes_repo.get_all(
        segment_id
    )

    forecast_df = build_daily_model_forecast(
        rows=history_rows,
        entity_id=segment_id,
    )

    if (
        forecast_df is None
        or forecast_df.empty
    ):
        raise ValueError(
            "Модель не сформировала пересчет "
            f"для segment_id={segment_id}"
        )

    new_forecast_map = {
        str(row["period_date"]): round(
            float(
                row["forecast_value"]
            ),
            2,
        )
        for _, row in forecast_df.iterrows()
    }

    old_value_map = {
        value.period_month: value
        for value in current_run.values
    }

    # --------------------------------------------------------
    # КОРРЕКТИРОВКА ПО ФАКТУ ПИКОВОГО ДНЯ
    # --------------------------------------------------------

    peak_correction = 1.0
    trigger_old_forecast = None
    trigger_actual_fact = None

    trigger_value = old_value_map.get(
        trigger_fact_period
    )

    if (
        trigger_value is not None
        and trigger_value.forecast_value
        is not None
    ):
        trigger_old_forecast = float(
            trigger_value.forecast_value
        )

        # Сначала берем факт из текущего run.
        if trigger_value.fact_value is not None:
            trigger_actual_fact = float(
                trigger_value.fact_value
            )

        # Если в forecast_values факта нет,
        # берем его напрямую из ezmes.
        if trigger_actual_fact is None:
            trigger_actual_fact = (
                await get_daily_fact_by_period(
                    segment_id=segment_id,
                    period_date=(
                        trigger_fact_period
                    ),
                    session=session,
                )
            )

        if (
            trigger_actual_fact is not None
            and trigger_old_forecast != 0
        ):
            raw_correction = (
                trigger_actual_fact
                / trigger_old_forecast
            )

            peak_correction = float(
                max(
                    0.85,
                    min(
                        1.15,
                        raw_correction,
                    ),
                )
            )

    # --------------------------------------------------------
    # КОРРЕКТИРУЕМ ТОЛЬКО БУДУЩИЕ ДАТЫ
    # --------------------------------------------------------

    for period in list(
        new_forecast_map.keys()
    ):
        if period >= recalculation_period:
            new_forecast_map[
                period
            ] = round(
                new_forecast_map[
                    period
                ]
                * peak_correction,
                2,
            )

    all_periods = sorted(
        set(
            old_value_map.keys()
        )
        | set(
            new_forecast_map.keys()
        )
    )

    merged_values = []

    fact_map = build_daily_fact_map(
        history_rows
    )

    for period in all_periods:
        old_value = old_value_map.get(
            period
        )

        new_forecast_value = (
            new_forecast_map.get(
                period
            )
        )

        # Для прошлой части сохраняем именно
        # старый прогноз, чтобы не переписывать историю.
        if old_value is not None:
            forecast_value = round(
                safe_float(
                    old_value.forecast_value
                ),
                2,
            )
        elif new_forecast_value is not None:
            forecast_value = round(
                float(new_forecast_value),
                2,
            )
        else:
            continue

        # Факт берём из полной истории ezmes.
        fact_value = fact_map.get(
            period
        )

        if fact_value is not None:
            fact_value = round(
                float(fact_value),
                2,
            )

            abs_error = round(
                fact_value - forecast_value,
                2,
            )

            if forecast_value != 0:
                pct_error = round(
                    (
                        abs_error
                        / forecast_value
                    )
                    * 100,
                    4,
                )
            else:
                pct_error = None

            merged_values.append(
                {
                    "period_month": period,
                    "forecast_value": (
                        forecast_value
                    ),
                    "fact_value": fact_value,
                    "abs_error": abs_error,
                    "pct_error": pct_error,
                    "status": (
                        "fact_available"
                    ),
                }
            )

            continue

        # Прошлая дата без факта:
        # сохраняем существующую строку.
        if (
            period < recalculation_period
            and old_value is not None
        ):
            merged_values.append(
                serialize_existing_value(
                    old_value
                )
            )

            continue

        # Будущая часть:
        # используем новый пересчитанный прогноз.
        if (
            period >= recalculation_period
            and new_forecast_value is not None
        ):
            merged_values.append(
                {
                    "period_month": period,
                    "forecast_value": round(
                        float(
                            new_forecast_value
                        ),
                        2,
                    ),
                    "fact_value": None,
                    "abs_error": None,
                    "pct_error": None,
                    "status": "planned",
                }
            )

            continue

        # Страховочный fallback.
        if old_value is not None:
            merged_values.append(
                serialize_existing_value(
                    old_value
                )
            )
    await forecast_repo.update_run_status(
        run_id=current_run.id,
        status="recalculated",
    )

    new_run = await forecast_repo.create_run(
        forecast_type=DAILY_FORECAST_TYPE,
        segment_id=segment_id,
        model_name=DAILY_MODEL_NAME,
        values=merged_values,
        parent_run_id=current_run.id,
        status="current",
    )

    return {
        "old_run_id": current_run.id,
        "new_run_id": new_run.id,
        "recalculation_period": (
            recalculation_period
        ),
        "trigger_fact_period": (
            trigger_fact_period
        ),
        "trigger_old_forecast": (
            round(
                trigger_old_forecast,
                2,
            )
            if trigger_old_forecast
            is not None
            else None
        ),
        "trigger_actual_fact": (
            round(
                trigger_actual_fact,
                2,
            )
            if trigger_actual_fact
            is not None
            else None
        ),
        "peak_correction": round(
            peak_correction,
            6,
        ),
        "values_count": len(
            merged_values
        ),
    }
def calculate_manual_level_correction(
    current_run,
    fact_map: dict[str, float],
    fact_period: str,
    lookback_observations: int = 5,
) -> dict:
    """
    Рассчитывает устойчивую корректировку уровня
    для ручного пересчёта.

    Использует медиану fact / forecast
    по последним доступным фактическим дням.
    """

    available_rows = []

    for value in current_run.values:
        period = value.period_month

        if period > fact_period:
            continue

        fact_value = fact_map.get(period)

        if (
            fact_value is None
            or value.forecast_value is None
        ):
            continue

        forecast_value = float(
            value.forecast_value
        )

        if forecast_value <= 0:
            continue

        available_rows.append(
            {
                "period": period,
                "forecast": forecast_value,
                "fact": float(fact_value),
                "ratio": (
                    float(fact_value)
                    / forecast_value
                ),
            }
        )

    available_rows = sorted(
        available_rows,
        key=lambda item: item["period"],
    )

    recent_rows = available_rows[
        -lookback_observations:
    ]

    if not recent_rows:
        return {
            "correction": 1.0,
            "raw_correction": 1.0,
            "rows_count": 0,
            "periods": [],
            "ratios": [],
        }

    ratios = [
        row["ratio"]
        for row in recent_rows
    ]

    raw_correction = float(
        pd.Series(ratios).median()
    )

    # Для ручного пересчёта разрешаем
    # более широкий диапазон, чем ±15%.
    correction = float(
        max(
            0.65,
            min(
                1.35,
                raw_correction,
            ),
        )
    )

    return {
        "correction": correction,
        "raw_correction": raw_correction,
        "rows_count": len(recent_rows),
        "periods": [
            row["period"]
            for row in recent_rows
        ],
        "ratios": [
            round(row["ratio"], 6)
            for row in recent_rows
        ],
    }
async def recalculate_daily_forecast_manual_from_date(
    current_run,
    segment_id: str,
    recalculation_period: str,
    fact_period: str,
    session: AsyncSession,
):
    """
    Ручной пересчёт будущей части прогноза.

    Корректировка уровня рассчитывается
    по последним фактическим дням,
    а не по одному пиковому дню.
    """

    ezmes_repo = EzmesRepository(
        session
    )

    forecast_repo = ForecastRepository(
        session
    )

    history_rows = await ezmes_repo.get_all(
        segment_id
    )

    forecast_df = build_daily_model_forecast(
        rows=history_rows,
        entity_id=segment_id,
    )

    if (
        forecast_df is None
        or forecast_df.empty
    ):
        raise ValueError(
            "Модель не сформировала ручной пересчёт "
            f"для segment_id={segment_id}"
        )

    fact_map = build_daily_fact_map(
        history_rows
    )

    correction_result = (
        calculate_manual_level_correction(
            current_run=current_run,
            fact_map=fact_map,
            fact_period=fact_period,
            lookback_observations=5,
        )
    )

    level_correction = correction_result[
        "correction"
    ]

    new_forecast_map = {
        str(row["period_date"]): round(
            float(row["forecast_value"]),
            2,
        )
        for _, row in forecast_df.iterrows()
    }

    for period in list(
        new_forecast_map.keys()
    ):
        if period >= recalculation_period:
            new_forecast_map[period] = round(
                new_forecast_map[period]
                * level_correction,
                2,
            )

    old_value_map = {
        value.period_month: value
        for value in current_run.values
    }

    all_periods = sorted(
        set(old_value_map.keys())
        | set(new_forecast_map.keys())
    )

    merged_values = []

    for period in all_periods:
        old_value = old_value_map.get(
            period
        )

        new_forecast_value = (
            new_forecast_map.get(period)
        )

        # Историческая часть:
        # сохраняем прежний прогноз.
        if (
            period < recalculation_period
            and old_value is not None
        ):
            forecast_value = round(
                safe_float(
                    old_value.forecast_value
                ),
                2,
            )
        elif new_forecast_value is not None:
            forecast_value = round(
                float(new_forecast_value),
                2,
            )
        elif old_value is not None:
            forecast_value = round(
                safe_float(
                    old_value.forecast_value
                ),
                2,
            )
        else:
            continue

        fact_value = fact_map.get(
            period
        )

        if fact_value is not None:
            fact_value = round(
                float(fact_value),
                2,
            )

            abs_error = round(
                fact_value - forecast_value,
                2,
            )

            pct_error = (
                round(
                    (
                        abs_error
                        / forecast_value
                    )
                    * 100,
                    4,
                )
                if forecast_value != 0
                else None
            )

            merged_values.append(
                {
                    "period_month": period,
                    "forecast_value": forecast_value,
                    "fact_value": fact_value,
                    "abs_error": abs_error,
                    "pct_error": pct_error,
                    "status": "fact_available",
                }
            )

            continue

        merged_values.append(
            {
                "period_month": period,
                "forecast_value": forecast_value,
                "fact_value": None,
                "abs_error": None,
                "pct_error": None,
                "status": "planned",
            }
        )

    await forecast_repo.update_run_status(
        run_id=current_run.id,
        status="recalculated",
    )

    new_run = await forecast_repo.create_run(
        forecast_type=DAILY_FORECAST_TYPE,
        segment_id=segment_id,
        model_name=DAILY_MODEL_NAME,
        values=merged_values,
        parent_run_id=current_run.id,
        status="current",
    )

    return {
        "old_run_id": current_run.id,
        "new_run_id": new_run.id,
        "recalculation_period": (
            recalculation_period
        ),
        "fact_period": fact_period,
        "level_correction": round(
            level_correction,
            6,
        ),
        "raw_level_correction": round(
            correction_result[
                "raw_correction"
            ],
            6,
        ),
        "correction_rows_count": (
            correction_result[
                "rows_count"
            ]
        ),
        "correction_periods": (
            correction_result[
                "periods"
            ]
        ),
        "correction_ratios": (
            correction_result[
                "ratios"
            ]
        ),
        "values_count": len(
            merged_values
        ),
    }
async def force_recalculate_daily_forecast(
    segment_id: str,
    base_ymd: str,
    session: AsyncSession,
):
    """
    Принудительный частичный пересчёт Daily forecast.

    До следующего дня после base_ymd:
        сохраняются исторические прогнозы;
        факты подтягиваются из ezmes.

    Начиная со следующего дня:
        используется новый структурный прогноз.

    Плановый календарь пересчётов по пикам
    при этом не изменяется.
    """

    forecast_repo = ForecastRepository(
        session
    )

    current_run = (
        await forecast_repo.get_latest_current_run(
            segment_id=segment_id,
            forecast_type=DAILY_FORECAST_TYPE,
        )
    )

    if current_run is None:
        raise ValueError(
            "Current daily forecast not found "
            f"for segment_id={segment_id}"
        )

    fact_date = ymd_to_date(
        base_ymd
    )

    fact_period = date_to_period(
        fact_date
    )

    recalculation_date = (
        fact_date
        + timedelta(days=1)
    )

    recalculation_period = date_to_period(
        recalculation_date
    )

    result = (
    await recalculate_daily_forecast_manual_from_date(
        current_run=current_run,
        segment_id=segment_id,
        recalculation_period=recalculation_period,
        fact_period=fact_period,
        session=session,
    )
)

    return {
        "status": "success",
        "action": "force_recalculated",
        "message": (
            "Daily forecast manually recalculated."
        ),
        "segment_id": segment_id,
        "base_ymd": base_ymd,
        "fact_period": fact_period,
        "recalculation_period": (
            recalculation_period
        ),
        "recalculation": result,
    }

# ============================================================
# 6. DAILY LIFECYCLE
# ============================================================

async def auto_update_daily_forecast(
    segment_id: str,
    base_ymd: str,
    session: AsyncSession,
):
    """
    Daily lifecycle.

    Каждый день:
    1. Загружает факт из Oracle.
    2. Сохраняет факт в ezmes.
    3. Обновляет факт/ошибку в текущем run.

    Новый run создается только:
    - если current отсутствует;
    - если начался новый месяц;
    - если наступила дата пересчета после пика.

    Стандартная логика пика:
    - базовая дата переносится
      на первый рабочий день;
    - следующий рабочий день —
      доступность факта;
    - еще следующий рабочий день —
      пересчет.

    Для bk_soft и vkl_soft:
    - если базовый пик попал
      на выходной или праздник,
      пик переносится на второй рабочий день;
    - даты факта и пересчета
      считаются уже от этого SOFT-пика.
    """

    oracle_result = (
        await refresh_daily_fact_from_oracle_by_base_ymd(
            segment_id=segment_id,
            base_ymd=base_ymd,
            session=session,
        )
    )

    if oracle_result["status"] != "loaded":
        return oracle_result

    forecast_repo = ForecastRepository(
        session
    )

    current_run = (
        await forecast_repo.get_latest_current_run(
            segment_id=segment_id,
            forecast_type=DAILY_FORECAST_TYPE,
        )
    )

    # --------------------------------------------------------
    # CURRENT отсутствует
    # --------------------------------------------------------

    if current_run is None:
        created = (
            await create_daily_run_from_model(
                segment_id=segment_id,
                session=session,
                parent_run_id=None,
                status="current",
            )
        )

        run = created["run"]
        values = created["values"]

        return {
            "status": "success",
            "action": "created",
            "message": (
                "Daily fact loaded. "
                "Current daily run was missing, "
                "new run created."
            ),
            "segment_id": segment_id,
            "base_ymd": base_ymd,
            "oracle_result": oracle_result,
            "created": {
                "run_id": run.id,
                "from_date": values[0][
                    "period_month"
                ],
                "to_date": values[-1][
                    "period_month"
                ],
                "values_count": len(
                    values
                ),
            },
        }

    base_date = ymd_to_date(
        base_ymd
    )

    fact_period = date_to_period(
        base_date
    )

    processing_date = get_processing_date(
        base_ymd
    )

    processing_period = date_to_period(
        processing_date
    )

    current_run_month = get_run_month(
        current_run
    )

    fact_month = fact_period[:7]

    # --------------------------------------------------------
    # НАЧАЛСЯ НОВЫЙ МЕСЯЦ
    # --------------------------------------------------------

    if (
        current_run_month is not None
        and current_run_month != fact_month
    ):
        await forecast_repo.update_run_status(
            run_id=current_run.id,
            status="completed",
        )

        created = (
            await create_daily_run_from_model(
                segment_id=segment_id,
                session=session,
                parent_run_id=current_run.id,
                status="current",
            )
        )

        new_run = created["run"]
        values = created["values"]

        first_fact_value = (
            await get_daily_fact_by_period(
                segment_id=segment_id,
                period_date=fact_period,
                session=session,
            )
        )

        first_updated_value = None

        if first_fact_value is not None:
            first_updated_value = (
                await forecast_repo.update_fact_value(
                    run_id=new_run.id,
                    period_month=fact_period,
                    fact_value=(
                        first_fact_value
                    ),
                )
            )

        return {
            "status": "success",
            "action": "new_month",
            "message": (
                "Previous daily run completed. "
                "New monthly daily run created."
            ),
            "segment_id": segment_id,
            "base_ymd": base_ymd,
            "old_run_id": current_run.id,
            "new_run_id": new_run.id,
            "from_date": values[0][
                "period_month"
            ],
            "to_date": values[-1][
                "period_month"
            ],
            "first_fact_period": (
                fact_period
            ),
            "first_fact_updated": (
                first_updated_value
                is not None
            ),
            "oracle_result": oracle_result,
        }

    # --------------------------------------------------------
    # ЗАПИСЫВАЕМ ФАКТ В CURRENT RUN
    # --------------------------------------------------------

    target_value = None

    for value in current_run.values:
        if (
            value.period_month
            == fact_period
        ):
            target_value = value
            break

    updated_value = None

    if target_value is not None:
        fact_value = (
            await get_daily_fact_by_period(
                segment_id=segment_id,
                period_date=fact_period,
                session=session,
            )
        )

        if fact_value is not None:
            updated_value = (
                await forecast_repo.update_fact_value(
                    run_id=current_run.id,
                    period_month=fact_period,
                    fact_value=fact_value,
                )
            )

    # --------------------------------------------------------
    # ПРОВЕРКА ДАТЫ ПЕРЕСЧЕТА
    # --------------------------------------------------------

    processing_month_start = (
        pd.Timestamp(
            processing_date
        )
        .replace(day=1)
        .normalize()
    )

    # ВАЖНО:
    # segment_id передается в обе функции.
    #
    # Поэтому bk_soft и vkl_soft используют
    # собственную отложенную дату пика.
    recalculation_dates = (
        get_recalculation_dates(
            month_start=(
                processing_month_start
            ),
            segment_id=segment_id,
        )
    )

    shifted_peak_dates = (
        get_shifted_peak_dates(
            month_start=(
                processing_month_start
            ),
            segment_id=segment_id,
        )
    )

    # Определяем, какому конкретному пику
    # соответствует сегодняшняя дата пересчета.
    triggered_base_peak_day = None

    for (
        base_peak_day,
        recalculation_date,
    ) in recalculation_dates.items():
        recalculation_date = (
            pd.Timestamp(
                recalculation_date
            ).date()
        )

        if (
            recalculation_date
            == processing_date
        ):
            triggered_base_peak_day = (
                base_peak_day
            )

            break

    is_recalculation_day = (
        triggered_base_peak_day
        is not None
    )

    trigger_peak_period = None

    if is_recalculation_day:
        actual_peak_date = (
            shifted_peak_dates.get(
                triggered_base_peak_day
            )
        )

        if actual_peak_date is None:
            raise ValueError(
                "Не найдена фактическая дата пика "
                f"для segment_id={segment_id}, "
                "base_peak_day="
                f"{triggered_base_peak_day}"
            )

        trigger_peak_period = (
            pd.Timestamp(
                actual_peak_date
            ).strftime(
                "%Y-%m-%d"
            )
        )

    if not is_recalculation_day:
        # --------------------------------------------------------
        # АВТОМАТИЧЕСКАЯ КОРРЕКТИРОВКА УРОВНЯ
        # --------------------------------------------------------

        ezmes_repo = EzmesRepository(
            session
        )

        history_rows = await ezmes_repo.get_all(
            segment_id
        )

        fact_map = build_daily_fact_map(
            history_rows
        )

        correction_result = (
            calculate_manual_level_correction(
                current_run=current_run,
                fact_map=fact_map,
                fact_period=fact_period,
                lookback_observations=5,
            )
        )

        correction_rows_count = (
            correction_result["rows_count"]
        )

        raw_level_correction = float(
            correction_result[
                "raw_correction"
            ]
        )

        level_deviation = abs(
            raw_level_correction - 1.0
        )

        should_recalculate_level = (
            correction_rows_count >= 5
            and level_deviation >= 0.05
        )

        if should_recalculate_level:
            adaptive_result = (
                await recalculate_daily_forecast_manual_from_date(
                    current_run=current_run,
                    segment_id=segment_id,
                    recalculation_period=(
                        processing_period
                    ),
                    fact_period=fact_period,
                    session=session,
                )
            )

            return {
                "status": "success",
                "action": (
                    "adaptive_recalculated"
                ),
                "message": (
                    "Daily fact loaded. "
                    "Forecast level automatically "
                    "adjusted using the last "
                    "5 available facts."
                ),
                "segment_id": segment_id,
                "base_ymd": base_ymd,
                "fact_period": fact_period,
                "processing_period": (
                    processing_period
                ),
                "fact_updated": (
                    updated_value is not None
                ),
                "adaptive_recalculation": (
                    adaptive_result
                ),
                "correction_check": {
                    "rows_count": (
                        correction_rows_count
                    ),
                    "raw_level_correction": round(
                        raw_level_correction,
                        6,
                    ),
                    "level_deviation_pct": round(
                        level_deviation * 100,
                        2,
                    ),
                    "threshold_pct": 5.0,
                    "lookback_observations": 5,
                    "periods": correction_result[
                        "periods"
                    ],
                    "ratios": correction_result[
                        "ratios"
                    ],
                },
                "oracle_result": oracle_result,
            }

        return {
            "status": "success",
            "action": "fact_updated",
            "message": (
                "Daily fact loaded. "
                "Automatic level correction "
                "was not required."
            ),
            "segment_id": segment_id,
            "run_id": current_run.id,
            "base_ymd": base_ymd,
            "fact_period": fact_period,
            "processing_period": (
                processing_period
            ),
            "fact_updated": (
                updated_value is not None
            ),
            "correction_check": {
                "rows_count": (
                    correction_rows_count
                ),
                "raw_level_correction": round(
                    raw_level_correction,
                    6,
                ),
                "level_deviation_pct": round(
                    level_deviation * 100,
                    2,
                ),
                "threshold_pct": 5.0,
                "lookback_observations": 5,
                "periods": correction_result[
                    "periods"
                ],
                "ratios": correction_result[
                    "ratios"
                ],
            },
            "oracle_result": oracle_result,
        }

    # --------------------------------------------------------
    # ЧАСТИЧНЫЙ ПЕРЕСЧЕТ
    # --------------------------------------------------------

    recalculation_result = (
        await recalculate_daily_forecast_from_date(
            current_run=current_run,
            segment_id=segment_id,
            recalculation_period=(
                processing_period
            ),
            trigger_fact_period=(
                trigger_peak_period
            ),
            session=session,
        )
    )

    return {
        "status": "success",
        "action": "recalculated",
        "message": (
            "Daily forecast partially recalculated "
            "after payment peak."
        ),
        "segment_id": segment_id,
        "base_ymd": base_ymd,
        "fact_period": fact_period,
        "processing_period": (
            processing_period
        ),
        "fact_updated": (
            updated_value is not None
        ),
        "recalculation": (
            recalculation_result
        ),
        "oracle_result": oracle_result,
        "triggered_base_peak_day": (
            triggered_base_peak_day
        ),
        "trigger_peak_period": (
            trigger_peak_period
        ),
    }