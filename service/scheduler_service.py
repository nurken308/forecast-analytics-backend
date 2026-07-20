import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from db.database import AsyncSessionLocal
from repositories.calendar_job_repository import CalendarJobRepository
from service.monthly_forecast_service import auto_update_monthly_forecast
from service.daily_forecast_service import auto_update_daily_forecast
from service.daily_entity_service import DAILY_ENTITIES


MONTHLY_SEGMENTS = ["retail", "mass", "bk_vkl"]
DAILY_SEGMENTS = DAILY_ENTITIES



LOCAL_TZ = ZoneInfo("Asia/Almaty")
RUN_TIME = time(9, 15)


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def today_run_at(now: datetime) -> datetime:
    return datetime.combine(
        now.date(),
        RUN_TIME,
        tzinfo=LOCAL_TZ,
    )


def next_daily_run_time(now: datetime) -> datetime:
    today_run = today_run_at(now)

    if now < today_run:
        return today_run

    return today_run + timedelta(days=1)


def next_monthly_run_time(now: datetime) -> datetime:
    current_month_run = datetime(
        year=now.year,
        month=now.month,
        day=1,
        hour=RUN_TIME.hour,
        minute=RUN_TIME.minute,
        second=0,
        microsecond=0,
        tzinfo=LOCAL_TZ,
    )

    if now < current_month_run:
        return current_month_run

    return current_month_run + relativedelta(months=1)


def seconds_until(target: datetime) -> float:
    diff = target - now_local()
    return max(diff.total_seconds(), 0)


def current_month_period(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def current_day_period(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def previous_day_base_ymd(dt: datetime) -> str:
    previous_day = dt.date() - timedelta(days=1)
    return previous_day.strftime("%Y%m%d")


async def run_monthly_scheduler_once():
    now = now_local()

    if now.day != 1:
        print(f"[MONTHLY SCHEDULER] Сегодня не 1 число: {now.date()}. Пропуск.")
        return

    if now.time() < RUN_TIME:
        print(f"[MONTHLY SCHEDULER] Еще рано: {now.strftime('%H:%M')}. Ждем 09:15.")
        return

    target_period = current_month_period(now)

    async with AsyncSessionLocal() as session:
        repo = CalendarJobRepository(session)

        scheduler_job = await repo.get_job(
            module="scheduler_monthly",
            segment_id="all",
            target_period=target_period,
        )

        if scheduler_job and scheduler_job.status == "loaded":
            print(f"[MONTHLY SCHEDULER] Уже выполнено за {target_period}. Пропуск.")
            return

        if scheduler_job is None:
            scheduler_job = await repo.create_job(
                module="scheduler_monthly",
                segment_id="all",
                target_period=target_period,
                base_ymd=now.strftime("%Y%m%d"),
                next_check_at=datetime.utcnow(),
            )

        try:
            results = []

            for segment_id in MONTHLY_SEGMENTS:
                print(f"[MONTHLY SCHEDULER] Auto-update monthly: {segment_id}")

                result = await auto_update_monthly_forecast(
                    segment_id=segment_id,
                    session=session,
                )

                results.append(
                    {
                        "segment_id": segment_id,
                        "result": result,
                    }
                )

            await repo.mark_loaded(scheduler_job.id)

            print(f"[MONTHLY SCHEDULER] Выполнено за {target_period}: {results}")

        except Exception as e:
            await repo.mark_failed(
                job_id=scheduler_job.id,
                error_message=str(e),
                next_check_at=datetime.utcnow(),
            )

            print(f"[MONTHLY SCHEDULER] Ошибка: {e}")


async def run_daily_scheduler_once():
    now = now_local()

    if now.time() < RUN_TIME:
        print(f"[DAILY SCHEDULER] Еще рано: {now.strftime('%H:%M')}. Ждем 09:15.")
        return

    target_period = current_day_period(now)
    base_ymd = previous_day_base_ymd(now)

    async with AsyncSessionLocal() as session:
        repo = CalendarJobRepository(session)

        scheduler_job = await repo.get_job(
            module="scheduler_daily",
            segment_id="all",
            target_period=target_period,
        )

        if scheduler_job and scheduler_job.status == "loaded":
            print(f"[DAILY SCHEDULER] Уже выполнено за {target_period}. Пропуск.")
            return

        if scheduler_job is None:
            scheduler_job = await repo.create_job(
                module="scheduler_daily",
                segment_id="all",
                target_period=target_period,
                base_ymd=base_ymd,
                next_check_at=datetime.utcnow(),
            )

        try:
            results = []

            for segment_id in DAILY_SEGMENTS:
                print(
                    f"[DAILY SCHEDULER] Auto-update daily: {segment_id}, "
                    f"base_ymd={base_ymd}"
                )

                result = await auto_update_daily_forecast(
                    segment_id=segment_id,
                    base_ymd=base_ymd,
                    session=session,
                )

                results.append(
                    {
                        "segment_id": segment_id,
                        "result": result,
                    }
                )

            await repo.mark_loaded(scheduler_job.id)

            print(
                f"[DAILY SCHEDULER] Выполнено за {target_period}, "
                f"base_ymd={base_ymd}: {results}"
            )

        except Exception as e:
            await repo.mark_failed(
                job_id=scheduler_job.id,
                error_message=str(e),
                next_check_at=datetime.utcnow(),
            )

            print(f"[DAILY SCHEDULER] Ошибка: {e}")


async def monthly_scheduler_loop():
    print("[MONTHLY SCHEDULER] Запущен.")

    while True:
        now = now_local()

        if now.day == 1 and now.time() >= RUN_TIME:
            await run_monthly_scheduler_once()

        next_run = next_monthly_run_time(now_local())
        sleep_seconds = seconds_until(next_run)

        print(
            "[MONTHLY SCHEDULER] Следующая проверка:",
            next_run.strftime("%Y-%m-%d %H:%M"),
            f"через {round(sleep_seconds / 3600, 2)} часов",
        )

        await asyncio.sleep(sleep_seconds)


async def daily_scheduler_loop():
    print("[DAILY SCHEDULER] Запущен.")

    while True:
        now = now_local()

        if now.time() >= RUN_TIME:
            await run_daily_scheduler_once()

        next_run = next_daily_run_time(now_local())
        sleep_seconds = seconds_until(next_run)

        print(
            "[DAILY SCHEDULER] Следующая проверка:",
            next_run.strftime("%Y-%m-%d %H:%M"),
            f"через {round(sleep_seconds / 3600, 2)} часов",
        )

        await asyncio.sleep(sleep_seconds)


async def scheduler_loop():
    print("[SCHEDULER] Запущен.")

    await asyncio.gather(
        monthly_scheduler_loop(),
        daily_scheduler_loop(),
    )