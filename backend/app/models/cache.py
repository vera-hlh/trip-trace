"""逆地理编码缓存 + POI 聚类模型"""
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, UniqueConstraint
from app.core.database import Base


class GeocodeCache(Base):
    """
    第一层缓存：网格快查
    将 (lat, lon) 截断至小数点后 3 位（约 100m 精度）作为 key
    命中缓存则直接返回，0 次 API 调用
    """
    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lat_key = Column(Float, nullable=False)   # 精度截断至 3 位小数（约 100m 网格）
    lon_key = Column(Float, nullable=False)
    country = Column(String)
    province = Column(String)
    city = Column(String)
    district = Column(String)
    poi = Column(String)
    source = Column(String)                   # 'offline' | 'gaode'
    cached_at = Column(String)

    __table_args__ = (UniqueConstraint("lat_key", "lon_key"),)


class PoiCluster(Base):
    """
    第二层缓存：POI 聚类懒加载
    
    按时间 + 距离双因子聚类，将同一大行程内时间相近、位置相近的照片归为同一景点。
    仅在切换景点时触发高德 API，典型场景下 1000 张照片只需 5-10 次 API 调用。
    
    聚类规则（均可配置）：
      - 距离阈值：center_lat/center_lon 到新照片坐标 ≤ radius_m（默认 500m）
      - 时间阈值：与聚类内最新照片时间差 ≤ 小行程切分阈值（默认 2h）
      - 满足双因子 → 归入当前聚类，更新聚类中心（加权平均）
      - 不满足 → 触发新的高德 API 查询，创建新聚类
    """
    __tablename__ = "poi_clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"))  # 关联大行程
    poi_name = Column(String)                           # 景点名称（来自高德 API）
    city = Column(String)                               # 所属城市
    center_lat = Column(Float, nullable=False)          # 聚类中心纬度（加权平均，动态更新）
    center_lon = Column(Float, nullable=False)          # 聚类中心经度
    radius_m = Column(Float, default=500.0)             # 聚类半径阈值（米，可配置）
    file_count = Column(Integer, default=0)             # 归入该 POI 的照片/视频数
    api_call_triggered = Column(Boolean, default=True)  # 是否触发过高德 API 查询（监控用）
    created_at = Column(String)
