"""
元数据提取模块单元测试

使用合成数据（无需真实照片/视频文件）测试核心逻辑：
  - GPS 坐标转换（度/分/秒 → 十进制）
  - ISO 6709 格式解析（视频 GPS）
  - EXIF 时间字符串解析
  - 时区转换（UTC → 本地）
  - 文件类型识别
  - 无 EXIF 照片的降级处理
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# 确保可以导入 app 包
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.metadata_service import (
    _convert_gps_to_decimal,
    _parse_iso6709,
    get_file_type,
    scan_folder,
    extract_metadata,
)
from app.utils.timezone_utils import (
    parse_exif_datetime,
    utc_to_local,
)


# ============================================================
# GPS 坐标转换测试
# ============================================================

class TestGpsConversion:

    def test_standard_degrees_minutes_seconds(self):
        """标准度/分/秒格式（北京天安门：39°54'14.57"N, 116°23'33.33"E）"""

        class Rational:
            def __init__(self, num, den):
                self.numerator = num
                self.denominator = den

        lat_dms = [Rational(39, 1), Rational(54, 1), Rational(1457, 100)]
        lon_dms = [Rational(116, 1), Rational(23, 1), Rational(3333, 100)]

        lat = _convert_gps_to_decimal(lat_dms)
        lon = _convert_gps_to_decimal(lon_dms)

        assert lat is not None
        assert lon is not None
        assert 39.9 < lat < 40.0
        assert 116.3 < lon < 116.5

    def test_float_tuple_format(self):
        """浮点数格式"""
        lat = _convert_gps_to_decimal([25.0, 1.0, 30.0])
        assert lat is not None
        assert abs(lat - 25.025) < 0.001

    def test_lijiang_coordinates(self):
        """丽江坐标（北纬 26.86，东经 100.23）"""
        lat = _convert_gps_to_decimal([26.0, 51.0, 36.0])
        lon = _convert_gps_to_decimal([100.0, 13.0, 48.0])
        assert lat is not None
        assert abs(lat - 26.86) < 0.01
        assert lon is not None
        assert abs(lon - 100.23) < 0.01

    def test_none_on_short_tuple(self):
        """坐标数据不完整时返回 None"""
        assert _convert_gps_to_decimal([25.0]) is None
        assert _convert_gps_to_decimal([]) is None

    def test_south_latitude(self):
        """南半球坐标（应用 -lat 修正，在调用方处理）"""
        lat = _convert_gps_to_decimal([33.0, 51.0, 54.0])  # 悉尼约 33°S
        assert lat is not None
        assert lat > 0  # 函数本身不处理 S/W，调用方负责取负


# ============================================================
# ISO 6709 GPS 解析测试
# ============================================================

class TestIso6709:

    def test_kunming_coordinates(self):
        """昆明坐标"""
        gps_str = "+25.0389+102.7183+1890/"
        lat, lon = _parse_iso6709(gps_str)
        assert lat is not None
        assert abs(lat - 25.0389) < 0.0001
        assert lon is not None
        assert abs(lon - 102.7183) < 0.0001

    def test_lijiang_coordinates(self):
        """丽江坐标"""
        gps_str = "+26.8721+100.2299+2400CRSWGS_84/"
        lat, lon = _parse_iso6709(gps_str)
        assert lat is not None
        assert abs(lat - 26.8721) < 0.0001

    def test_negative_coordinates(self):
        """南半球坐标"""
        gps_str = "-33.8688+151.2093/"
        lat, lon = _parse_iso6709(gps_str)
        assert lat is not None
        assert lat < 0
        assert abs(lat - (-33.8688)) < 0.0001

    def test_invalid_string(self):
        """无效字符串返回 None"""
        lat, lon = _parse_iso6709("no_gps_here")
        assert lat is None
        assert lon is None


# ============================================================
# 时间解析测试
# ============================================================

class TestDatetimeParsing:

    def test_standard_exif_format(self):
        """标准 EXIF 格式：'2025:09:10 09:23:00'"""
        dt = parse_exif_datetime("2025:09:10 09:23:00")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 9
        assert dt.day == 10
        assert dt.hour == 9
        assert dt.minute == 23

    def test_iso_format(self):
        """ISO 格式：'2025-09-10T09:23:00'"""
        dt = parse_exif_datetime("2025-09-10T09:23:00")
        assert dt is not None
        assert dt.year == 2025

    def test_none_on_empty(self):
        """空字符串返回 None"""
        assert parse_exif_datetime("") is None
        assert parse_exif_datetime(None) is None

    def test_none_on_invalid(self):
        """无效格式返回 None"""
        assert parse_exif_datetime("not_a_date") is None


