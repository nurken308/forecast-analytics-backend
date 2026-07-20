from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import requests

# ============================================================
# CONFIG
# ============================================================

API_URL = "http://10.20.70.241:8000"

SEGMENTS = [
    "retail",
    "bk",
    "bk_soft",
    "vkl",
    "vkl_soft",
    "rb_z_ip",
    "rb_z_ip_soft",  # РБ ЗАЛОГОВЫЙ ИП (с), скоринговый продукт
    "rb_z_too",
    "rb_bz_ip",
    "rb_bz_too",
]

# ============================================================
# РЕЖИМ РАБОТЫ
# ============================================================

# True:
# каждый день автоматически обрабатывается вчерашняя дата.
#
# False:
# используется ручной диапазон MANUAL_START_DATE —
# MANUAL_END_DATE для восстановления истории.
AUTO_DATE_MODE = False

MANUAL_START_DATE = "20260718"
MANUAL_END_DATE = "20260718"


def resolve_processing_period() -> tuple[str, str]:
    if AUTO_DATE_MODE:
        yesterday = (
            datetime.today().date()
            - timedelta(days=1)
        ).strftime("%Y%m%d")

        return yesterday, yesterday

    return (
        MANUAL_START_DATE,
        MANUAL_END_DATE,
    )


START_DATE, END_DATE = resolve_processing_period()

REQUEST_TIMEOUT = 900

# Пауза между тяжёлыми Oracle-запросами
REQUEST_DELAY_SECONDS = 2

# Количество повторных попыток при временной ошибке
MAX_RETRIES = 2

# После дозагрузки обновить факты в текущих Daily forecast runs



# ============================================================
# HELPERS
# ============================================================

def generate_dates(start_ymd: str, end_ymd: str) -> list[str]:
    start_date = datetime.strptime(start_ymd, "%Y%m%d").date()
    end_date = datetime.strptime(end_ymd, "%Y%m%d").date()

    if start_date > end_date:
        raise ValueError("START_DATE не может быть больше END_DATE")

    result: list[str] = []
    current_date = start_date

    while current_date <= end_date:
        result.append(current_date.strftime("%Y%m%d"))
        current_date += timedelta(days=1)

    return result


def safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {
            "status": "error",
            "message": response.text or "Backend вернул не JSON",
        }


def get_existing_dates(segment_id: str) -> set[str]:
    url = f"{API_URL}/postgres/ezmes/{segment_id}/last-30"

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    rows = response.json()

    return {
        str(row["base_ymd"])
        for row in rows
        if row.get("base_ymd") is not None
    }





def auto_update_forecast(
    segment_id: str,
    base_ymd: str,
) -> dict[str, Any]:
    """
    Выполняет полный Daily lifecycle:

    1. Загружает факт из Oracle.
    2. Сохраняет его в ezmes.
    3. Обновляет факт в текущем прогнозе.
    4. При необходимости пересчитывает прогноз.
    """

    url = (
        f"{API_URL}/daily-forecast/"
        f"auto-update/{segment_id}/{base_ymd}"
    )

    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = requests.post(
                url,
                timeout=REQUEST_TIMEOUT,
            )

            result = safe_json(response)

            if (
                response.ok
                and result.get("status") != "error"
            ):
                return {
                    "success": True,
                    "segment_id": segment_id,
                    "base_ymd": base_ymd,
                    "result": result,
                }
            error_message = (
                result.get("detail")
                or result.get("message")
                or str(result)
            )

            last_error = (
                f"HTTP {response.status_code}: "
                f"{error_message}"
            )

        except requests.RequestException as error:
            last_error = str(error)

        if attempt <= MAX_RETRIES:
            print(
                f"      ↻ Повтор "
                f"{attempt}/{MAX_RETRIES}: "
                f"{segment_id} | {base_ymd}"
            )

            time.sleep(5)

    return {
        "success": False,
        "segment_id": segment_id,
        "base_ymd": base_ymd,
        "error": (
            last_error
            or "Неизвестная ошибка auto-update"
        ),
    }

# ============================================================
# MAIN
# ============================================================

def main() -> None:
    processing_dates = generate_dates(
        START_DATE,
        END_DATE,
    )

    print("=" * 72)
    print("DAILY FORECAST — АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ")
    print("=" * 72)
    print(
        "Режим:",
        (
            "автоматический"
            if AUTO_DATE_MODE
            else "ручной диапазон"
        ),
    )
    print(
        f"Период: {START_DATE} — {END_DATE}"
    )
    print(
        f"Сегментов: {len(SEGMENTS)}"
    )
    print("=" * 72)

    success_count = 0
    failed: list[dict[str, Any]] = []

    # --------------------------------------------------------
    # ОБРАБАТЫВАЕМ КАЖДЫЙ СЕГМЕНТ ПОСЛЕДОВАТЕЛЬНО
    # --------------------------------------------------------

    for segment_index, segment_id in enumerate(
        SEGMENTS,
        start=1,
    ):
        print()
        print(
            f"[{segment_index}/{len(SEGMENTS)}] "
            f"Сегмент: {segment_id}"
        )

        for date_index, base_ymd in enumerate(
            processing_dates,
            start=1,
        ):
            print(
                f"   "
                f"[{date_index}/{len(processing_dates)}] "
                f"{base_ymd} ...",
                end=" ",
                flush=True,
            )

            result = auto_update_forecast(
                segment_id=segment_id,
                base_ymd=base_ymd,
            )

            if result["success"]:
                success_count += 1

                api_result = result["result"]

                action = api_result.get(
                    "action",
                    api_result.get(
                        "status",
                        "updated",
                    ),
                )

                fact_updated = api_result.get(
                    "fact_updated"
                )

                print(
                    f"✅ action={action}",
                    end="",
                )

                if fact_updated is not None:
                    print(
                        f", fact_updated="
                        f"{fact_updated}",
                        end="",
                    )

                adaptive_result = api_result.get(
                    "adaptive_recalculation"
                )

                if adaptive_result:
                    print(
                        ", "
                        f"new_run_id="
                        f"{adaptive_result.get('new_run_id')}",
                        end="",
                    )

                    print(
                        ", "
                        f"level_correction="
                        f"{adaptive_result.get('level_correction')}",
                        end="",
                    )

                recalculation_result = (
                    api_result.get(
                        "recalculation"
                    )
                )

                if recalculation_result:
                    print(
                        ", "
                        f"new_run_id="
                        f"{recalculation_result.get('new_run_id')}",
                        end="",
                    )

                print()

            else:
                failed.append(result)

                print(
                    f"❌ {result.get('error')}"
                )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    # --------------------------------------------------------
    # ИТОГ
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("РЕЗУЛЬТАТ")
    print("=" * 72)
    print(
        f"Успешно обработано: "
        f"{success_count}"
    )
    print(
        f"Ошибок: {len(failed)}"
    )

    if failed:
        print()
        print("Список ошибок:")

        for item in failed:
            print(
                f"- {item.get('segment_id')} | "
                f"{item.get('base_ymd')} | "
                f"{item.get('error')}"
            )

    print()
    print("Готово.")


if __name__ == "__main__":
    main()