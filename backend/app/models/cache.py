"""逆地理编码缓存模型"""
from sqlalchemy import Column, Integer, String, Float, UniqueConstraint
from app.core.database import Base


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lat_key = Column(Float, nullable=False)   # 精度截断至 3 位小数
    lon_key = Column(Float, nullable=False)
    country = Column(String)
    province = Column(String)
    city = Column(String)
    district = Column(String)
    poi = Column(String)
    source = Column(String)                   # 'offline' | 'gaode'
    cached_at = Column(String)

    __table_args__ = (UniqueConstraint("lat_key", "lon_key"),)
