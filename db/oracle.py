import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

ORACLE_USER = os.getenv("ORACLE_USER")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD")
ORACLE_HOST = os.getenv("ORACLE_HOST")
ORACLE_PORT = os.getenv("ORACLE_PORT")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE")

DATABASE_URL = (
    f"oracle+oracledb://{ORACLE_USER}:{ORACLE_PASSWORD}"
    f"@{ORACLE_HOST}:{ORACLE_PORT}/?service_name={ORACLE_SERVICE}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

print("Oracle user:", ORACLE_USER)
print("Oracle host:", ORACLE_HOST)