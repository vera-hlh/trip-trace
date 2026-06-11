"""
逆地理编码服务（三层优化方案）

第一层：网格缓存快查
  - (lat, lon) 截断至 3 位小数（约 100m 精度）作为 key
  - 命中缓存 → 直接返回，0 次外部调用

第二层：POI 聚类中心距离判定（懒加载）
  - 距离当前行程已有 POI 中心 ≤ 500m 且 时间差 ≤ 2h → 归入同一 POI
  - 典型结果：1000 张照片只需 5-10 次在线 API 调用

第三层：高德地图 API（可选，需 Key）
  - 仅在切换景点时触发
  - 离线无法获取具体景点名（POI），需在线增强
"""
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 数据结构
# ============================================================

@dataclass
class GeoLocation:
    """逆地理编码结果"""
    country: str = ""
    country_code: str = ""  # "CN", "JP" 等
    province: str = ""      # 省/州
    city: str = ""          # 市
    district: str = ""      # 区县
    poi: str = ""           # 景点名称（需在线 API）
    source: str = "offline" # "offline" | "gaode"

    @property
    def is_china(self) -> bool:
        return self.country_code.upper() in ("CN", "CHN", "CHINA")

    def to_remark_path(self) -> str:
        """生成备注路径字符串"""
        parts = [p for p in [self.country, self.province, self.city, self.poi or self.district] if p]
        return "/".join(parts)


# ============================================================
# 第一层：离线逆地理编码（reverse_geocoder）
# ============================================================

# 懒加载 reverse_geocoder（数据文件较大，首次加载耗时约 0.5s）
_rg = None


def _get_reverse_geocoder():
    global _rg
    if _rg is None:
        try:
            import reverse_geocoder
            _rg = reverse_geocoder
        except ImportError:
            logger.error("reverse_geocoder 未安装，请运行: pip install reverse_geocoder")
    return _rg


def reverse_geocode_offline(lat: float, lon: float) -> Optional[GeoLocation]:
    """
    离线逆地理编码（全球覆盖）

    返回国家、省、市信息。对于中国地点，城市名为英文拼音，
    中文名需通过额外处理或在线 API 获取。

    Args:
        lat: 纬度
        lon: 经度

    Returns:
        GeoLocation 对象，失败返回 None
    """
    rg = _get_reverse_geocoder()
    if rg is None:
        return None

    try:
        results = rg.search([(lat, lon)], verbose=False)
        if not results:
            return None

        r = results[0]
        # reverse_geocoder 返回字段：
        # name: 城市名, admin1: 省/州, admin2: 区县, cc: 国家代码
        return GeoLocation(
            country=_country_code_to_name(r.get("cc", "")),
            country_code=r.get("cc", ""),
            province=r.get("admin1", ""),
            city=r.get("name", ""),
            district=r.get("admin2", ""),
            source="offline",
        )
    except Exception as e:
        logger.warning(f"reverse_geocoder 查询失败 ({lat}, {lon}): {e}")
        return None


def _country_code_to_name(cc: str) -> str:
    """将 ISO 国家代码转为中文国家名（常用国家）"""
    mapping = {
        "CN": "中国", "JP": "日本", "KR": "韩国", "US": "美国",
        "GB": "英国", "FR": "法国", "DE": "德国", "IT": "意大利",
        "AU": "澳大利亚", "CA": "加拿大", "TH": "泰国", "SG": "新加坡",
        "MY": "马来西亚", "VN": "越南", "ID": "印度尼西亚", "PH": "菲律宾",
        "IN": "印度", "NP": "尼泊尔", "NZ": "新西兰", "MX": "墨西哥",
    }
    return mapping.get(cc.upper(), cc)


# ============================================================
# 第三层（可选）：高德地图 API（在线增强，获取 POI 景点名）
# ============================================================

async def reverse_geocode_gaode(
    lat: float,
    lon: float,
    api_key: str,
) -> Optional[GeoLocation]:
    """
    高德地图逆地理编码（在线，获取精确中文地址和景点名）

    仅用于第三层（POI 聚类触发新查询时）

    Args:
        lat: 纬度
        lon: 经度
        api_key: 高德 API Key

    Returns:
        GeoLocation 对象（含中文省市区和 POI 名），失败返回 None
    """
    if not api_key:
        return None

    try:
        import httpx
        # 高德 API 坐标格式：经度,纬度
        url = (
            f"https://restapi.amap.com/v3/geocode/regeo"
            f"?output=json&location={lon},{lat}&key={api_key}"
            f"&radius=1000&extensions=all"
        )
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            data = resp.json()

        if data.get("status") != "1":
            logger.warning(f"高德 API 返回错误: {data.get('info')}")
            return None

        regeocode = data.get("regeocode", {})
        address_comp = regeocode.get("addressComponent", {})

        province = address_comp.get("province", "")
        city = address_comp.get("city", "")
        district = address_comp.get("district", "")

        # 直辖市（如北京、上海）city 字段为空数组，用 province 代替
        if not city or city == []:
            city = province

        # 获取最近景点 POI
        pois = regeocode.get("pois", [])
        poi_name = pois[0].get("name", "") if pois else ""

        return GeoLocation(
            country="中国",
            country_code="CN",
            province=province if isinstance(province, str) else "",
            city=city if isinstance(city, str) else "",
            district=district if isinstance(district, str) else "",
            poi=poi_name,
            source="gaode",
        )

    except Exception as e:
        logger.warning(f"高德 API 查询失败 ({lat}, {lon}): {e}")
        return None


