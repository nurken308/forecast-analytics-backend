from fastapi import APIRouter
from schemas.forecast_shema import OLSForecastRequest
import pathlib
from service.ols_forecast import load_macro, fit_segment_model, forecast_segment

router = APIRouter(
    prefix="/OLS",
)

@router.post("/forecast")
def ols_forecast():
    """
    Triggers OLS forecast using internal Excel files.
    No input parameters.
    Returns numeric results only.
    """

    base_dir = pathlib.Path(__file__).resolve().parent.parent

    seg_paths = {
        "Розничный сегмент": base_dir / "Розница.xlsx",
        "Масс продукты": base_dir / "Масс продукты.xlsx",
        "БК+ВКЛ": base_dir / "БК+ВКЛ.xlsx",
    }

    macro_path = base_dir / "НСТ.xlsx"
    macro = load_macro(macro_path)

    results = {}

    for name, path in seg_paths.items():
        seg_model = fit_segment_model(
            name=name,
            seg_path=path,
            macro=macro,
            with_macro=True
        )

        preds = forecast_segment(
            seg_model,
            macro=macro,
            horizon=3
        )

        results[name] = {
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

    return results