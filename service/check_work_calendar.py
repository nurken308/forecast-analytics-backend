import pandas as pd

from work_calendar_service import (
    build_calendar_dataframe,
    get_peak_schedule,
    get_qurban_ait_info,
    get_recalculation_dates,
    is_non_working_day,
)


def main() -> None:
    print("=" * 80)
    print("КУРБАН-АЙТ")
    print("=" * 80)

    for year in [
        2025,
        2026,
        2027,
        2028,
    ]:
        info = get_qurban_ait_info(year)

        print(
            f"{year}: "
            f"date={info['date'].date()}, "
            f"status={info['status']}, "
            f"is_confirmed={info['is_confirmed']}, "
            f"is_non_working="
            f"{is_non_working_day(info['date'])}"
        )

    print()
    print("=" * 80)
    print("ПИК 5 ИЮЛЯ 2026")
    print("=" * 80)

    july_schedule = get_peak_schedule(
        "2026-07-01"
    )

    peak = july_schedule[5]

    for key, value in peak.items():
        print(f"{key}: {value}")

    print()
    print("=" * 80)
    print("ВСЕ ПЕРЕСЧЕТЫ ИЮЛЯ 2026")
    print("=" * 80)

    recalculation_dates = get_recalculation_dates(
        "2026-07-01"
    )

    for (
        base_day,
        recalculation_date,
    ) in recalculation_dates.items():
        print(
            f"Пик {base_day}: "
            f"{recalculation_date.date()}"
        )

    print()
    print("=" * 80)
    print("ПРОВЕРКА НАУРЫЗА")
    print("=" * 80)

    calendar_2026 = build_calendar_dataframe(2026)

    nauryz = calendar_2026[
        calendar_2026[
            "calendar_date"
        ].between(
            pd.Timestamp("2026-03-19"),
            pd.Timestamp("2026-03-27"),
        )
    ]

    print(
        nauryz[
            [
                "calendar_date",
                "weekday_name",
                "day_type",
                "is_working_day",
                "description",
            ]
        ].to_string(index=False)
    )

    print()
    print("=" * 80)
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("=" * 80)


if __name__ == "__main__":
    main()