# ============================================================
# POI 聚类（第二层懒加载核心逻辑）
# ============================================================

def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    计算两点之间的 Haversine 距离（单位：米）
    """
    R = 6371000  # 地球半径（米）
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class PoiClusterState:
    """
    内存中的 POI 聚类状态（在单次扫描任务中使用）

    用于 POI 懒加载聚类：同一大行程内，距离相近 + 时间相近的照片
    复用同一 POI，不重复调用 API。
    """
    poi_name: str
    city: str
    center_lat: float
    center_lon: float
    radius_m: float = 500.0
    file_count: int = 0
    last_datetime: Optional[datetime] = None

    def matches(
        self,
        lat: float,
        lon: float,
        dt: Optional[datetime] = None,
        time_threshold_hours: float = 2.0,
    ) -> bool:
        """
        判断新照片是否属于此 POI 聚类

        同时满足：
          - 距聚类中心 ≤ radius_m 米
          - 时间差 ≤ time_threshold_hours 小时（若有时间信息）
        """
        dist = haversine_distance_m(self.center_lat, self.center_lon, lat, lon)
        if dist > self.radius_m:
            return False

        if dt and self.last_datetime:
            hours_diff = abs((dt - self.last_datetime).total_seconds()) / 3600
            if hours_diff > time_threshold_hours:
                return False

        return True

    def update_center(self, lat: float, lon: float, dt: Optional[datetime] = None):
        """加权平均更新聚类中心"""
        n = self.file_count
        self.center_lat = (self.center_lat * n + lat) / (n + 1)
        self.center_lon = (self.center_lon * n + lon) / (n + 1)
        self.file_count += 1
        if dt:
            self.last_datetime = dt


# ============================================================
# 统一入口函数
# ============================================================

async def get_location(
    lat: float,
    lon: float,
    dt: Optional[datetime] = None,
    gaode_api_key: str = "",
    poi_clusters: Optional[list[PoiClusterState]] = None,
    time_threshold_hours: float = 2.0,
) -> tuple[GeoLocation, bool]:
    """
    三层逆地理编码统一入口

    Args:
        lat: 纬度
        lon: 经度
        dt: 照片拍摄时间（用于 POI 聚类时间判断）
        gaode_api_key: 高德 API Key（空则跳过第三层）
        poi_clusters: 当前行程的 POI 聚类列表（None 则不做聚类）
        time_threshold_hours: POI 聚类时间阈值（小时）

    Returns:
        (GeoLocation, api_called)
        api_called: 是否调用了在线 API（用于统计 API 消耗）
    """
    # 第二层：检查是否命中已有 POI 聚类
    if poi_clusters is not None:
        for cluster in poi_clusters:
            if cluster.matches(lat, lon, dt, time_threshold_hours):
                cluster.update_center(lat, lon, dt)
                # 直接返回聚类的地理信息
                return GeoLocation(
                    country="中国" if cluster.city else "",
                    city=cluster.city,
                    poi=cluster.poi_name,
                    source="offline",
                ), False

    # 第一层：离线查询（获取省市信息）
    location = reverse_geocode_offline(lat, lon)
    if location is None:
        location = GeoLocation()

    api_called = False

    # 第三层：在线 API 增强（获取 POI 景点名）
    if gaode_api_key and location.is_china:
        online_loc = await reverse_geocode_gaode(lat, lon, gaode_api_key)
        if online_loc:
            # 合并：优先使用高德的中文地名
            location.province = online_loc.province or location.province
            location.city = online_loc.city or location.city
            location.district = online_loc.district or location.district
            location.poi = online_loc.poi
            location.source = "gaode"
            api_called = True

    # 创建新的 POI 聚类
    if poi_clusters is not None:
        new_cluster = PoiClusterState(
            poi_name=location.poi or location.city,
            city=location.city,
            center_lat=lat,
            center_lon=lon,
            last_datetime=dt,
            file_count=1,
        )
        poi_clusters.append(new_cluster)

    return location, api_called


# ============================================================
# 缓存键工具
# ============================================================

def make_cache_key(lat: float, lon: float) -> tuple[float, float]:
    """
    生成地理编码缓存键（截断至 3 位小数，约 100m 精度）

    >>> make_cache_key(25.0389, 102.7183)
    (25.039, 102.718)
    """
    return round(lat, 3), round(lon, 3)
