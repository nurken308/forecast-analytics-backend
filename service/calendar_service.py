from datetime import datetime
from dateutil.relativedelta import relativedelta

from repositories.calendar_job_repository import CalendarJobRepository


def period_to_base_ymd(period: str) -> str:
    # "2026-07" -> "20260630"
    dt = datetime.strptime(period + "-01", "%Y-%m-%d")
    prev_month_end = dt + relativedelta(days=-1)
    return prev_month_end.strftime("%Y%m%d")


def next_check_time(days: int = 1) -> datetime:
    return datetime.utcnow() + relativedelta(days=days)


class CalendarService:
    def __init__(self, session):
        self.repo = CalendarJobRepository(session)

    async def get_or_create_monthly_fact_job(
        self,
        segment_id: str,
        period: str,
    ):
        job = await self.repo.get_job(
            module="forecast_monthly",
            segment_id=segment_id,
            target_period=period,
        )

        if job:
            return job

        base_ymd = period_to_base_ymd(period)

        return await self.repo.create_job(
            module="forecast_monthly",
            segment_id=segment_id,
            target_period=period,
            base_ymd=base_ymd,
            next_check_at=datetime.utcnow(),
        )

    def should_check_oracle(self, job) -> bool:
        if job.status == "loaded":
            return False

        if job.next_check_at is None:
            return True

        return datetime.utcnow() >= job.next_check_at