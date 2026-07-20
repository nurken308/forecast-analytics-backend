from work_calendar_service import get_peak_schedule


def print_schedule(segment_id: str) -> None:
    print()
    print("=" * 80)
    print(f"SEGMENT: {segment_id}")
    print("=" * 80)

    schedule = get_peak_schedule(
        month_start="2026-07-01",
        segment_id=segment_id,
    )

    for base_day, item in schedule.items():
        print(
            f"Пик {base_day}: "
            f"original={item['original_peak_date'].date()} | "
            f"actual={item['actual_peak_date'].date()} | "
            f"fact_available={item['fact_available_date'].date()} | "
            f"recalculation={item['recalculation_date'].date()} | "
            f"delayed_soft_peak={item['delayed_soft_peak']}"
        )


def main() -> None:
    for segment_id in [
        "retail",
        "bk",
        "bk_soft",
        "vkl",
        "vkl_soft",
    ]:
        print_schedule(segment_id)


if __name__ == "__main__":
    main()