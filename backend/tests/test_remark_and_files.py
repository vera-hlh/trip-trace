"""
Week 5 单元测试：备注写入 + 文件操作

测试：
  - format_remark() 备注模板格式化
  - write_remark() 对 JPEG 照片写入备注并读回验证
  - copy_file_safe() 安全复制（含冲突处理）
  - _resolve_conflict() 文件名冲突解决
  - ensure_dir() 目录创建
"""
import os
import sys
import shutil
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.remark_service import format_remark, write_remark, write_photo_remark
from app.utils.file_utils import (
    copy_file_safe,
    _resolve_conflict,
    ensure_dir,
    delete_file_safe,
    FileOperationResult,
)


# ============================================================
# 备注模板格式化测试
# ============================================================

class TestFormatRemark:

    def test_full_template(self):
        """完整模板：含国家/省/市/POI"""
        result = format_remark(
            "地点: {country}/{province}/{city}/{poi}",
            country="中国",
            province="云南省",
            city="昆明市",
            poi="石林风景区",
        )
        assert result == "地点: 中国/云南省/昆明市/石林风景区"

    def test_poi_falls_back_to_district(self):
        """POI 为空时用 district 替代"""
        result = format_remark(
            "地点: {country}/{province}/{city}/{poi}",
            country="中国",
            province="云南省",
            city="昆明市",
            district="石林彝族自治县",
            poi="",  # 空 POI
        )
        assert result == "地点: 中国/云南省/昆明市/石林彝族自治县"

    def test_trip_name_in_template(self):
        """包含行程名的模板"""
        result = format_remark(
            "地点: {city} | 行程: {trip_name} > {sub_trip_name}",
            city="昆明市",
            trip_name="2025-09_云南之旅",
            sub_trip_name="01_昆明_0910-0913",
        )
        assert "昆明市" in result
        assert "2025-09_云南之旅" in result

    def test_cleans_double_slash(self):
        """清理双斜杠"""
        result = format_remark(
            "地点: {country}/{province}/{city}/{poi}",
            country="中国",
            province="",  # 空省份
            city="昆明市",
            poi="石林",
        )
        # 不应该有 //
        assert "//" not in result

    def test_international_location(self):
        """国际地点（英文）"""
        result = format_remark(
            "Location: {country}/{city}",
            country="France",
            city="Paris",
        )
        assert result == "Location: France/Paris"


# ============================================================
# 照片备注写入测试（使用真实 JPEG 文件）
# ============================================================

class TestWritePhotoRemark:

    def create_minimal_jpeg(self, path: str) -> None:
        """创建最小化的 JPEG 文件（用于测试）"""
        from PIL import Image
        img = Image.new("RGB", (10, 10), color=(255, 100, 50))
        img.save(path, format="JPEG", quality=85)

    def test_write_and_read_back(self, tmp_path):
        """写入备注后读回验证内容正确"""
        import piexif

        jpg_file = str(tmp_path / "test.jpg")
        self.create_minimal_jpeg(jpg_file)

        remark = "地点: 中国/云南省/昆明市/石林风景区"
        result = write_photo_remark(jpg_file, remark)

        assert result.success is True, f"写入失败: {result.error}"

        # 读回验证
        exif_dict = piexif.load(jpg_file)
        user_comment_bytes = exif_dict["Exif"].get(piexif.ExifIFD.UserComment, b"")

        # 去掉 8 字节 null 头
        comment_text = user_comment_bytes[8:].decode("utf-8", errors="ignore")
        assert "石林风景区" in comment_text

    def test_remark_uses_utf8_null_header(self, tmp_path):
        """UserComment 使用 8 字节 null 编码头（支持中文）"""
        import piexif

        jpg_file = str(tmp_path / "utf8_test.jpg")
        self.create_minimal_jpeg(jpg_file)

        write_photo_remark(jpg_file, "测试备注")

        exif_dict = piexif.load(jpg_file)
        user_comment = exif_dict["Exif"].get(piexif.ExifIFD.UserComment, b"")

        # 验证是 null 编码头（8个0字节），而非 ASCII 头
        assert user_comment[:8] == b"\x00\x00\x00\x00\x00\x00\x00\x00"

    def test_write_to_nonexistent_file(self):
        """对不存在的文件写备注 → 返回失败"""
        result = write_remark("/nonexistent/path/file.jpg", "test")
        assert result.success is False

    def test_unsupported_format(self, tmp_path):
        """不支持的格式 → 返回失败"""
        txt_file = str(tmp_path / "test.txt")
        Path(txt_file).write_text("hello")

        result = write_remark(txt_file, "test")
        assert result.success is False
        assert "不支持" in result.error

    def test_backup_created_on_request(self, tmp_path):
        """create_backup=True 时创建 .bak 文件"""
        jpg_file = str(tmp_path / "backup_test.jpg")
        self.create_minimal_jpeg(jpg_file)

        result = write_photo_remark(jpg_file, "test remark", create_backup=True)

        assert result.success is True
        assert result.backup_path is not None
        assert os.path.exists(result.backup_path)
        assert result.backup_path.endswith(".bak")