# ============================================================
# 时区转换测试
# ============================================================

class TestTimezoneConversion:

    def test_utc_to_china(self):
        """UTC 转中国时间（+8）"""
        utc_dt = datetime(2025, 9, 10, 1, 23, 0, tzinfo=timezone.utc)
        # 北京坐标
        local_dt = utc_to_local(utc_dt, lat=39.9, lon=116.4)
        # 应该是 2025-09-10 09:23:00（+8）
        assert local_dt.year == 2025
        assert local_dt.month == 9
        assert local_dt.day == 10
        assert local_dt.hour == 9  # 1 + 8 = 9
        assert local_dt.minute == 23

    def test_utc_no_coords_fallback(self):
        """无坐标时使用默认 +8 时区"""
        utc_dt = datetime(2025, 9, 10, 0, 0, 0, tzinfo=timezone.utc)
        local_dt = utc_to_local(utc_dt)
        # 默认 Asia/Shanghai，UTC+8
        assert local_dt.hour == 8

    def test_naive_datetime_assumed_utc(self):
        """naive datetime 被视为 UTC"""
        naive_dt = datetime(2025, 9, 10, 0, 0, 0)  # 无时区
        local_dt = utc_to_local(naive_dt)
        assert local_dt.hour == 8  # 加 8 小时

    def test_timezone_info_stripped(self):
        """返回的 datetime 不含 tzinfo（naive）"""
        utc_dt = datetime(2025, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
        local_dt = utc_to_local(utc_dt)
        assert local_dt.tzinfo is None


# ============================================================
# 文件类型识别测试
# ============================================================

class TestFileTypeDetection:

    def test_photo_extensions(self):
        for ext in [".jpg", ".jpeg", ".PNG", ".heic", ".HEIF", ".tiff", ".webp"]:
            assert get_file_type(f"test{ext}") == "photo", f"Failed for {ext}"

    def test_video_extensions(self):
        for ext in [".mp4", ".mov", ".MOV", ".avi", ".mkv", ".m4v"]:
            assert get_file_type(f"test{ext}") == "video", f"Failed for {ext}"

    def test_unsupported_extensions(self):
        for ext in [".txt", ".pdf", ".zip", ".psd", ".xls"]:
            assert get_file_type(f"test{ext}") is None, f"Should be None for {ext}"


# ============================================================
# scan_folder 测试
# ============================================================

class TestScanFolder:

    def test_finds_photos_and_videos(self, tmp_path):
        """能找到照片和视频文件"""
        (tmp_path / "photo1.jpg").touch()
        (tmp_path / "photo2.JPEG").touch()
        (tmp_path / "video1.mp4").touch()
        (tmp_path / "document.txt").touch()   # 应被忽略
        (tmp_path / "archive.zip").touch()    # 应被忽略

        results = scan_folder(str(tmp_path))
        assert len(results) == 3
        filenames = [os.path.basename(p) for p in results]
        assert "photo1.jpg" in filenames
        assert "photo2.JPEG" in filenames
        assert "video1.mp4" in filenames
        assert "document.txt" not in filenames

    def test_recursive_scan(self, tmp_path):
        """能递归扫描子文件夹"""
        subdir = tmp_path / "2025-09-云南"
        subdir.mkdir()
        (tmp_path / "root.jpg").touch()
        (subdir / "sub.jpg").touch()

        results = scan_folder(str(tmp_path))
        assert len(results) == 2

    def test_skips_hidden_dirs(self, tmp_path):
        """跳过以点开头的隐藏目录"""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "photo.jpg").touch()
        (tmp_path / "visible.jpg").touch()

        results = scan_folder(str(tmp_path))
        assert len(results) == 1

    def test_empty_folder(self, tmp_path):
        """空文件夹返回空列表"""
        results = scan_folder(str(tmp_path))
        assert results == []


# ============================================================
# 无 EXIF 照片的降级处理测试
# ============================================================

class TestNoExifFallback:

    def test_png_without_exif(self, tmp_path):
        """没有 EXIF 的 PNG 文件应降级使用文件修改时间"""
        # 创建一个最小化的 PNG 文件（1x1 像素）
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x02, 0x00, 0x01, 0xE2, 0x21, 0xBC,
            0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
            0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        png_file = tmp_path / "test.png"
        png_file.write_bytes(png_data)

        result = extract_metadata(str(png_file))

        assert result is not None
        assert result.file_type == "photo"
        assert result.has_gps == False
        assert result.needs_review == True
        # 应该有一个降级的时间（文件修改时间）
        assert result.datetime_original is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
