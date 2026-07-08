from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.forecast_router import router as forecast_router
from routers.oracle_router import router as oracle_router
from routers.postgres_router import router as postgres_router
from routers.monthly_forecast_router import router as monthly_forecast_router

app = FastAPI()

app.include_router(forecast_router)
app.include_router(oracle_router)
app.include_router(postgres_router)
app.include_router(monthly_forecast_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)