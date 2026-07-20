import time

import requests


API_URL = "http://10.20.70.241:8000"
BASE_YMD = "20260714"
REQUEST_TIMEOUT = 900

SEGMENTS = [
    "retail",
    "bk",
    "bk_soft",
    "vkl",
    "vkl_soft",
    "rb_z_ip",
    "rb_z_ip_soft",
    "rb_z_too",
    "rb_bz_ip",
    "rb_bz_too",
]


def main():
    print("=" * 72)
    print(f"ПРИНУДИТЕЛЬНЫЙ ПЕРЕСЧЁТ DAILY НА {BASE_YMD}")
    print("=" * 72)

    errors = []

    for index, segment_id in enumerate(SEGMENTS, start=1):
        url = (
            f"{API_URL}/daily-forecast/"
            f"force-recalculate/{segment_id}/{BASE_YMD}"
        )

        print(
            f"[{index}/{len(SEGMENTS)}] "
            f"{segment_id:15} ...",
            end=" ",
            flush=True,
        )

        try:
            response = requests.post(
                url,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            result = response.json()

            if result.get("status") != "success":
                errors.append(
                    {
                        "segment_id": segment_id,
                        "result": result,
                    }
                )
                print(f"❌ {result}")
            else:
                recalculation = result.get(
                    "recalculation",
                    {},
                )

                print(
                    f"✅ old_run={recalculation.get('old_run_id')} | "
                    f"new_run={recalculation.get('new_run_id')} | "
                    f"correction={recalculation.get('peak_correction')}"
                )

        except Exception as error:
            errors.append(
                {
                    "segment_id": segment_id,
                    "error": str(error),
                }
            )
            print(f"❌ {error}")

        time.sleep(1)

    print()
    print("=" * 72)
    print(f"Завершено. Ошибок: {len(errors)}")
    print("=" * 72)

    if errors:
        for item in errors:
            print(
                f"- {item['segment_id']}: "
                f"{item.get('error') or item.get('result')}"
            )


if __name__ == "__main__":
    main()