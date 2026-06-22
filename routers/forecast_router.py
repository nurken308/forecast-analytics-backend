from fastapi import APIRouter, HTTPException
import pathlib
from service.ols_forecast import load_macro, fit_segment_model, forecast_segment
from schemas.forecast_shema import SimpleForecastRequest
from service.refresh_service import refresh_forecast, get_saved_forecast

router = APIRouter(
    prefix="/OLS",
)

@router.post("/forecast")
def ols_forecast(payload: SimpleForecastRequest):
    segment_id = payload.segment_id

    base_dir = pathlib.Path(__file__).resolve().parent.parent

    seg_paths = {
        "retail": {
            "name": "Розница",
            "path": base_dir / "Розница.xlsx",
        },
        "mass": {
            "name": "Масс Продукты",
            "path": base_dir / "Масс продукты.xlsx",
        },
        "bk_vkl": {
            "name": "БК + ВКЛ",
            "path": base_dir / "БК+ВКЛ.xlsx",
        },
    }

    if segment_id not in seg_paths:
        raise HTTPException(status_code=400, detail="Unknown segment")

    segment = seg_paths[segment_id]

    macro_path = base_dir / "НСТ.xlsx"
    macro = load_macro(macro_path)

    seg_model = fit_segment_model(
        name=segment["name"],
        seg_path=segment["path"],
        macro=macro,
        with_macro=True
    )

    preds = forecast_segment(
        seg_model,
        macro=macro,
        horizon=3
    )

    return {
        "segment_id": segment_id,
        "segment_name": segment["name"],
        "r2_adj": round(seg_model.model.rsquared_adj, 4),
        "features": seg_model.columns,
        "coefficients": {
            k: round(v, 4)
            for k, v in seg_model.model.params.items()
        },
        "forecast": [
            {"date": d.strftime("%Y-%m-%d"), "value": round(v, 2)}
            for d, v in preds
        ]
    }

@router.get("/forecast-cache/{segment_id}")
def forecast_cache(segment_id: str):
    return get_saved_forecast(segment_id)


@router.post("/refresh/{segment_id}")
def refresh(segment_id: str):
    return refresh_forecast(segment_id, force=True)