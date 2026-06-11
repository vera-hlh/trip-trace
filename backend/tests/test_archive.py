"""
智能归档算法单元测试

测试场景：
  1. 基础行程切分（地点变化 + 时间 > 2h）
  2. 同地点合并（不切分）
  3. GPS 漂移过滤（地点变化但时间 < 30min）
  4. 大行程边界（时间间隔 > 30 天）
  5. 地点回归（A→B→A 模式，第二次 A 切分为新子行程）
  6. 模拟云南旅行（昆明→大理→丽江→香格里拉→昆明）
  7. 无时间文件处理
  8. 文件夹命名规则验证
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.archive_service import (
    ArchiveConfig,
    MediaItem,
    BigTrip,
    SubTrip,
    segment_into_trips,
    generate_archive_preview,
)


# ============================================================
# 测试辅助函数
# ============================================================

def make_item(
    filename: str,
    dt: datetime,
    city: str = "",
    location_key: str = "",
    has_gps: bool = True,
) -> MediaItem:
    """创建测试用 MediaItem"""
    return MediaItem(
        file_path=f"C:/Photos/{filename}",
        file_name=filename,
        datetime_original=dt,
        city=city,
        location_key=location_key or f"CN/云南省/{city}",
        has_gps=has_gps,
    )


def dt(year=2025, month=9, day=10, hour=9, minute=0) -> datetime:
    """快速创建 datetime"""
    return datetime(year, month, day, hour, minute, 0)


# ============================================================
# 基础行程切分测试
# ============================================================

class TestBasicSegmentation:

    def test_single_location_single_trip(self):
        """单一地点的照片归为一个子行程"""
        items = [
            make_item("01.jpg", dt(day=10, hour=9), city="昆明"),
            make_item("02.jpg", dt(day=10, hour=11), city="昆明"),
            make_item("03.jpg", dt(day=11, hour=9), city="昆明"),
        ]
        big_trips = segment_into_trips(items)
        assert len(big_trips) == 1
        assert len(big_trips[0].sub_trips) == 1
        assert big_trips[0].sub_trips[0].location_label == "昆明"
        assert big_trips[0].sub_trips[0].file_count == 3

    def test_two_locations_split(self):
        """两个地点（时间差 > 2h）→ 两个子行程"""
        items = [
            make_item("k1.jpg", dt(day=10, hour=9), city="昆明"),
            make_item("k2.jpg", dt(day=10, hour=11), city="昆明"),
            # 3小时后到大理
            make_item("d1.jpg", dt(day=10, hour=14), city="大理"),
            make_item("d2.jpg", dt(day=10, hour=16), city="大理"),
        ]
        big_trips = segment_into_trips(items)
        assert len(big_trips) == 1
        assert len(big_trips[0].sub_trips) == 2
        labels = [t.location_label for t in big_trips[0].sub_trips]
        assert "昆明" in labels
        assert "大理" in labels

    def test_location_change_within_threshold_merged(self):
        """地点变化但时间差 < 2h → 合并为同一子行程"""
        config = ArchiveConfig(small_trip_threshold_hours=2.0)
        items = [
            make_item("k1.jpg", dt(day=10, hour=9), city="昆明"),
            # 1.5h 后地点变化（短途）
            make_item("d1.jpg", dt(day=10, hour=10, minute=30), city="大理"),
        ]
        big_trips = segment_into_trips(items, config)
        # 时间差 1.5h < 2h，合并
        total_sub = sum(len(b.sub_trips) for b in big_trips)
        assert total_sub == 1


# ============================================================
# 同地点合并测试
# ============================================================

class TestSameLocationMerge:

    def test_same_location_always_merged(self):
        """同地点照片始终合并，无论时间间隔多大"""
        config = ArchiveConfig(small_trip_threshold_hours=2.0)
        items = [
            make_item("k1.jpg", dt(day=10, hour=9), city="昆明"),
            make_item("k2.jpg", dt(day=10, hour=11), city="昆明"),
            # 12小时后，同一地点
            make_item("k3.jpg", dt(day=10, hour=21), city="昆明"),
            # 次日
            make_item("k4.jpg", dt(day=11, hour=9), city="昆明"),
        ]
        big_trips = segment_into_trips(items, config)
        assert len(big_trips) == 1
        assert len(big_trips[0].sub_trips) == 1  # 全部合并为一个昆明行程
        assert big_trips[0].sub_trips[0].file_count == 4

    def test_same_location_different_days_merged(self):
        """昆明3天，全部合并"""
        items = [
            make_item(f"k{i}.jpg", dt(day=10 + i // 3, hour=9 + (i % 3) * 3), city="昆明")
            for i in range(9)
        ]
        big_trips = segment_into_trips(items)
        assert len(big_trips[0].sub_trips) == 1


# ============================================================
# GPS 漂移过滤测试
# ============================================================

class TestGpsDriftFilter:

    def test_short_location_change_filtered(self):
        """短时间（< 30min）的地点变化视为 GPS 漂移"""
        config = ArchiveConfig(gps_drift_threshold_hours=0.5)
        items = [
            make_item("k1.jpg", dt(day=10, hour=9, minute=0), city="昆明"),
            # 20分钟后，GPS 漂移到"大理"（不合理，应过滤）
            make_item("drift.jpg", dt(day=10, hour=9, minute=20), city="大理"),
            make_item("k2.jpg", dt(day=10, hour=9, minute=40), city="昆明"),
        ]
        big_trips = segment_into_trips(items, config)
        # 漂移应被过滤，仍为 1 个子行程
        assert len(big_trips[0].sub_trips) == 1


# ============================================================
# 大行程切分测试
# ============================================================

class TestBigTripSplit:

    def test_30_days_gap_creates_new_big_trip(self):
        """时间间隔 > 30 天 → 新大行程"""
        config = ArchiveConfig(big_trip_threshold_days=30)
        items = [
            make_item("sep1.jpg", dt(month=9, day=10), city="昆明"),
            make_item("sep2.jpg", dt(month=9, day=15), city="大理"),
            # 50天后
            make_item("nov1.jpg", dt(month=11, day=5), city="北京"),
        ]
        big_trips = segment_into_trips(items, config)
        assert len(big_trips) == 2
        assert big_trips[0].year == 2025
        assert big_trips[0].month == 9
        assert big_trips[1].month == 11

    def test_within_30_days_same_big_trip(self):
        """25 天内 → 同一大行程"""
        config = ArchiveConfig(big_trip_threshold_days=30)
        items = [
            make_item("a1.jpg", dt(month=9, day=10), city="昆明"),
            make_item("a2.jpg", dt(month=9, day=20), city="大理"),  # 10天后
            make_item("a3.jpg", dt(month=10, day=3), city="丽江"),  # 13天后，共23天
        ]
        big_trips = segment_into_trips(items, config)
        assert len(big_trips) == 1


# ============================================================
# 地点回归测试（A→B→A 模式）
# ============================================================

class TestLocationReturn:

    def test_location_return_creates_new_sub_trip(self):
        """昆明→大理→昆明：第二次昆明为新子行程"""
        items = [
            # 第一次昆明（Day 1-3）
            make_item("k1.jpg", dt(day=10, hour=9), city="昆明"),
            make_item("k2.jpg", dt(day=11, hour=9), city="昆明"),
            # 大理（Day 4-5）
            make_item("d1.jpg", dt(day=13, hour=14), city="大理"),
            make_item("d2.jpg", dt(day=14, hour=9), city="大理"),
            # 第二次昆明（Day 6）
            make_item("k3.jpg", dt(day=16, hour=14), city="昆明"),
        ]
        big_trips = segment_into_trips(items)
        assert len(big_trips) == 1

        sub_labels = [t.location_label for t in big_trips[0].sub_trips]
        # 应该有 3 个子行程：昆明①、大理、昆明②
        assert len(sub_labels) == 3
        assert sub_labels[0] == "昆明"
        assert sub_labels[1] == "大理"
        assert sub_labels[2] == "昆明"


# ============================================================
# 模拟云南旅行全程测试（核心场景验证）
# ============================================================

class TestYunnanTrip:
    """
    模拟 2025年9月 云南旅行：
    行程：昆明(10-13日) → 大理(13-15日) → 丽江(15-17日) → 香格里拉(17-19日) → 昆明(19-20日)
    预期：5个子行程，地点回归（两次昆明）分开
    """

    def build_yunnan_items(self) -> list[MediaItem]:
        """构建模拟云南旅行照片列表"""
        items = []

        # 昆明第一次（9月10-13日）
        for day in range(10, 13):
            for hour in [9, 12, 15]:
                items.append(make_item(f"km1_{day}_{hour}.jpg",
                                       datetime(2025, 9, day, hour), city="昆明"))

        # 大理（9月13-15日，从昆明出发后 4h 到达）
        items.append(make_item("km_last.jpg", datetime(2025, 9, 13, 8), city="昆明"))
        for day in range(13, 15):
            for hour in [14, 16, 18]:
                items.append(make_item(f"dali_{day}_{hour}.jpg",
                                       datetime(2025, 9, day, hour), city="大理"))

        # 丽江（9月15-17日）
        for day in range(15, 17):
            for hour in [9, 14, 18]:
                items.append(make_item(f"lj_{day}_{hour}.jpg",
                                       datetime(2025, 9, day, hour), city="丽江"))

        # 香格里拉（9月17-19日）
        for day in range(17, 19):
            for hour in [9, 14, 18]:
                items.append(make_item(f"xlgl_{day}_{hour}.jpg",
                                       datetime(2025, 9, day, hour), city="香格里拉"))

        # 昆明第二次（9月19-20日）
        for day in range(19, 21):
            for hour in [9, 15]:
                items.append(make_item(f"km2_{day}_{hour}.jpg",
                                       datetime(2025, 9, day, hour), city="昆明"))

        return items

    def test_yunnan_creates_one_big_trip(self):
        """整个云南行程应为 1 个大行程"""
        items = self.build_yunnan_items()
        big_trips = segment_into_trips(items)
        assert len(big_trips) == 1
        assert big_trips[0].year == 2025
        assert big_trips[0].month == 9

    def test_yunnan_has_5_sub_trips(self):
        """云南行程应有 5 个子行程（包含两次昆明）"""
        items = self.build_yunnan_items()
        big_trips = segment_into_trips(items)
        sub_trips = big_trips[0].sub_trips

        assert len(sub_trips) == 5

    def test_yunnan_sub_trip_order(self):
        """子行程顺序：昆明①→大理→丽江→香格里拉→昆明②"""
        items = self.build_yunnan_items()
        big_trips = segment_into_trips(items)
        labels = [t.location_label for t in big_trips[0].sub_trips]

        assert labels[0] == "昆明"
        assert labels[1] == "大理"
        assert labels[2] == "丽江"
        assert labels[3] == "香格里拉"
        assert labels[4] == "昆明"

    def test_yunnan_sub_trip_sequence_numbers(self):
        """子行程序号从 1 开始连续编号"""
        items = self.build_yunnan_items()
        big_trips = segment_into_trips(items)
        for i, sub in enumerate(big_trips[0].sub_trips, start=1):
            assert sub.sequence_num == i

    def test_yunnan_folder_names(self):
        """验证文件夹命名格式"""
        items = self.build_yunnan_items()
        big_trips = segment_into_trips(items)

        big = big_trips[0]
        # 大行程文件夹含年月
        assert "2025-09" in big.folder_name

        # 子行程文件夹格式：序号_地点_MMDD-MMDD
        for sub in big.sub_trips:
            name = sub.trip_name
            assert name.startswith(f"{sub.sequence_num:02d}_")
            assert sub.location_label in name


# ============================================================
# 无时间文件测试
# ============================================================

class TestNoTimestampFiles:

    def test_no_time_files_handled(self):
        """无时间戳的文件不影响正常处理"""
        items = [
            make_item("k1.jpg", dt(day=10, hour=9), city="昆明"),
            MediaItem(  # 无时间的截图
                file_path="C:/Photos/screenshot.png",
                file_name="screenshot.png",
                datetime_original=None,
                has_gps=False,
            ),
            make_item("k2.jpg", dt(day=10, hour=11), city="昆明"),
        ]
        big_trips = segment_into_trips(items)
        # 不应报错
        assert len(big_trips) >= 1
        total_files = sum(sub.file_count for b in big_trips for sub in b.sub_trips)
        assert total_files == 3  # 含无时间文件

    def test_all_no_time_files(self):
        """全部无时间文件 → 生成待分类行程"""
        items = [
            MediaItem(file_path=f"C:/p/{i}.png", file_name=f"{i}.png",
                      datetime_original=None, has_gps=False)
            for i in range(3)
        ]
        big_trips = segment_into_trips(items)
        assert len(big_trips) == 1
        assert "待分类" in big_trips[0].sub_trips[0].location_label


# ============================================================
# 归档预览测试
# ============================================================

class TestArchivePreview:

    def test_preview_generates_correct_paths(self):
        """预览生成的目标路径格式正确"""
        items = [
            make_item("IMG_001.jpg", dt(day=10, hour=9), city="昆明"),
        ]
        big_trips = segment_into_trips(items)
        preview = generate_archive_preview(big_trips, output_base="C:/归档")

        assert len(preview) == 1
        item = preview[0]

        assert "C:/归档" in item.target_path
        assert "2025-09" in item.target_path
        assert "昆明" in item.target_path
        assert "IMG_001.jpg" in item.target_path
        assert item.original_path == "C:/Photos/IMG_001.jpg"

    def test_preview_total_count_matches(self):
        """预览中的文件数量与输入一致"""
        items = [
            make_item(f"{i:03d}.jpg", dt(day=10 + i // 5, hour=9 + i % 5), city="昆明")
            for i in range(10)
        ]
        big_trips = segment_into_trips(items)
        preview = generate_archive_preview(big_trips, "C:/归档")
        assert len(preview) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
