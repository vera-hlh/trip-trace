"""媒体文件元数据模型"""
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from app.core.database import Base


class MediaFile(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, default="local", nullable=False, index=True)  # Phase 4: 多用户预留
    original_path = Column(String, unique=True, nullable=False)
    current_path = Column(String)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)          # 'photo' | 'video'
    datetime_original = Column(String)                  # ISO8601 本地时间
    latitude = Column(Float)
    longitude = Column(Float)
    country = Column(String)
    province = Column(String)
    city = Column(String)
    district = Column(String)
    township = Column(String)                           # 乡镇（北极镇）← 精确行政区划
    poi = Column(String)                                # 景点/地标名
    poi_type = Column(String)                           # POI 类型字符串（如'风景名胜;风景名胜相关;旅游景点'）
    geocode_source = Column(String)                     # 'gaode' | 'offline' | None（未编码）
    remark_written = Column(Boolean, default=False)
    trip_id = Column(Integer, ForeignKey("trips.id"))
    has_gps = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)       # 无 GPS/时间文件标记
