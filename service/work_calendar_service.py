from __future__ import annotations

from calendar import monthrange
from typing import Dict, Iterable, Optional, Set, TypedDict

import pandas as pd


# ============================================================
# 1. БАЗОВЫЕ НАСТРОЙКИ
# ============================================================

# Контрольные платежные пики.
BASE_PAYMENT_DAYS = [2, 5, 10, 15, 20, 25]


# Для этих сущностей пик, выпавший на нерабочий день,
# появляется не в первый, а во второй рабочий день
# после окончания нерабочего периода.
SOFT_DELAYED_PEAK_ENTITIES = {
    "bk_soft",
    "vkl_soft",
}


class QurbanAitConfig(TypedDict):
    date: str
    status: str


# ============================================================
# 2. ПОСТОЯННЫЕ ПРАЗДНИКИ КАЗАХСТАНА
# ============================================================

KZ_FIXED_HOLIDAYS_BY_MONTH_DAY: Dict[
    tuple[int, int],
    str,
] = {
    (1, 1): "Новый год",
    (1, 2): "Новый год",

    (3, 8): "Международный женский день",

    (3, 21): "Наурыз мейрамы",
    (3, 22): "Наурыз мейрамы",
    (3, 23): "Наурыз мейрамы",

    (5, 1): "Праздник единства народа Казахстана",
    (5, 7): "День защитника Отечества",
    (5, 9): "День Победы",

    (7, 6): "День столицы",

    (8, 30): "День Конституции Республики Казахстан",

    (10, 25): "День Республики",

    (12, 16): "День Независимости",
}


# Православное Рождество является нерабочим днем,
# но дополнительный перенос за него не создается.
KZ_ORTHODOX_CHRISTMAS_MONTH_DAY = (1, 7)


# ============================================================
# 3. КУРБАН-АЙТ
# ============================================================

# confirmed:
# дата официально подтверждена и влияет на календарь.
#
# estimated:
# дата предварительная и не влияет:
# - на рабочие дни;
# - на перенос пиков;
# - на scheduler;
# - на даты пересчета.
KZ_QURBAN_AIT_BY_YEAR: Dict[int, QurbanAitConfig] = {
    2025: {
        "date": "2025-06-06",
        "status": "confirmed",
    },
    2026: {
        "date": "2026-05-27",
        "status": "confirmed",
    },

    # После официального подтверждения можно добавить:
    #
    # 2027: {
    #     "date": "2027-05-16",
    #     "status": "confirmed",
    # },
}


QURBAN_AIT_ESTIMATION_SHIFT_DAYS = 11


# ============================================================
# 4. ДОПОЛНИТЕЛЬНЫЕ ВЫХОДНЫЕ И РАБОЧИЕ ДНИ
# ============================================================

# Дополнительные нерабочие дни, утвержденные отдельно.
# Автоматические переносы праздников сюда добавлять не нужно.
KZ_EXTRA_NON_WORKING_BY_YEAR: Dict[
    int,
    Dict[str, str],
] = {
    2026: {},
    2027: {},
}


# Дополнительные рабочие дни.
# Например, рабочая суббота из-за официального переноса.
KZ_EXTRA_WORKING_BY_YEAR: Dict[
    int,
    Dict[str, str],
] = {
    2026: {},
    2027: {},
}


# ============================================================
# 5. НОРМАЛИЗАЦИЯ ДАТ
# ============================================================

def normalize_date(value) -> pd.Timestamp:
    """
    Приводит значение к pandas.Timestamp без времени.
    """

    if value is None:
        raise ValueError("Дата не может быть None.")

    return pd.Timestamp(value).normalize()


def normalize_dates(values: Iterable) -> Set[pd.Timestamp]:
    """
    Преобразует коллекцию дат в набор нормализованных дат.
    """

    return {
        normalize_date(value)
        for value in values
    }