# ============================================================
# 文件复制测试
# ============================================================

class TestCopyFileSafe:

    def test_basic_copy(self, tmp_path):
        """基本文件复制"""
        src = tmp_path / "source.jpg"
        src.write_bytes(b"test content")
        dst = str(tmp_path / "dest" / "output.jpg")

        result = copy_file_safe(str(src), dst)

        assert result.success is True
        assert os.path.exists(dst)
        assert Path(dst).read_bytes() == b"test content"

    def test_creates_target_directory(self, tmp_path):
        """自动创建目标目录（多级）"""
        src = tmp_path / "src.jpg"
        src.write_bytes(b"data")
        dst = str(tmp_path / "a" / "b" / "c" / "output.jpg")

        result = copy_file_safe(str(src), dst)

        assert result.success is True
        assert os.path.exists(dst)

    def test_conflict_rename(self, tmp_path):
        """同名文件存在时自动重命名"""
        src = tmp_path / "photo.jpg"
        src.write_bytes(b"original")
        dst = str(tmp_path / "output" / "photo.jpg")

        # 第一次复制
        result1 = copy_file_safe(str(src), dst)
        assert result1.success is True
        assert os.path.exists(dst)

        # 第二次复制（同路径），应自动重命名
        src2 = tmp_path / "photo2.jpg"
        src2.write_bytes(b"different")
        result2 = copy_file_safe(str(src2), dst, on_conflict="rename")

        assert result2.success is True
        assert result2.target_path != dst  # 路径应不同（重命名）
        assert os.path.exists(result2.target_path)

    def test_conflict_skip(self, tmp_path):
        """同名文件存在且设置 skip → 跳过，返回成功"""
        # 目标目录和已存在的文件
        dst_dir = tmp_path / "output"
        dst_dir.mkdir()
        dst = str(dst_dir / "photo.jpg")

        # 预先在目标位置放置文件
        Path(dst).write_bytes(b"original content")

        # 新的源文件（内容不同）
        src = tmp_path / "photo_new.jpg"
        src.write_bytes(b"new content")

        result = copy_file_safe(str(src), dst, on_conflict="skip")
        assert result.success is True  # 跳过视为成功
        # 目标文件内容未改变
        assert Path(dst).read_bytes() == b"original content"

    def test_source_not_found(self, tmp_path):
        """源文件不存在 → 返回失败"""
        result = copy_file_safe(
            "/nonexistent/source.jpg",
            str(tmp_path / "dst.jpg"),
        )
        assert result.success is False
        assert "不存在" in result.error


# ============================================================
# 冲突解决测试
# ============================================================

class TestResolveConflict:

    def test_adds_counter_suffix(self, tmp_path):
        """自动添加 _1 后缀"""
        existing = tmp_path / "photo.jpg"
        existing.touch()

        new_path = _resolve_conflict(str(existing))
        assert new_path.endswith("photo_1.jpg")
        assert not os.path.exists(new_path)

    def test_increments_counter(self, tmp_path):
        """已有 _1 时继续递增到 _2"""
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo_1.jpg").touch()

        new_path = _resolve_conflict(str(tmp_path / "photo.jpg"))
        assert new_path.endswith("photo_2.jpg")


# ============================================================
# 目录创建测试
# ============================================================

class TestEnsureDir:

    def test_creates_nested_dirs(self, tmp_path):
        """递归创建多级目录"""
        target = str(tmp_path / "a" / "b" / "c")
        ensure_dir(target)
        assert os.path.isdir(target)

    def test_existing_dir_no_error(self, tmp_path):
        """目录已存在不报错"""
        ensure_dir(str(tmp_path))  # 不应抛出异常


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
