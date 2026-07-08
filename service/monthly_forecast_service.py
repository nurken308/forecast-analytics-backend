from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from repositories.forecast_repository import ForecastRepository
from repositories.ezmes_repository import EzmesRepository
from service.forecast_lifecycle_service import ForecastLifecycleService
from service.oracle_sql_service import load_oracle_pivot
from service.calendar_service import CalendarService, next_check_time, period_to_base_ymd


def next_months_from_base(base_ymd: str, horizon: int = 3):
    base_date = datetime.strptime(base_ymd, "%Y%m%d")
    return [
        (base_date + relativedelta(months=i)).strftime("%Y-%m")
        for i in range(1, horizon + 1)
    ]


def prepare_oracle_rows(df):
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    required_cols = ["base_ymd", "od", "prosrochka_1"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        raise ValueError({
            "message": "Не найдены нужные колонки Oracle",
            "missing_columns": missing,
            "available_columns": list(df.columns),
        })

    df = df[required_cols]
    df = df.where(pd.notnull(df), None)

    return df.to_dict(orient="records")


async def refresh_fact_from_oracle_by_period(segment_id: str, period: str, session):
    calendar = CalendarService(session)
    ezmes_repo = EzmesRepository(session)

    job = await calendar.get_or_create_monthly_fact_job(
        segment_id=segment_id,
        period=period,
    )

    if not calendar.should_check_oracle(job):
        return {
            "status": "skipped_by_calendar",
            "period": period,
            "base_ymd": job.base_ymd,
            "job_status": job.status,
            "next_check_at": job.next_check_at,
        }

    try:
        df = load_oracle_pivot(segment_id, job.base_ymd)
        rows = prepare_oracle_rows(df)

        if not rows:
            await calendar.repo.mark_checked(
                job_id=job.id,
                next_check_at=next_check_time(1),
            )
            return {
                "status": "no_data_in_oracle",
                "period": period,
                "base_ymd": job.base_ymd,
                "next_check_at": job.next_check_at,
            }

        result = await ezmes_repo.upsert_history(segment_id, rows)

        await calendar.repo.mark_loaded(job.id)

        return {
            "status": "loaded",
            "period": period,
            "base_ymd": job.base_ymd,
            "result": result,
        }

    except Exception as e:
        await calendar.repo.mark_failed(
            job_id=job.id,
            error_message=str(e),
            next_check_at=next_check_time(1),
        )

        return {
            "status": "failed",
            "period": period,
            "base_ymd": job.base_ymd,
            "error": str(e),
        }


async def build_monthly_forecast(segment_id: str, session):
    ezmes_repo = EzmesRepository(session)
    lifecycle = ForecastLifecycleService(session)

    forecast_repo = ForecastRepository(session)

    existing_current = await forecast_repo.get_latest_current_run(
        segment_id=segment_id,
        forecast_type="monthly",
    )

    if existing_current:
        return existing_current

    base_row = await ezmes_repo.get_earliest(segment_id)

    if base_row is None:
        raise ValueError(f"Нет данных в таблице ezmes для сегмента {segment_id}")

    base_value = float(base_row.prosrochka_1)
    months = next_months_from_base(base_row.base_ymd, horizon=3)
    values = []
    for i, month in enumerate(months, start=1):
        forecast_value = base_value * (1 + 0.02 * i)
        values.append({
            "period_month": month,
            "forecast_value": round(forecast_value, 2),
        })

    return await lifecycle.create_current(
        forecast_type="monthly",
        segment_id=segment_id,
        model_name="Simple growth 2%",
        values=values,
    )


async def recalculate_after_fact(run_id: int, session):
    forecast_repo = ForecastRepository(session)
    lifecycle = ForecastLifecycleService(session)

    old_run = await forecast_repo.get_run_by_id(run_id)

    if old_run is None:
        return None

    sorted_values = sorted(old_run.values, key=lambda x: x.period_month)

    fact_values = [v for v in sorted_values if v.fact_value is not None]
    planned_values = [v for v in sorted_values if v.fact_value is None]

    if not fact_values:
        raise ValueError("Нет факта для пересчета прогноза")

    if not planned_values:
        await lifecycle.mark_completed(old_run.id)
        return old_run

    latest_fact = fact_values[-1]
    base_value = float(latest_fact.fact_value)

    values = []

    for v in fact_values:
        values.append({
            "period_month": v.period_month,
            "forecast_value": float(v.forecast_value),
            "fact_value": float(v.fact_value),
            "abs_error": float(v.abs_error) if v.abs_error is not None else None,
            "pct_error": float(v.pct_error) if v.pct_error is not None else None,
            "status": "fact_available",
        })

    for i, old_value in enumerate(planned_values, start=1):
        forecast_value = base_value * (1 + 0.02 * i)
        values.append({
            "period_month": old_value.period_month,
            "forecast_value": round(forecast_value, 2),
            "status": "planned",
        })

    return await lifecycle.create_current(
        forecast_type="monthly",
        segment_id=old_run.segment_id,
        model_name="Simple growth 2% recalculated",
        values=values,
        parent_run_id=old_run.id,
    )


async def auto_update_monthly_forecast(segment_id: str, session):
    forecast_repo = ForecastRepository(session)
    ezmes_repo = EzmesRepository(session)

    current_run = await forecast_repo.get_latest_current_run(
        segment_id=segment_id,
        forecast_type="monthly",
    )

    if current_run is None:
        new_run = await build_monthly_forecast(segment_id, session)
        return {
            "status": "created_new",
            "message": "Current forecast not found. New forecast was created.",
            "run_id": new_run.id,
        }

    sorted_values = sorted(current_run.values, key=lambda x: x.period_month)

    updated_months = []
    oracle_checks = []

    for value in sorted_values:
        if value.fact_value is not None:
            continue

        refresh_result = await refresh_fact_from_oracle_by_period(
            segment_id=segment_id,
            period=value.period_month,
            session=session,
        )
        oracle_checks.append(refresh_result)

        base_ymd = period_to_base_ymd(value.period_month)
        fact_row = await ezmes_repo.get_by_base_ymd(segment_id, base_ymd)

        if fact_row is None:
            continue

        updated = await forecast_repo.update_fact_value(
            run_id=current_run.id,
            period_month=value.period_month,
            fact_value=float(fact_row.prosrochka_1),
        )

        if updated:
            updated_months.append(value.period_month)

    refreshed_run = await forecast_repo.get_run_by_id(current_run.id)
    refreshed_values = sorted(refreshed_run.values, key=lambda x: x.period_month)

    all_completed = all(v.fact_value is not None for v in refreshed_values)

    if all_completed:
        lifecycle = ForecastLifecycleService(session)

        await lifecycle.mark_completed(refreshed_run.id)

        latest_fact = await ezmes_repo.get_latest(segment_id)

        if latest_fact is None:
            return {
                "status": "completed_no_new_fact",
                "completed_run_id": refreshed_run.id,
                "updated_months": updated_months,
                "oracle_checks": oracle_checks,
            }

        new_run = await build_monthly_forecast(segment_id, session)

        return {
            "status": "completed_and_new_created",
            "completed_run_id": refreshed_run.id,
            "new_run_id": new_run.id,
            "updated_months": updated_months,
            "oracle_checks": oracle_checks,
        }
        return {
            "status": "completed_and_new_created",
            "completed_run_id": refreshed_run.id,
            "new_run_id": new_run.id,
            "updated_months": updated_months,
            "oracle_checks": oracle_checks,
        }

    if updated_months:
        new_run = await recalculate_after_fact(refreshed_run.id, session)

        return {
            "status": "fact_updated_and_recalculated",
            "old_run_id": refreshed_run.id,
            "new_run_id": new_run.id,
            "updated_months": updated_months,
            "oracle_checks": oracle_checks,
        }

    return {
        "status": "no_action",
        "message": "По календарю Oracle проверен только там, где разрешено. Новых фактов нет.",
        "run_id": current_run.id,
        "oracle_checks": oracle_checks,
    }