def normalize_segment_id(
    segment_id: Optional[str],
) -> Optional[str]:
    """
    Нормализует идентификатор Daily entity.
    """

    if segment_id is None:
        return None

    normalized = str(segment_id).strip().lower()

    return normalized or None


# ============================================================
# 6. БАЗОВЫЕ ПРАЗДНИКИ
# ============================================================

def get_fixed_holidays(
    year: int,
) -> Dict[pd.Timestamp, str]:
    """
    Возвращает государственные и национальные праздники года.
    """

    result: Dict[pd.Timestamp, str] = {}

    for (
        month,
        day,
    ), description in KZ_FIXED_HOLIDAYS_BY_MONTH_DAY.items():
        holiday_date = pd.Timestamp(
            year=year,
            month=month,
            day=day,
        )

        result[holiday_date] = description

    return result


def get_orthodox_christmas(
    year: int,
) -> Dict[pd.Timestamp, str]:
    """
    Возвращает православное Рождество.
    """

    month, day = KZ_ORTHODOX_CHRISTMAS_MONTH_DAY

    holiday_date = pd.Timestamp(
        year=year,
        month=month,
        day=day,
    )

    return {
        holiday_date: "Православное Рождество",
    }


# ============================================================
# 7. КУРБАН-АЙТ
# ============================================================

def validate_qurban_ait_status(
    status: str,
) -> str:
    """
    Проверяет статус даты Курбан-айта.
    """

    normalized_status = str(status).strip().lower()

    allowed_statuses = {
        "confirmed",
        "estimated",
    }

    if normalized_status not in allowed_statuses:
        raise ValueError(
            "Некорректный статус Курбан-айта: "
            f"{status}. "
            "Допустимо: confirmed, estimated."
        )

    return normalized_status


def estimate_qurban_ait_date(
    year: int,
) -> pd.Timestamp:
    """
    Предварительно оценивает дату Курбан-айта.

    Если год отсутствует в конфигурации:
    - берется ближайший предыдущий известный год;
    - дата переносится в нужный календарный год;
    - на каждый следующий год вычитается примерно 11 дней.

    Estimated-дата не влияет на производственный календарь.
    """

    configured = KZ_QURBAN_AIT_BY_YEAR.get(year)

    if configured is not None:
        return normalize_date(
            configured["date"]
        )

    previous_years = sorted(
        known_year
        for known_year in KZ_QURBAN_AIT_BY_YEAR
        if known_year < year
    )

    if not previous_years:
        raise ValueError(
            "Невозможно предварительно определить "
            f"Курбан-айт для {year} года: "
            "отсутствует базовая дата."
        )

    latest_known_year = max(previous_years)

    latest_known_date = normalize_date(
        KZ_QURBAN_AIT_BY_YEAR[
            latest_known_year
        ]["date"]
    )

    years_difference = (
        year - latest_known_year
    )

    estimated_date = (
        latest_known_date
        + pd.DateOffset(
            years=years_difference
        )
        - pd.Timedelta(
            days=(
                QURBAN_AIT_ESTIMATION_SHIFT_DAYS
                * years_difference
            )
        )
    )

    return normalize_date(
        estimated_date
    )


def get_qurban_ait_info(
    year: int,
) -> Dict[str, object]:
    """
    Возвращает дату и статус Курбан-айта.
    """

    configured = KZ_QURBAN_AIT_BY_YEAR.get(year)

    if configured is not None:
        status = validate_qurban_ait_status(
            configured["status"]
        )

        qurban_date = normalize_date(
            configured["date"]
        )
    else:
        status = "estimated"
        qurban_date = estimate_qurban_ait_date(
            year
        )

    return {
        "date": qurban_date,
        "status": status,
        "is_confirmed": status == "confirmed",
    }


def get_qurban_ait_date(
    year: int,
) -> pd.Timestamp:
    """
    Возвращает подтвержденную или предварительную дату.
    """

    info = get_qurban_ait_info(year)

    return info["date"]


