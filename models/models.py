from sqlalchemy.orm import declarative_base
from sqlalchemy import MetaData, Column, Integer, Numeric, String, DateTime, ForeignKey
from sqlalchemy import DateTime, ForeignKey, Date, Text
from sqlalchemy.orm import relationship
from sqlalchemy import DateTime
from datetime import datetime
from sqlalchemy import Boolean, JSON, ForeignKey

models_metadata = MetaData()
Base = declarative_base(metadata=models_metadata)
 

class Prognoz(Base):
    __tablename__ = 'ezmes'
    metadata = models_metadata

    id = Column(Integer, primary_key=True)
    segment_id = Column(String(50), nullable=False, server_default="retail")
    base_ymd = Column(String(8), nullable=False)
    od = Column(Numeric(20, 2), nullable=False, server_default='0')
    prosrochka_1 = Column(Numeric(20, 2), nullable=False, server_default='0')

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    metadata = models_metadata

    id = Column(Integer, primary_key=True)
    forecast_type = Column(String(50), nullable=False)  # monthly / daily / provision
    segment_id = Column(String(50), nullable=False)     # retail / mass / bk_vkl
    model_name = Column(String(100), nullable=False)
    horizon_months = Column(Integer, nullable=False, server_default="3")
    status = Column(String(30), nullable=False, server_default="active")  # active / archived
    parent_run_id = Column(Integer, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    values = relationship("ForecastValue", back_populates="run")


class ForecastValue(Base):
    __tablename__ = "forecast_values"
    metadata = models_metadata

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id"), nullable=False)

    period_month = Column(String(10), nullable=False)  # 2026-06
    forecast_value = Column(Numeric(20, 2), nullable=False)
    fact_value = Column(Numeric(20, 2), nullable=True)

    abs_error = Column(Numeric(20, 2), nullable=True)
    pct_error = Column(Numeric(10, 4), nullable=True)

    status = Column(String(30), nullable=False, server_default="planned")  # planned / fact_available

    run = relationship("ForecastRun", back_populates="values")

class CalendarJob(Base):
    __tablename__ = "calendar_jobs"
    metadata = models_metadata

    id = Column(Integer, primary_key=True)

    module = Column(String(50), nullable=False)          # forecast_monthly / forecast_daily / provision
    segment_id = Column(String(50), nullable=False)      # retail / mass / bk_vkl
    target_period = Column(String(20), nullable=False)   # 2026-07 / 2026-07-02

    base_ymd = Column(String(8), nullable=False)         # 20260731

    status = Column(String(30), nullable=False, server_default="waiting")
    # waiting / loaded / failed / skipped

    last_check_at = Column(DateTime, nullable=True)
    next_check_at = Column(DateTime, nullable=True)
    loaded_at = Column(DateTime, nullable=True)

    error_message = Column(String(1000), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class ForecastModel(Base):
    __tablename__ = "forecast_models"
    metadata = models_metadata

    id = Column(Integer, primary_key=True)

    model_code = Column(String(100), unique=True, nullable=False)
    model_name = Column(String(200), nullable=False)

    forecast_type = Column(String(50), nullable=False)     # monthly / daily / provision
    segment_id = Column(String(50), nullable=False)        # retail / mass / bk_vkl

    algorithm = Column(String(100), nullable=False)        # OLS / Ridge / NeuralProphet / XGBoost
    version = Column(String(30), nullable=False)

    description = Column(String(1000), nullable=True)

    horizon_months = Column(Integer, nullable=False, default=3)
    parameters_json = Column(JSON, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class ForecastModelVersion(Base):
    __tablename__ = "forecast_model_versions"
    metadata = models_metadata

    id = Column(Integer, primary_key=True)

    model_id = Column(Integer, ForeignKey("forecast_models.id"), nullable=False)

    algorithm = Column(String(100), nullable=False)       # OLS / Ridge / NeuralProphet / XGBoost
    version = Column(String(30), nullable=False)          # 1.0 / 2.0

    description = Column(String(1000), nullable=True)
    parameters_json = Column(JSON, nullable=True)

    horizon_months = Column(Integer, nullable=False, default=3)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)