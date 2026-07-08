from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import CalendarJob


class CalendarJobRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_job(
        self,
        module: str,
        segment_id: str,
        target_period: str,
    ):
        result = await self.session.execute(
            select(CalendarJob).where(
                CalendarJob.module == module,
                CalendarJob.segment_id == segment_id,
                CalendarJob.target_period == target_period,
            )
        )

        return result.scalar_one_or_none()

    async def create_job(
        self,
        module: str,
        segment_id: str,
        target_period: str,
        base_ymd: str,
        next_check_at: datetime,
    ):

        job = CalendarJob(
            module=module,
            segment_id=segment_id,
            target_period=target_period,
            base_ymd=base_ymd,
            status="waiting",
            next_check_at=next_check_at,
        )

        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)

        return job

    async def mark_loaded(self, job_id: int):

        job = await self.session.get(CalendarJob, job_id)

        job.status = "loaded"
        job.loaded_at = datetime.utcnow()

        await self.session.commit()

        return job

    async def mark_failed(
        self,
        job_id: int,
        error_message: str,
        next_check_at: datetime,
    ):

        job = await self.session.get(CalendarJob, job_id)

        job.status = "failed"
        job.error_message = error_message
        job.last_check_at = datetime.utcnow()
        job.next_check_at = next_check_at

        await self.session.commit()

        return job

    async def mark_checked(
        self,
        job_id: int,
        next_check_at: datetime,
    ):

        job = await self.session.get(CalendarJob, job_id)

        job.last_check_at = datetime.utcnow()
        job.next_check_at = next_check_at

        await self.session.commit()

        return job