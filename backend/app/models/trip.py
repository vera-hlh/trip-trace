"""行程信息模型"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.core.database import Base


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, default="local", nullable=False, index=True)  # Phase 4: 多用户预留
    trip_name = Column(String, nullable=False)           # 例：01_昆明_0910-0913
    display_name = Column(String)                        # 用户自定义名称
    start_date = Column(String, nullable=False)          # ISO8601 日期
    end_date = Column(String, nullable=False)
    parent_trip_id = Column(Integer, ForeignKey("trips.id"))  # 大行程 ID
    sequence_num = Column(Integer)                       # 子行程序号
    location_label = Column(String)                      # 主要地点标签
    user_merged = Column(Boolean, default=False)         # 是否用户手动合并
