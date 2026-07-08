from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from repositories.forecast_repository import ForecastRepository
from service.monthly_forecast_service import (
    build_monthly_forecast,
    recalculate_after_fact,
    auto_update_monthly_forecast,
)
router = APIRouter(
    prefix="/monthly-forecast",
    tags=["Monthly Forecast"]
)


def serialize_run(run):
    return {
        "id": run.id,
        "segment_id": run.segment_id,
        "model_name": run.model_name,
        "status": run.status,
        "created_at": run.created_at,
        "values": [
            {
                "period_month": v.period_month,
                "forecast_value": float(v.forecast_value),
                "fact_value": float(v.fact_value) if v.fact_value is not None else None,
                "abs_error": float(v.abs_error) if v.abs_error is not None else None,
                "pct_error": float(v.pct_error) if v.pct_error is not None else None,
                "status": v.status,
            }
            for v in sorted(run.values, key=lambda x: x.period_month)
        ],
    }


@router.get("/health")
def health():
    return {"status": "ok", "module": "monthly forecast"}


@router.post("/build/{segment_id}")
async def build_monthly_run(
    segment_id: str,
    session: AsyncSession = Depends(get_session),
):
    run = await build_monthly_forecast(segment_id, session)
    return {
        "status": "success",
        "run_id": run.id,
        "segment_id": segment_id,
        "message": "Monthly forecast was built and saved",
    }


@router.get("/current/{segment_id}")
async def get_current_monthly_run_by_segment(
    segment_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ForecastRepository(session)
    run = await repo.get_latest_current_run(segment_id, "monthly")

    if not run:
        return {
            "status": "not_found",
            "segment_id": segment_id,
            "message": "Active monthly forecast not found",
        }

    return serialize_run(run)


@router.get("/current")
async def get_current_monthly_runs(
    session: AsyncSession = Depends(get_session),
):
    repo = ForecastRepository(session)
    runs = await repo.get_current_runs("monthly")
    return [serialize_run(run) for run in runs]


@router.get("/history/{segment_id}")
async def get_monthly_history(
    segment_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ForecastRepository(session)
    runs = await repo.get_history(segment_id, "monthly")
    return [serialize_run(run) for run in runs]


@router.get("/archive/all")
async def get_monthly_archive_all(
    session: AsyncSession = Depends(get_session),
):
    repo = ForecastRepository(session)
    runs = await repo.get_archive_all("monthly")
    return [serialize_run(run) for run in runs]


@router.get("/{run_id}")
async def get_monthly_run_details(
    run_id: int,
    session: AsyncSession = Depends(get_session),
):
    repo = ForecastRepository(session)
    run = await repo.get_run_by_id(run_id)

    if not run:
        return {
            "status": "not_found",
            "message": f"Run {run_id} not found",
        }

    return serialize_run(run)


@router.post("/update-fact/{run_id}")
async def update_monthly_fact(
    run_id: int,
    period_month: str,
    fact_value: float,
    session: AsyncSession = Depends(get_session),
):
    repo = ForecastRepository(session)

    value = await repo.update_fact_value(
        run_id=run_id,
        period_month=period_month,
        fact_value=fact_value,
    )

    if value is None:
        return {
            "status": "not_found",
            "message": "Forecast value not found",
        }

    return {
        "status": "success",
        "run_id": run_id,
        "period_month": value.period_month,
        "forecast_value": float(value.forecast_value),
        "fact_value": float(value.fact_value),
        "abs_error": float(value.abs_error),
        "pct_error": float(value.pct_error),
        "value_status": value.status,
    }


@router.post("/recalculate/{run_id}")
async def recalculate_monthly_forecast(
    run_id: int,
    session: AsyncSession = Depends(get_session),
):
    new_run = await recalculate_after_fact(run_id, session)

    if new_run is None:
        return {
            "status": "not_found",
            "message": f"Run {run_id} not found",
        }

    return {
        "status": "success",
        "old_run_id": run_id,
        "new_run_id": new_run.id,
        "segment_id": new_run.segment_id,
        "model_name": new_run.model_name,
        "values_count": "created",
    }
@router.post("/auto-update/{segment_id}")
async def auto_update_monthly(
    segment_id: str,
    session: AsyncSession = Depends(get_session),
):
    return await auto_update_monthly_forecast(segment_id, session)