def is_qurban_ait_confirmed(
    year: int,
) -> bool:
    """
    Проверяет, подтверждена ли дата Курбан-айта.
    """

    info = get_qurban_ait_info(year)

    return bool(
        info["is_confirmed"]
    )


def get_confirmed_qurban_ait_holiday(
    year: int,
) -> Dict[pd.Timestamp, str]:
    """
    Возвращает Курбан-айт как нерабочий день
    только при статусе confirmed.
    """

    info = get_qurban_ait_info(year)

    if not info["is_confirmed"]:
        return {}

    return {
        info["date"]: "Первый день Курбан-айта",
    }


# ============================================================
# 8. ДОПОЛНИТЕЛЬНЫЕ ДНИ
# ============================================================

def get_extra_non_working_days(
    year: int,
) -> Dict[pd.Timestamp, str]:
    """
    Возвращает дополнительные нерабочие дни года.
    """

    configured = KZ_EXTRA_NON_WORKING_BY_YEAR.get(
        year,
        {},
    )

    return {
        normalize_date(day): description
        for day, description in configured.items()
    }


def get_extra_working_days(
    year: int,
) -> Dict[pd.Timestamp, str]:
    """
    Возвращает дополнительные рабочие дни года.
    """

    configured = KZ_EXTRA_WORKING_BY_YEAR.get(
        year,
        {},
    )

    return {
        normalize_date(day): description
        for day, description in configured.items()
    }


# ============================================================
# 9. ВЫХОДНЫЕ ДНИ
# ============================================================

def is_weekend(d) -> bool:
    """
    Проверяет, является ли дата субботой или воскресеньем.
    """

    d = normalize_date(d)

    return d.weekday() >= 5


def is_extra_working_day(d) -> bool:
    """
    Проверяет, является ли дата дополнительным рабочим днем.
    """

    d = normalize_date(d)

    return d in get_extra_working_days(
        d.year
    )


# ============================================================
# 10. АВТОМАТИЧЕСКИЕ ПЕРЕНОСЫ ПРАЗДНИКОВ
# ============================================================

def get_transferred_holidays(
    year: int,
) -> Dict[pd.Timestamp, str]:
    """
    Рассчитывает дополнительные выходные при совпадении
    фиксированного государственного праздника с выходным.

    Православное Рождество и Курбан-айт сюда не входят.
    """

    fixed_holidays = get_fixed_holidays(year)
    fixed_dates = set(
        fixed_holidays.keys()
    )

    transferred: Dict[pd.Timestamp, str] = {}

    weekend_holidays = sorted(
        holiday_date
        for holiday_date in fixed_dates
        if holiday_date.weekday() >= 5
    )

    for holiday_date in weekend_holidays:
        candidate = (
            holiday_date
            + pd.Timedelta(days=1)
        )

        while (
            candidate.weekday() >= 5
            or candidate in fixed_dates
            or candidate in transferred
        ):
            candidate += pd.Timedelta(days=1)

        transferred[candidate] = (
            "Перенос выходного за праздник "
            f"{holiday_date.strftime('%d.%m.%Y')} — "
            f"{fixed_holidays[holiday_date]}"
        )

    return transferred


# ============================================================
# 11. ПОЛНЫЙ ПРАЗДНИЧНЫЙ КАЛЕНДАРЬ
# ============================================================

def get_kz_holiday_details(
    year: int,
) -> Dict[pd.Timestamp, str]:
    """
    Возвращает все официальные и дополнительные
    нерабочие даты года.
    """

    result: Dict[pd.Timestamp, str] = {}

    result.update(
        get_fixed_holidays(year)
    )

    result.update(
        get_transferred_holidays(year)
    )

    result.update(
        get_orthodox_christmas(year)
    )

    result.update(
        get_confirmed_qurban_ait_holiday(year)
    )

    result.update(
        get_extra_non_working_days(year)
    )

    # Дополнительный рабочий день имеет высший приоритет.
    for working_day in get_extra_working_days(year):
        result.pop(
            working_day,
            None,
        )

    return result


