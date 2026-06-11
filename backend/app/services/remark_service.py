"""
文件备注写入服务

将地理位置信息写入照片/视频的"备注"字段，不修改其他元数据。

照片（JPEG/TIFF 等）：
  - 写入 EXIF UserComment（编码：8字节null头 + UTF-8）
  - 写入 EXIF ImageDescription（可选）
  
视频（MP4/MOV 等）：
  - 写入 ©cmt 标签（mutagen）

备注格式示例：
  "地点: 中国/云南省/昆明市/石林风景区\n行程: 2025-09_云南之旅 > 01_昆明_0910-0913"
"""
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RemarkResult:
    """备注写入结果"""
    file_path: str
    success: bool
    error: Optional[str] = None
    backup_path: Optional[str] = None  # 写入前备份路径（如果创建了备份）


# ============================================================
# 照片备注写入
# ============================================================

def write_photo_remark(
    file_path: str,
    remark_text: str,
    create_backup: bool = False,
) -> RemarkResult:
    """
    将备注写入照片的 EXIF UserComment 字段

    Args:
        file_path: 照片文件路径
        remark_text: 备注文本（支持中文）
        create_backup: 是否在写入前创建 .bak 备份

    Returns:
        RemarkResult 对象
    """
    backup_path = None

    try:
        import piexif
        from PIL import Image

        # 可选：创建备份
        if create_backup:
            backup_path = file_path + ".bak"
            shutil.copy2(file_path, backup_path)

        # 读取现有 EXIF
        try:
            exif_dict = piexif.load(file_path)
        except Exception:
            # 某些文件可能没有 EXIF，创建空的
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

        # 确保字典键存在
        if "Exif" not in exif_dict:
            exif_dict["Exif"] = {}

        # UserComment 编码规范：
        # 正确：8字节 null 头（undefined 类型）+ UTF-8 内容
        # 错误：b"ASCII\0\0\0" + 内容（不支持中文）
        encoded_remark = b"\x00\x00\x00\x00\x00\x00\x00\x00" + remark_text.encode("utf-8")
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = encoded_remark

        # 同时写入 ImageDescription（通用性更好，Android 相册支持）
        if "0th" not in exif_dict:
            exif_dict["0th"] = {}
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = remark_text.encode("utf-8")

        # 生成新的 EXIF bytes
        new_exif_bytes = piexif.dump(exif_dict)

        # 保存（使用 PIL 保持图片质量）
        with Image.open(file_path) as img:
            img.save(file_path, exif=new_exif_bytes, quality="keep")

        return RemarkResult(
            file_path=file_path,
            success=True,
            backup_path=backup_path,
        )

    except ImportError as e:
        return RemarkResult(file_path=file_path, success=False, error=f"依赖未安装: {e}")
    except Exception as e:
        logger.warning(f"写入照片备注失败 {file_path}: {e}")
        # 如果创建了备份且写入失败，尝试还原
        if backup_path and os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, file_path)
                os.remove(backup_path)
            except Exception:
                pass
        return RemarkResult(file_path=file_path, success=False, error=str(e))


# ============================================================
# 视频备注写入
# ============================================================

def write_video_remark(
    file_path: str,
    remark_text: str,
    create_backup: bool = False,
) -> RemarkResult:
    """
    将备注写入视频文件的 ©cmt 标签

    支持格式：MP4, MOV, M4V（mutagen MP4 格式）

    Args:
        file_path: 视频文件路径
        remark_text: 备注文本
        create_backup: 是否创建 .bak 备份

    Returns:
        RemarkResult 对象
    """
    backup_path = None

    try:
        from mutagen.mp4 import MP4

        if create_backup:
            backup_path = file_path + ".bak"
            shutil.copy2(file_path, backup_path)

        video = MP4(file_path)
        video["©cmt"] = [remark_text]
        video.save()

        return RemarkResult(
            file_path=file_path,
            success=True,
            backup_path=backup_path,
        )

    except ImportError as e:
        return RemarkResult(file_path=file_path, success=False, error=f"依赖未安装: {e}")
    except Exception as e:
        # 尝试其他格式
        try:
            from mutagen import File as MutagenFile
            f = MutagenFile(file_path)
            if f is not None and hasattr(f, "tags") and f.tags is not None:
                f.tags["comment"] = remark_text
                f.save()
                return RemarkResult(file_path=file_path, success=True, backup_path=backup_path)
        except Exception as e2:
            logger.warning(f"写入视频备注失败 {file_path}: {e2}")

        if backup_path and os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, file_path)
                os.remove(backup_path)
            except Exception:
                pass
        return RemarkResult(file_path=file_path, success=False, error=str(e))


# ============================================================
# 备注内容格式化
# ============================================================

def format_remark(
    template: str,
    country: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    poi: str = "",
    trip_name: str = "",
    sub_trip_name: str = "",
) -> str:
    """
    使用模板格式化备注文本

    默认模板示例：
      "地点: {country}/{province}/{city}/{poi}"
      → "地点: 中国/云南省/昆明市/石林风景区"

    Args:
        template: 备注模板（支持 {country}, {province}, {city}, {district}, {poi}, {trip_name}, {sub_trip_name}）

    Returns:
        格式化后的备注字符串
    """
    result = template.format(
        country=country,
        province=province,
        city=city,
        district=district,
        poi=poi or district,  # POI 为空时用 district 替代
        trip_name=trip_name,
        sub_trip_name=sub_trip_name,
    )
    # 清理末尾多余的斜杠
    result = result.replace("//", "/").rstrip("/")
    return result.strip()


# ============================================================
# 统一入口
# ============================================================

def write_remark(
    file_path: str,
    remark_text: str,
    create_backup: bool = False,
) -> RemarkResult:
    """
    根据文件类型自动选择备注写入方式

    Args:
        file_path: 文件路径
        remark_text: 备注文本
        create_backup: 是否创建备份

    Returns:
        RemarkResult 对象
    """
    from app.services.metadata_service import PHOTO_EXTENSIONS, VIDEO_EXTENSIONS

    ext = Path(file_path).suffix.lower()

    if ext in PHOTO_EXTENSIONS:
        return write_photo_remark(file_path, remark_text, create_backup)
    elif ext in VIDEO_EXTENSIONS:
        return write_video_remark(file_path, remark_text, create_backup)
    else:
        return RemarkResult(
            file_path=file_path,
            success=False,
            error=f"不支持的文件格式: {ext}",
        )
