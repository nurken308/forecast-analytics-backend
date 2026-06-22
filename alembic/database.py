from env_config import DB_USER, DB_PASS, DB_HOST, DB_NAME, DB_PORT
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from models.models import models_metadata

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_async_engine(DATABASE_URL)

models_metadata.bind = engine

async def create_tables():
    async with engine.begin() as connection:
        await connection.run_sync(models_metadata.create_all)