def get_kz_non_working_days(
    year: int,
) -> Set[pd.Timestamp]:
    """
    Возвращает праздничные и дополнительные нерабочие дни.

    Обычные субботы и воскресенья проверяются отдельно.
    """

    return set(
        get_kz_holiday_details(year).keys()
    )


def get_kz_non_working_days_2026() -> Set[pd.Timestamp]:
    """
    Обратная совместимость со старым кодом.
    """

    return get_kz_non_working_days(
        2026
    )


def is_kz_holiday(d) -> bool:
    """
    Проверяет, является ли дата праздником
    или перенесенным выходным.
    """

    d = normalize_date(d)

    return d in get_kz_non_working_days(
        d.year
    )


def is_non_working_day(d) -> bool:
    """
    Определяет, является ли дата нерабочей.

    Дополнительный рабочий день имеет высший приоритет.
    Estimated Курбан-айт не влияет на результат.
    """

    d = normalize_date(d)

    if is_extra_working_day(d):
        return False

    return (
        is_weekend(d)
        or is_kz_holiday(d)
    )


# ============================================================
# 12. ТИП И ОПИСАНИЕ ДНЯ
# ============================================================

def get_day_type(d) -> str:
    """
    Возвращает тип календарного дня.
    """

    d = normalize_date(d)
    year = d.year

    if d in get_extra_working_days(year):
        return "transferred_working_day"

    if d in get_transferred_holidays(year):
        return "transferred_day_off"

    if d in get_extra_non_working_days(year):
        return "extra_day_off"

    if d in get_fixed_holidays(year):
        return "holiday"

    if d in get_orthodox_christmas(year):
        return "holiday"

    if d in get_confirmed_qurban_ait_holiday(year):
        return "holiday"

    qurban_info = get_qurban_ait_info(year)

    if (
        not qurban_info["is_confirmed"]
        and d == qurban_info["date"]
    ):
        return "estimated_qurban_ait"

    if is_weekend(d):
        return "weekend"

    return "working"


def get_day_description(
    d,
) -> Optional[str]:
    """
    Возвращает описание календарного дня.
    """

    d = normalize_date(d)
    year = d.year

    extra_working_days = get_extra_working_days(
        year
    )

    if d in extra_working_days:
        return extra_working_days[d]

    holiday_details = get_kz_holiday_details(
        year
    )

    if d in holiday_details:
        return holiday_details[d]

    qurban_info = get_qurban_ait_info(year)

    if (
        not qurban_info["is_confirmed"]
        and d == qurban_info["date"]
    ):
        return (
            "Предварительная дата первого дня "
            "Курбан-айта. "
            "Не влияет на производственный календарь."
        )

    return None


# ============================================================
# 13. РАБОЧИЕ ДНИ
# ============================================================

def shift_to_working_day(d):
    """
    Переносит дату на ближайший следующий рабочий день.

    Если дата рабочая, возвращает ее без изменений.
    """

    d = normalize_date(d)

    while is_non_working_day(d):
        d += pd.Timedelta(days=1)

    return d


def previous_working_day(d):
    """
    Возвращает предыдущий рабочий день строго до даты.
    """

    d = (
        normalize_date(d)
        - pd.Timedelta(days=1)
    )

    while is_non_working_day(d):
        d -= pd.Timedelta(days=1)

    return d


def next_working_day(d):
    """
    Возвращает следующий рабочий день строго после даты.
    """

    d = (
        normalize_date(d)
        + pd.Timedelta(days=1)
    )

    while is_non_working_day(d):
        d += pd.Timedelta(days=1)

    return d


def add_working_days(
    d,
    working_days: int,
):
    """
    Сдвигает дату на заданное количество рабочих дней.
    """

    d = normalize_date(d)

    if working_days == 0:
        return d

    direction = (
        1
        if working_days > 0
        else -1
    )

    remaining = abs(
        working_days
    )

    while remaining > 0:
        d += pd.Timedelta(
            days=direction
        )

        if not is_non_working_day(d):
            remaining -= 1

    return d


