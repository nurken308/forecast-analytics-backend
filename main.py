from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.forecast_router import router as forecast_router

app = FastAPI()
app.include_router(forecast_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)