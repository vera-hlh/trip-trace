"""
逆地理编码服务单元测试

测试：
  - Haversine 距离计算
  - POI 聚类匹配逻辑
  - 聚类中心加权更新
  - 缓存键生成
  - 离线 reverse_geocoder（真实 API 调用，需网络）
  - 国家代码转中文名
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.geocode_service import (
    GeoLocation,
    PoiClusterState,
    haversine_distance_m,
    make_cache_key,
    reverse_geocode_offline,
    _country_code_to_name,
)


# ============================================================
# Haversine 距离测试
# ============================================================

class TestHaversineDistance:

    def test_same_point_is_zero(self):
        """同一点距离为 0"""
        d = haversine_distance_m(25.04, 102.72, 25.04, 102.72)
        assert d == 0.0

    def test_kunming_to_dali(self):
        """昆明到大理约 300km"""
        # 昆明约 (25.04, 102.72)，大理约 (25.60, 100.27)
        d = haversine_distance_m(25.04, 102.72, 25.60, 100.27)
        # 约 280-320km
        assert 250_000 < d < 350_000

    def test_nearby_points_within_500m(self):
        """同一景区内两个点距离 < 500m"""
        # 石林景区内两个点（约 200m 距离）
        d = haversine_distance_m(24.770, 103.270, 24.772, 103.272)
        assert d < 500

    def test_different_cities_over_1km(self):
        """不同城市之间距离 > 1km"""
        # 昆明到丽江约 480km
        d = haversine_distance_m(25.04, 102.72, 26.87, 100.22)
        assert d > 1000


# ============================================================
# POI 聚类测试
# ============================================================

class TestPoiClusterState:

    def make_cluster(self, lat=25.04, lon=102.72, poi="石林风景区", city="昆明"):
        return PoiClusterState(
            poi_name=poi,
            city=city,
            center_lat=lat,
            center_lon=lon,
            last_datetime=datetime(2025, 9, 10, 9, 0, 0),
        )

    def test_nearby_same_time_matches(self):
        """距离近且时间接近 → 匹配"""
        cluster = self.make_cluster()
        # 同一景区内，300m 外，1小时后
        dt = datetime(2025, 9, 10, 10, 0, 0)
        assert cluster.matches(25.042, 102.723, dt) is True

    def test_far_away_no_match(self):
        """距离太远 → 不匹配"""
        cluster = self.make_cluster()
        # 大理坐标
        dt = datetime(2025, 9, 10, 10, 0, 0)
        assert cluster.matches(25.60, 100.27, dt) is False

    def test_too_long_ago_no_match(self):
        """时间差超过 2h → 不匹配"""
        cluster = self.make_cluster()
        # 距离近但超过 3 小时
        dt = datetime(2025, 9, 10, 12, 0, 0)  # 3h 后
        # 即使距离很近（50m），时间差 > 2h 不匹配
        assert cluster.matches(25.0402, 102.7204, dt, time_threshold_hours=2.0) is False

    def test_time_within_threshold_matches(self):
        """时间在阈值内 → 匹配"""
        cluster = self.make_cluster()
        dt = datetime(2025, 9, 10, 10, 59, 0)  # 1h59m 后
        assert cluster.matches(25.042, 102.723, dt, time_threshold_hours=2.0) is True

    def test_no_datetime_ignores_time_check(self):
        """无时间信息时，只按距离判断"""
        cluster = self.make_cluster()
        # 无 dt，只要距离满足就匹配
        assert cluster.matches(25.042, 102.723, dt=None) is True

    def test_update_center_weighted_average(self):
        """聚类中心加权更新"""
        cluster = PoiClusterState(
            poi_name="test",
            city="昆明",
            center_lat=25.0,
            center_lon=102.0,
            file_count=0,
        )
        # 第一个点
        cluster.update_center(25.0, 102.0)
        assert cluster.file_count == 1
        assert cluster.center_lat == 25.0

        # 第二个点（偏移）
        cluster.update_center(25.1, 102.1)
        assert cluster.file_count == 2
        assert abs(cluster.center_lat - 25.05) < 0.001  # 加权平均

    def test_custom_radius(self):
        """自定义聚类半径"""
        cluster = PoiClusterState(
            poi_name="test", city="昆明",
            center_lat=25.0, center_lon=102.0,
            radius_m=200.0,  # 缩小到 200m
        )
        # 300m 外的点不匹配
        assert cluster.matches(25.003, 102.0, dt=None) is False


# ============================================================
# 缓存键测试
# ============================================================

class TestCacheKey:

    def test_truncates_to_3_decimal(self):
        """截断至 3 位小数"""
        key = make_cache_key(25.03891234, 102.71835678)
        assert key == (25.039, 102.718)

    def test_negative_coordinates(self):
        """负坐标（南半球/西半球）"""
        key = make_cache_key(-33.8688, 151.2093)
        assert key == (-33.869, 151.209)

    def test_same_nearby_points_get_same_key(self):
        """同一 100m 网格内的两点应该得到相同缓存键"""
        # round(25.0389, 3)=25.039, round(25.0391, 3)=25.039（4位小数为1，向下舍）
        # round(102.7183, 3)=102.718, round(102.7184, 3)=102.718
        key1 = make_cache_key(25.0389, 102.7183)
        key2 = make_cache_key(25.0391, 102.7184)  # 同一 3 位小数网格，相差约 25m
        assert key1 == key2

    def test_different_grid_cells_different_key(self):
        """相差超过 100m 时缓存键不同"""
        key1 = make_cache_key(25.0389, 102.7183)  # → (25.039, 102.718)
        key2 = make_cache_key(25.0389, 102.7197)  # → (25.039, 102.720)
        assert key1 != key2


# ============================================================
# 国家代码转中文名测试
# ============================================================

class TestCountryCodeToName:

    def test_china(self):
        assert _country_code_to_name("CN") == "中国"

    def test_japan(self):
        assert _country_code_to_name("JP") == "日本"

    def test_unknown_returns_code(self):
        """未知代码直接返回"""
        assert _country_code_to_name("ZZ") == "ZZ"

    def test_case_insensitive(self):
        """大小写不敏感"""
        assert _country_code_to_name("cn") == "中国"
        assert _country_code_to_name("Cn") == "中国"


# ============================================================
# GeoLocation 辅助方法测试
# ============================================================

class TestGeoLocation:

    def test_is_china(self):
        loc = GeoLocation(country_code="CN")
        assert loc.is_china is True

    def test_not_china(self):
        loc = GeoLocation(country_code="JP")
        assert loc.is_china is False

    def test_remark_path_with_poi(self):
        """含 POI 的备注路径"""
        loc = GeoLocation(
            country="中国",
            province="云南省",
            city="昆明市",
            poi="石林风景区",
        )
        assert loc.to_remark_path() == "中国/云南省/昆明市/石林风景区"

    def test_remark_path_without_poi(self):
        """无 POI 时用 district 替代"""
        loc = GeoLocation(
            country="中国",
            province="云南省",
            city="昆明市",
            district="石林彝族自治县",
        )
        assert loc.to_remark_path() == "中国/云南省/昆明市/石林彝族自治县"

    def test_remark_path_empty_fields_skipped(self):
        """空字段被跳过"""
        loc = GeoLocation(country="中国", city="昆明市")
        assert loc.to_remark_path() == "中国/昆明市"


# ============================================================
# 离线逆地理编码集成测试
# ============================================================

class TestReverseGeocodeOffline:
    """
    注：这些测试需要 reverse_geocoder 已安装
    首次运行会加载 GeoNames 数据文件（约 0.5s）
    """

    def test_kunming_china(self):
        """昆明坐标 → 中国"""
        loc = reverse_geocode_offline(25.04, 102.72)
        assert loc is not None
        assert loc.country_code == "CN"
        assert "Yunnan" in loc.province or "云南" in loc.province

    def test_paris_france(self):
        """巴黎坐标 → 法国"""
        loc = reverse_geocode_offline(48.8566, 2.3522)
        assert loc is not None
        assert loc.country_code == "FR"

    def test_sydney_australia(self):
        """悉尼坐标 → 澳大利亚"""
        loc = reverse_geocode_offline(-33.8688, 151.2093)
        assert loc is not None
        assert loc.country_code == "AU"

    def test_lijiang_is_china(self):
        """丽江坐标 → 中国云南"""
        loc = reverse_geocode_offline(26.87, 100.23)
        assert loc is not None
        assert loc.is_china is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