# ============================================================
# 14. ОСОБЫЙ ПЕРЕНОС SOFT-ПИКОВ
# ============================================================

def uses_delayed_soft_peak(
    segment_id: Optional[str],
) -> bool:
    """
    Проверяет, использует ли сущность отложенный SOFT-пик.
    """

    normalized_segment_id = normalize_segment_id(
        segment_id
    )

    return (
        normalized_segment_id
        in SOFT_DELAYED_PEAK_ENTITIES
    )


def shift_soft_peak_to_second_working_day(d):
    """
    Перенос пика для bk_soft и vkl_soft.

    Если базовая дата рабочая:
        пик остается на исходной дате.

    Если базовая дата нерабочая:
        1. находится первый рабочий день;
        2. пик переносится на следующий рабочий день.

    Пример:
        суббота -> понедельник первый рабочий день
                -> вторник фактический SOFT-пик.
    """

    d = normalize_date(d)

    if not is_non_working_day(d):
        return d

    first_working_day = shift_to_working_day(
        d
    )

    second_working_day = next_working_day(
        first_working_day
    )

    return second_working_day


def shift_peak_date(
    d,
    segment_id: Optional[str] = None,
):
    """
    Возвращает фактическую дату пика с учетом сущности.

    Обычные сущности:
        первый рабочий день.

    bk_soft и vkl_soft:
        если исходная дата нерабочая —
        второй рабочий день.
    """

    d = normalize_date(d)

    if uses_delayed_soft_peak(segment_id):
        return shift_soft_peak_to_second_working_day(
            d
        )

    return shift_to_working_day(
        d
    )


# ============================================================
# 15. ПИКИ
# ============================================================

def get_shifted_peak_dates(
    month_start,
    segment_id: Optional[str] = None,
) -> Dict[int, pd.Timestamp]:
    """
    Возвращает фактические даты контрольных пиков месяца.

    Поддерживает старый вызов:

        get_shifted_peak_dates(month_start)

    И новый сегментный вызов:

        get_shifted_peak_dates(
            month_start,
            segment_id="bk_soft",
        )
    """

    month_start = (
        normalize_date(month_start)
        .replace(day=1)
    )

    result: Dict[int, pd.Timestamp] = {}

    days_in_month = monthrange(
        month_start.year,
        month_start.month,
    )[1]

    for base_day in BASE_PAYMENT_DAYS:
        if base_day > days_in_month:
            continue

        original_peak_date = (
            month_start.replace(
                day=base_day
            )
        )

        actual_peak_date = shift_peak_date(
            d=original_peak_date,
            segment_id=segment_id,
        )

        result[base_day] = (
            actual_peak_date
        )

    return result


# ============================================================
# 16. ПЕРЕСЧЕТЫ
# ============================================================

def get_recalculation_date(
    actual_peak_date,
):
    """
    Рассчитывает дату пересчета после фактического пика.

    1. actual_peak_date — фактический день пика.
    2. Следующий рабочий день — доступность факта.
    3. Еще следующий рабочий день — пересчет.
    """

    actual_peak_date = normalize_date(
        actual_peak_date
    )

    fact_available_date = next_working_day(
        actual_peak_date
    )

    recalculation_date = next_working_day(
        fact_available_date
    )

    return recalculation_date


