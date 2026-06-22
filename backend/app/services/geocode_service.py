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
    district: str = ""      # 区/县（漠河市）
    township: str = ""      # 乡镇（北极镇）← 新增：行政区划，无需半径搜索
    poi: str = ""           # 景点/地标名称（需在线 API）
    source: str = "offline" # "offline" | "gaode"

    @property
    def is_china(self) -> bool:
        return self.country_code.upper() in ("CN", "CHN", "CHINA")

    @property
    def best_location_label(self) -> str:
        """
        返回最具体的位置标签（用于归档文件夹命名）
        优先级：POI > 乡镇 > 区县 > 城市
        """
        return self.poi or self.township or self.district or self.city

    def to_remark_path(self) -> str:
        """
        生成备注路径字符串
        层级：省份 → 城市 → 区县/乡镇 → POI
        """
        parts = []
        if self.province:
            parts.append(self.province)
        if self.city and self.city != self.province:
            parts.append(self.city)
        if self.district and self.district != self.city:
            parts.append(self.district)
        if self.township:
            parts.append(self.township)
        if self.poi:
            parts.append(self.poi)
        return "/".join(parts) if parts else self.city


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
        "RU": "俄罗斯", "MN": "蒙古",
    }
    return mapping.get(cc.upper(), cc)


# 中国省份英文→中文映射
_PROVINCE_MAP: dict[str, str] = {
    "Beijing Shi": "北京市", "Tianjin Shi": "天津市", "Shanghai Shi": "上海市",
    "Chongqing Shi": "重庆市",
    "Hebei Sheng": "河北省", "Shanxi Sheng": "山西省", "Liaoning Sheng": "辽宁省",
    "Jilin Sheng": "吉林省", "Heilongjiang Sheng": "黑龙江省",
    "Jiangsu Sheng": "江苏省", "Zhejiang Sheng": "浙江省", "Anhui Sheng": "安徽省",
    "Fujian Sheng": "福建省", "Jiangxi Sheng": "江西省", "Shandong Sheng": "山东省",
    "Henan Sheng": "河南省", "Hubei Sheng": "湖北省", "Hunan Sheng": "湖南省",
    "Guangdong Sheng": "广东省", "Hainan Sheng": "海南省",
    "Sichuan Sheng": "四川省", "Guizhou Sheng": "贵州省", "Yunnan Sheng": "云南省",
    "Shaanxi Sheng": "陕西省", "Gansu Sheng": "甘肃省", "Qinghai Sheng": "青海省",
    "Nei Mongol Zizhiqu": "内蒙古自治区", "Guangxi Zhuangzu Zizhiqu": "广西壮族自治区",
    "Xizang Zizhiqu": "西藏自治区", "Ningxia Huizu Zizhiqu": "宁夏回族自治区",
    "Xinjiang Uygur Zizhiqu": "新疆维吾尔自治区",
    "Hong Kong": "香港", "Macao": "澳门",
}

# 中国城市英文→中文映射（主要城市 + 旅游目的地）
_CITY_MAP: dict[str, str] = {
    # 东北
    "Harbin": "哈尔滨", "Shenyang": "沈阳", "Dalian": "大连",
    "Changchun": "长春", "Jilin": "吉林", "Mudanjiang": "牡丹江",
    "Qiqihar": "齐齐哈尔", "Daqing": "大庆", "Jiamusi": "佳木斯",
    "Xilinji": "西林吉", "Mohe": "漠河",
    "Erdaobaihe": "二道白河", "Baihe": "白河", "Sandao": "三道",
    "Manjiang": "漫江", "Fusong": "抚松",
    # 华北
    "Beijing": "北京", "Tianjin": "天津", "Shijiazhuang": "石家庄",
    "Taiyuan": "太原", "Hohhot": "呼和浩特", "Baotou": "包头",
    # 华东
    "Shanghai": "上海", "Nanjing": "南京", "Hangzhou": "杭州",
    "Suzhou": "苏州", "Wuxi": "无锡", "Ningbo": "宁波",
    "Hefei": "合肥", "Fuzhou": "福州", "Xiamen": "厦门",
    "Jinan": "济南", "Qingdao": "青岛", "Nanchang": "南昌",
    # 华南
    "Guangzhou": "广州", "Shenzhen": "深圳", "Zhuhai": "珠海",
    "Dongguan": "东莞", "Foshan": "佛山", "Nanning": "南宁",
    "Haikou": "海口", "Sanya": "三亚",
    # 西南
    "Chengdu": "成都", "Chongqing": "重庆", "Kunming": "昆明",
    "Guiyang": "贵阳", "Lhasa": "拉萨", "Dali": "大理",
    "Lijiang": "丽江", "Shangri-La": "香格里拉", "Zhongdian": "中甸",
    "Xishuangbanna": "西双版纳", "Jinghong": "景洪",
    # 西北
    "Xi'an": "西安", "Lanzhou": "兰州", "Xining": "西宁",
    "Yinchuan": "银川", "Urumqi": "乌鲁木齐",
    # 华中
    "Wuhan": "武汉", "Zhengzhou": "郑州", "Changsha": "长沙",
    # 直辖市/特别
    "Hong Kong": "香港", "Macao": "澳门",
}


