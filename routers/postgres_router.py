from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from repositories.ezmes_repository import EzmesRepository
from service.oracle_sql_service import load_oracle_pivot

router = APIRouter(prefix="/postgres", tags=["PostgreSQL"])


@router.get("/ezmes")
async def get_ezmes(session: AsyncSession = Depends(get_session)):
    repo = EzmesRepository(session)
    rows = await repo.get_all(segment_id=None)

    return [
        {
            "id": row.id,
            "base_ymd": row.base_ymd,
            "od": float(row.od),
            "prosrochka_1": float(row.prosrochka_1),
        }
        for row in rows
    ]


@router.get("/ezmes/{segment_id}/last-30")
async def get_last_30_ezmes(
    segment_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = EzmesRepository(session)
    rows = await repo.get_last_n(segment_id, 30)

    return [
        {
            "id": row.id,
            "base_ymd": row.base_ymd,
            "od": float(row.od),
            "prosrochka_1": float(row.prosrochka_1),
        }
        for row in rows
    ]


@router.get("/ezmes/{segment_id}/fact/{period_month}")
async def get_fact_by_month(
    period_month: str,
    session: AsyncSession = Depends(get_session),
):
    repo = EzmesRepository(session)
    row = await repo.get_by_month(segment_id, period_month)

    if not row:
        return {
            "status": "not_found",
            "period_month": period_month,
        }

    return {
        "status": "success",
        "period_month": period_month,
        "base_ymd": row.base_ymd,
        "od": float(row.od),
        "prosrochka_1": float(row.prosrochka_1),
    }


@router.post("/ezmes/upsert-test")
async def upsert_test_ezmes(session: AsyncSession = Depends(get_session)):
    repo = EzmesRepository(session)

    rows = [
        {
            "base_ymd": "20260531",
            "od": 304555.98,
            "prosrochka_1": 120079.50,
        },
        {
            "base_ymd": "20260630",
            "od": 309000.00,
            "prosrochka_1": 121500.00,
        },
    ]

    result = await repo.upsert_history(segment_id, rows)

    return {
        "status": "success",
        **result,
    }


@router.post("/ezmes/refresh/{segment_id}")
async def refresh_ezmes(segment_id: str, session: AsyncSession = Depends(get_session)):
    df = load_oracle_pivot(segment_id)

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    required_cols = ["base_ymd", "od", "prosrochka_1"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        return {
            "status": "error",
            "message": "Не найдены нужные колонки",
            "missing_columns": missing,
            "available_columns": list(df.columns),
        }

    df = df[required_cols]
    df = df.where(df.notnull(), None)

    rows = df.to_dict(orient="records")

    repo = EzmesRepository(session)
    result = await repo.upsert_history(segment_id, rows)

    return {
        "status": "success",
        "segment_id": segment_id,
        **result,
    }
@router.post("/ezmes/refresh/{segment_id}/{base_ymd}")
async def refresh_ezmes_by_date(
    segment_id: str,
    base_ymd: str,
    session: AsyncSession = Depends(get_session),
):
    df = load_oracle_pivot(segment_id, base_ymd)

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    required_cols = ["base_ymd", "od", "prosrochka_1"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        return {
            "status": "error",
            "message": "Не найдены нужные колонки",
            "missing_columns": missing,
            "available_columns": list(df.columns),
        }

    df = df[required_cols]
    df = df.where(df.notnull(), None)

    rows = df.to_dict(orient="records")

    repo = EzmesRepository(session)
    result = await repo.upsert_history(segment_id, rows)

    return {
        "status": "success",
        "segment_id": segment_id,
        "base_ymd": base_ymd,
        **result,
    }