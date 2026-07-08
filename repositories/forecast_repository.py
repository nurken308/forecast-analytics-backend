from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.models import ForecastRun, ForecastValue


class ForecastRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(
        self,
        forecast_type: str,
        segment_id: str,
        model_name: str,
        values: list[dict],
        parent_run_id: int | None = None,
        status: str = "current",
    ):
        run = ForecastRun(
            forecast_type=forecast_type,
            segment_id=segment_id,
            model_name=model_name,
            parent_run_id=parent_run_id,
            status=status,
        )

        self.session.add(run)
        await self.session.flush()

        for item in values:
            self.session.add(
                ForecastValue(
                    run_id=run.id,
                    period_month=item["period_month"],
                    forecast_value=item["forecast_value"],
                    fact_value=item.get("fact_value"),
                    abs_error=item.get("abs_error"),
                    pct_error=item.get("pct_error"),
                    status=item.get("status", "planned"),
                )
            )

        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_latest_current_run(
        self,
        segment_id: str,
        forecast_type: str = "monthly",
    ):
        result = await self.session.execute(
            select(ForecastRun)
            .where(
                ForecastRun.forecast_type == forecast_type,
                ForecastRun.segment_id == segment_id,
                ForecastRun.status.in_(["current", "active"]),
            )
            .options(selectinload(ForecastRun.values))
            .order_by(ForecastRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_current_runs(self, forecast_type: str = "monthly"):
        result = await self.session.execute(
            select(ForecastRun)
            .where(
                ForecastRun.forecast_type == forecast_type,
                ForecastRun.status.in_(["current", "active"]),
            )
            .options(selectinload(ForecastRun.values))
            .order_by(ForecastRun.created_at.desc())
        )
        return result.scalars().all()

    async def get_run_by_id(self, run_id: int):
        result = await self.session.execute(
            select(ForecastRun)
            .where(ForecastRun.id == run_id)
            .options(selectinload(ForecastRun.values))
        )
        return result.scalar_one_or_none()

    async def update_fact_value(
        self,
        run_id: int,
        period_month: str,
        fact_value: float,
    ):
        result = await self.session.execute(
            select(ForecastValue).where(
                ForecastValue.run_id == run_id,
                ForecastValue.period_month == period_month,
            )
        )

        value = result.scalar_one_or_none()

        if value is None:
            return None

        forecast_value = float(value.forecast_value)
        abs_error = fact_value - forecast_value
        pct_error = (abs_error / forecast_value * 100) if forecast_value != 0 else None

        value.fact_value = fact_value
        value.abs_error = round(abs_error, 2)
        value.pct_error = round(pct_error, 4) if pct_error is not None else None
        value.status = "fact_available"

        await self.session.commit()
        await self.session.refresh(value)

        return value

    async def update_run_status(self, run_id: int, status: str):
        run = await self.get_run_by_id(run_id)

        if run is None:
            return None

        run.status = status
        await self.session.commit()
        await self.session.refresh(run)

        return run

    async def get_history(
        self,
        segment_id: str,
        forecast_type: str = "monthly",
    ):
        result = await self.session.execute(
            select(ForecastRun)
            .where(
                ForecastRun.forecast_type == forecast_type,
                ForecastRun.segment_id == segment_id,
                ForecastRun.status.in_(["current", "active", "recalculated", "completed", "archived"]),
            )
            .options(selectinload(ForecastRun.values))
            .order_by(ForecastRun.created_at.desc())
        )
        return result.scalars().all()

    async def get_archive_all(self, forecast_type: str = "monthly"):
        result = await self.session.execute(
            select(ForecastRun)
            .where(
                ForecastRun.forecast_type == forecast_type,
                ForecastRun.status.in_(["recalculated", "completed", "archived"]),
            )
            .options(selectinload(ForecastRun.values))
            .order_by(ForecastRun.created_at.desc())
        )
        return result.scalars().all()