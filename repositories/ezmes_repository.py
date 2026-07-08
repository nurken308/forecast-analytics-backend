from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models.models import Prognoz


class EzmesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self, segment_id: str | None = None):
        query = select(Prognoz)

        if segment_id:
            query = query.where(Prognoz.segment_id == segment_id)

        result = await self.session.execute(
            query.order_by(Prognoz.segment_id, Prognoz.base_ymd)
        )
        return result.scalars().all()

    async def get_latest(self, segment_id: str):
        result = await self.session.execute(
            select(Prognoz)
            .where(Prognoz.segment_id == segment_id)
            .order_by(Prognoz.base_ymd.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    async def get_earliest(self, segment_id: str):
        result = await self.session.execute(
            select(Prognoz)
            .where(Prognoz.segment_id == segment_id)
            .order_by(Prognoz.base_ymd.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    async def get_last_n(self, segment_id: str, n: int = 30):
        result = await self.session.execute(
            select(Prognoz)
            .where(Prognoz.segment_id == segment_id)
            .order_by(Prognoz.base_ymd.desc())
            .limit(n)
        )
        rows = result.scalars().all()
        return list(reversed(rows))

    async def get_by_month(self, segment_id: str, period_month: str):
        prefix = period_month.replace("-", "")

        result = await self.session.execute(
            select(Prognoz)
            .where(
                Prognoz.segment_id == segment_id,
                Prognoz.base_ymd.like(f"{prefix}%"),
            )
            .order_by(Prognoz.base_ymd.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_base_ymd(self, segment_id: str, base_ymd: str):
        result = await self.session.execute(
            select(Prognoz).where(
                Prognoz.segment_id == segment_id,
                Prognoz.base_ymd == base_ymd,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_history(self, segment_id: str, rows: list[dict]):
        inserted = 0
        updated = 0

        for row in rows:
            base_ymd = str(row.get("base_ymd"))

            result = await self.session.execute(
                select(Prognoz).where(
                    Prognoz.segment_id == segment_id,
                    Prognoz.base_ymd == base_ymd,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.od = row.get("od", 0) or 0
                existing.prosrochka_1 = row.get("prosrochka_1", 0) or 0
                updated += 1
            else:
                self.session.add(
                    Prognoz(
                        segment_id=segment_id,
                        base_ymd=base_ymd,
                        od=row.get("od", 0) or 0,
                        prosrochka_1=row.get("prosrochka_1", 0) or 0,
                    )
                )
                inserted += 1

        await self.session.commit()

        return {
            "segment_id": segment_id,
            "inserted": inserted,
            "updated": updated,
            "total": inserted + updated,
        }

    async def replace_all(self, segment_id: str, rows: list[dict]):
        await self.session.execute(
            delete(Prognoz).where(Prognoz.segment_id == segment_id)
        )

        objects = []
        for row in rows:
            objects.append(
                Prognoz(
                    segment_id=segment_id,
                    base_ymd=str(row.get("base_ymd")),
                    od=row.get("od", 0) or 0,
                    prosrochka_1=row.get("prosrochka_1", 0) or 0,
                )
            )

        self.session.add_all(objects)
        await self.session.commit()

        return len(objects)