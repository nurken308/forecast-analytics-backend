from sqlalchemy.orm import declarative_base
from sqlalchemy import MetaData, Column, Integer, Numeric, String

models_metadata = MetaData()
Base = declarative_base(metadata=models_metadata)
 

class Prognoz(Base):
    __tablename__ = 'ezmes'
    metadata = models_metadata

    id = Column(Integer, primary_key = True)
    base_ymd = Column(String(8), nullable=False)
    od = Column(Numeric(20,2), nullable=False, server_default='0')
    prosrochka_1 = Column(Numeric(20,2), nullable=False, server_default='0')