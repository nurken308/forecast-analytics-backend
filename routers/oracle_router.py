from fastapi import APIRouter, HTTPException
import pandas as pd

from db.oracle import engine
from service.oracle_sql_service import load_oracle_pivot

router = APIRouter(prefix="/oracle", tags=["Oracle"])


@router.get("/test")
def test_oracle():
    try:
        df = pd.read_sql("SELECT 1 AS test_value FROM dual", engine)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pivot/{segment_id}")
def get_pivot(segment_id: str):
    try:
        df = load_oracle_pivot(segment_id)
        return df.to_dict(orient="records")
    except Exception as e:
        return {
            "error_type": type(e).__name__,
            "error_short": str(e)[-1000:]
        }