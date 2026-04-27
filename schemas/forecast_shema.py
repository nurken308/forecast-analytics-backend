from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import date

class OLSForecastRequest(BaseModel):
    segment_name: str = Field(..., example="Розничный сегмент")

    periods: List[date] = Field(..., example=["2025-01-01", "2025-02-01"])
    target: List[float] = Field(..., example=[95000, 98000])

    drivers: Optional[Dict[str, List[float]]] = Field(
        default=None,
        example={
            "Рестр-ия": [1200, 1180],
            "Зона рисков": [5400, 5600]
        }
    )

    macro: Optional[Dict[str, Dict[date, float]]] = Field(
        default=None,
        example={
            "cpi": {
                "2025-01-01": 103.4,
                "2025-02-01": 103.7
            },
            "usdkzt": {
                "2025-01-01": 471.2,
                "2025-02-01": 469.8
            }
        }
    )

    horizon: int = Field(3, ge=1, le=12)
    future_start: Optional[date] = Field(None, example="2026-01-01")
    with_macro: bool = True