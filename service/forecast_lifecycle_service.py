from repositories.forecast_repository import ForecastRepository


class ForecastLifecycleService:
    def __init__(self, session):
        self.session = session
        self.repo = ForecastRepository(session)

    async def mark_recalculated(self, run_id: int):
        return await self.repo.update_run_status(run_id, "recalculated")

    async def mark_completed(self, run_id: int):
        return await self.repo.update_run_status(run_id, "completed")

    async def archive(self, run_id: int):
        return await self.repo.update_run_status(run_id, "archived")

    async def create_current(
        self,
        forecast_type: str,
        segment_id: str,
        model_name: str,
        values: list[dict],
        parent_run_id: int | None = None,
    ):
        old_current = await self.repo.get_latest_current_run(
            segment_id=segment_id,
            forecast_type=forecast_type,
        )

        if old_current:
            await self.repo.update_run_status(old_current.id, "recalculated")

        new_run = await self.repo.create_run(
            forecast_type=forecast_type,
            segment_id=segment_id,
            model_name=model_name,
            values=values,
            parent_run_id=parent_run_id,
            status="current",
        )

        return new_run