def translate_cn_location(city: str, province: str) -> tuple[str, str]:
    """
    将英文城市/省份名翻译为中文（中国境内）
    同时生成"城市 (City)" 双语格式

    Returns:
        (中文城市名, 中文省份名) 或原始英文（若无对应翻译）
    """
    cn_city = _CITY_MAP.get(city, city)
    cn_province = _PROVINCE_MAP.get(province, province)
    return cn_city, cn_province


# ============================================================
# 第三层（可选）：高德地图 API（在线增强，获取 POI 景点名）
# ============================================================

# ── 旅行相关 POI 类型代码（用于 poitype 参数过滤） ─────────────
# 文档来源：高德 POI 分类编码 V1.06（2023-02）
_TRAVEL_POI_TYPES = "|".join([
    "110000",  # 风景名胜（含公园、国家景点、世遗、寺庙、海滩等全部子类）
    "190700",  # 热点地名
    "190600",  # 标志性建筑物
    "190200",  # 自然地名（山、湖、峡谷、冰川、岛屿…）
    "150200",  # 火车站（旅行重要节点，如漠河站）← 新增
    "190106",  # 乡镇级地名（北极镇等）← 注：通过 addressComponent.township 更精确，这里作为 POI 补充
    "140100",  # 博物馆
    "140200",  # 展览馆
    "140400",  # 美术馆
    "080400",  # 度假疗养场所
    "080500",  # 休闲场所（游乐场、露营地）
    "061000",  # 特色商业街（步行街）
    "190108",  # 村庄级地名（网红村庄：乌镇、西塘、西江苗寨等）
])

# ── POI 优先级（前缀匹配，从高到低）────────────────────────────
_POI_PRIORITY_PREFIXES = [
    "1102",    # 风景名胜（国家/省级景点、世界遗产、寺庙道观、海滩…）
    "1907",    # 热点地名
    "1906",    # 标志性建筑物
    "1902",    # 自然地名（山/湖/峡谷/冰川…）
    "1101",    # 公园广场
    "1502",    # 火车站（旅行重要节点，150200前缀）
    "1401",    # 博物馆
    "1402",    # 展览馆
    "1404",    # 美术馆
    "0804",    # 度假疗养场所
    "0610",    # 特色商业街
    "0805",    # 休闲场所
]
# 特定精确匹配类型码（最低优先级，不在前缀列表中）
_VILLAGE_TYPECODE = "190108"


def _select_best_travel_poi(pois: list) -> str:
    """
    从高德返回的 pois 列表中，按优先级选出最佳旅行相关 POI 名称。

    优先级：风景名胜 > 热点地名 > 标志性建筑 > 自然地名 >
           博物馆/展览馆 > 度假地 > 商业街 > 休闲场所 > 村庄

    若无旅行相关 POI，返回空字符串（调用方显示到城市级别即可）。
    """
    if not pois:
        return ""

    # 按优先级前缀匹配
    for prefix in _POI_PRIORITY_PREFIXES:
        for poi in pois:
            typecode = str(poi.get("typecode", ""))
            if typecode.startswith(prefix):
                name = poi.get("name", "").strip()
                if name:
                    return name

    # 最低优先级：村庄级地名（精确匹配）
    for poi in pois:
        if str(poi.get("typecode", "")) == _VILLAGE_TYPECODE:
            name = poi.get("name", "").strip()
            if name:
                return name

    return ""  # 无旅行相关 POI