def get_peak_schedule(
    month_start,
    segment_id: Optional[str] = None,
) -> Dict[int, Dict[str, object]]:
    """
    Возвращает полный график пиков месяца.

    Для каждого пика:
    - base_day;
    - original_peak_date;
    - actual_peak_date;
    - fact_available_date;
    - recalculation_date;
    - segment_id;
    - delayed_soft_peak.
    """

    month_start = (
        normalize_date(month_start)
        .replace(day=1)
    )

    normalized_segment_id = normalize_segment_id(
        segment_id
    )

    shifted_peaks = get_shifted_peak_dates(
        month_start=month_start,
        segment_id=normalized_segment_id,
    )

    result: Dict[int, Dict[str, object]] = {}

    for (
        base_day,
        actual_peak_date,
    ) in shifted_peaks.items():
        original_peak_date = (
            month_start.replace(
                day=base_day
            )
        )

        fact_available_date = next_working_day(
            actual_peak_date
        )

        recalculation_date = next_working_day(
            fact_available_date
        )

        result[base_day] = {
            "base_day": base_day,
            "segment_id": normalized_segment_id,
            "delayed_soft_peak": (
                uses_delayed_soft_peak(
                    normalized_segment_id
                )
                and is_non_working_day(
                    original_peak_date
                )
            ),
            "original_peak_date": (
                original_peak_date
            ),
            "actual_peak_date": (
                actual_peak_date
            ),
            "fact_available_date": (
                fact_available_date
            ),
            "recalculation_date": (
                recalculation_date
            ),
        }

    return result


def get_recalculation_dates(
    month_start,
    segment_id: Optional[str] = None,
) -> Dict[int, pd.Timestamp]:
    """
    Возвращает даты пересчета всех пиков месяца.

    Старый код продолжает работать без segment_id.
    """

    peak_schedule = get_peak_schedule(
        month_start=month_start,
        segment_id=segment_id,
    )

    return {
        base_day: schedule[
            "recalculation_date"
        ]
        for (
            base_day,
            schedule,
        ) in peak_schedule.items()
    }


def find_peak_by_recalculation_date(
    month_start,
    recalculation_date,
    segment_id: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    """
    Находит пик по дате пересчета.
    """

    recalculation_date = normalize_date(
        recalculation_date
    )

    peak_schedule = get_peak_schedule(
        month_start=month_start,
        segment_id=segment_id,
    )

    for schedule in peak_schedule.values():
        if (
            schedule["recalculation_date"]
            == recalculation_date
        ):
            return schedule

    return None


def is_recalculation_date(
    d,
    month_start=None,
    segment_id: Optional[str] = None,
) -> bool:
    """
    Проверяет, является ли дата датой пересчета
    для указанной Daily entity.
    """

    d = normalize_date(d)

    if month_start is None:
        month_start = d.replace(
            day=1
        )
    else:
        month_start = (
            normalize_date(month_start)
            .replace(day=1)
        )

    return (
        find_peak_by_recalculation_date(
            month_start=month_start,
            recalculation_date=d,
            segment_id=segment_id,
        )
        is not None
    )


# ============================================================
# 17. ДИАГНОСТИКА
# ============================================================

def build_calendar_dataframe(
    year: int,
) -> pd.DataFrame:
    """
    Формирует полный календарь года.
    """

    start_date = pd.Timestamp(
        year=year,
        month=1,
        day=1,
    )

    end_date = pd.Timestamp(
        year=year,
        month=12,
        day=31,
    )

    qurban_info = get_qurban_ait_info(
        year
    )

    rows = []

    for current_date in pd.date_range(
        start=start_date,
        end=end_date,
        freq="D",
    ):
        is_estimated_qurban = (
            not qurban_info["is_confirmed"]
            and current_date
            == qurban_info["date"]
        )

        rows.append(
            {
                "calendar_date": current_date,
                "year": current_date.year,
                "month": current_date.month,
                "day": current_date.day,
                "weekday": current_date.weekday(),
                "weekday_name": (
                    current_date.day_name()
                ),
                "day_type": get_day_type(
                    current_date
                ),
                "is_working_day": (
                    not is_non_working_day(
                        current_date
                    )
                ),
                "is_non_working_day": (
                    is_non_working_day(
                        current_date
                    )
                ),
                "is_estimated_qurban_ait": (
                    is_estimated_qurban
                ),
                "qurban_ait_status": (
                    qurban_info["status"]
                    if current_date
                    == qurban_info["date"]
                    else None
                ),
                "description": (
                    get_day_description(
                        current_date
                    )
                ),
            }
        )

    return pd.DataFrame(rows)