async def reverse_geocode_gaode(
    lat: float,
    lon: float,
    api_key: str,
) -> Optional[GeoLocation]:
    """
    高德地图逆地理编码（在线，获取精确中文地址和旅行相关 POI 景点名）

    改进：
      - coordsys=gps：正确处理 WGS-84 坐标（避免偏移）
      - poitype 过滤：只返回旅行相关 POI（风景名胜/自然地名/热点/村庄等）
      - 优先级选择：按景点重要性排序，取最相关的 POI
      - 层级精简：国家→省份→城市→POI（跳过区县）

    Args:
        lat: 纬度
        lon: 经度
        api_key: 高德 API Key

    Returns:
        GeoLocation 对象（含中文省市和 POI 名），失败返回 None
    """
    if not api_key:
        return None

    try:
        import httpx
        # coordsys=gps：输入为 WGS-84，高德内部自动转换到 GCJ-02
        # radius=2000：平衡城市密集区与农村稀疏区（township 字段不依赖半径）
        # poitype：只请求旅行相关 POI 类型
        url = (
            f"https://restapi.amap.com/v3/geocode/regeo"
            f"?output=json&location={lon},{lat}&key={api_key}"
            f"&radius=2000&extensions=all&coordsys=gps"
            f"&poitype={_TRAVEL_POI_TYPES}"
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
        # ⭐ 关键：township 是精确的行政区划（如北极镇），不依赖半径搜索
        # 城市密集区有 township，农村/山区也有 township，无论半径大小都能精确命中
        township_raw = address_comp.get("township", "")
        township = township_raw if isinstance(township_raw, str) else ""

        # 直辖市（北京/上海/天津/重庆）city 字段为空数组，用 province 代替
        if not city or city == []:
            city = province

        # 按优先级选择最佳旅行相关 POI（若无则为空字符串）
        pois = regeocode.get("pois", [])
        poi_name = _select_best_travel_poi(pois)

        return GeoLocation(
            country="中国",
            country_code="CN",
            province=province if isinstance(province, str) else "",
            city=city if isinstance(city, str) else "",
            district=district if isinstance(district, str) else "",
            township=township,          # 乡镇级行政区（精确，无需搜索半径）
            poi=poi_name,               # 景点/地标（依赖搜索，可能为空）
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
# 中国地理范围边界框判断（兜底，修复边境离线库误判）
# ============================================================

def _is_in_china_bbox(lat: float, lon: float) -> bool:
    """
    判断坐标是否在中国地理范围边界框内（粗略矩形判断）。

    用于修复 reverse_geocoder 在中俄/中蒙/中越等边境地区的误判问题：
    例如漠河北极镇坐标可能被离线库识别为俄罗斯 Yerofey Pavlovich，
    但实际坐标在中国境内 → 需调用高德 API 获取正确中文地名。

    范围参考（含港澳台、含黑龙江最北端、含新疆南疆）：
      经度：73.0°E ~ 135.5°E
      纬度：17.5°N ~ 53.6°N
    """
    return 73.0 <= lon <= 135.5 and 17.5 <= lat <= 53.6


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
    #
    # 触发条件：配置了高德 Key，且坐标在中国范围内。
    # 注意：is_china 依赖离线库的国家判断，在中俄边境等地区可能误判为境外
    # （如漠河北极镇被误识别为俄罗斯 Yerofey Pavlovich）。
    # 因此额外用坐标边界框兜底：只要经纬度落在中国范围内就调用高德 API。
    in_china = location.is_china or _is_in_china_bbox(lat, lon)
    if gaode_api_key and in_china:
        online_loc = await reverse_geocode_gaode(lat, lon, gaode_api_key)
        if online_loc:
            # 合并：优先使用高德的中文地名
            location.province = online_loc.province or location.province
            location.city = online_loc.city or location.city
            location.district = online_loc.district or location.district
            location.township = online_loc.township  # 乡镇级行政区（精确，来自高德 addressComponent）
            location.poi = online_loc.poi
            location.source = "gaode"
            location.country = "中国"
            location.country_code = "CN"
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
