"""
媒体文件元数据提取服务

支持格式：
  照片：JPEG, PNG, HEIC/HEIF, TIFF, WebP, RAW 系列
  视频：MP4, MOV, AVI, MKV, M4V

提取内容：
  - 拍摄时间（DateTimeOriginal 优先，无 EXIF 则用文件修改时间）
  - GPS 坐标（十进制度数）
  - 文件类型分类（photo / video）
  - 是否有 GPS 标记
  - 是否需要人工审核（无时间 + 无 GPS）
"""
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 支持的照片扩展名
PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tiff", ".tif", ".webp", ".bmp",
    ".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng",
}

# 支持的视频扩展名
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".m4v",
    ".wmv", ".flv", ".webm", ".3gp", ".ts",
}


@dataclass
class MediaFileData:
    """提取出来的媒体文件元数据"""
    file_path: str
    file_name: str
    file_type: str              # "photo" | "video"
    file_size_bytes: int = 0

    datetime_original: Optional[datetime] = None  # 本地时间
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    has_gps: bool = False
    needs_review: bool = False  # 无 GPS 且无可靠时间

    error: Optional[str] = None  # 提取过程中的错误信息


def get_file_type(file_path: str) -> Optional[str]:
    """判断文件类型，返回 'photo'、'video' 或 None（不支持的格式）"""
    ext = Path(file_path).suffix.lower()
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def scan_folder(folder_path: str) -> list[str]:
    """
    递归扫描文件夹，返回所有支持的媒体文件路径列表
    """
    media_files = []
    all_extensions = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS

    for root, dirs, files in os.walk(folder_path):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            ext = Path(filename).suffix.lower()
            if ext in all_extensions:
                media_files.append(os.path.join(root, filename))

    return sorted(media_files)


# ============================================================
# 照片元数据提取
# ============================================================

def _convert_gps_to_decimal(gps_value) -> Optional[float]:
    """
    将 EXIF GPS 坐标（度/分/秒）转为十进制度数

    gps_value 可能是：
      - list/tuple of IFDRational: [(d_num, d_den), (m_num, m_den), (s_num, s_den)]
      - list/tuple of float-like: [d, m, s]
    """
    try:
        if len(gps_value) < 3:
            return None

        def to_float(v):
            if hasattr(v, "numerator"):
                return v.numerator / v.denominator if v.denominator != 0 else 0.0
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        d = to_float(gps_value[0])
        m = to_float(gps_value[1])
        s = to_float(gps_value[2])
        return d + m / 60.0 + s / 3600.0
    except Exception:
        return None


def extract_photo_metadata(file_path: str) -> MediaFileData:
    """
    提取照片的 EXIF 元数据

    Returns:
        MediaFileData 对象，包含时间和 GPS 信息
    """
    result = MediaFileData(
        file_path=file_path,
        file_name=os.path.basename(file_path),
        file_type="photo",
        file_size_bytes=os.path.getsize(file_path),
    )

    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        with Image.open(file_path) as img:
            # 尝试获取 EXIF 数据
            exif_data = None

            # 方式一：_getexif()（大多数 JPEG）
            if hasattr(img, "_getexif"):
                try:
                    exif_data = img._getexif()
                except Exception:
                    pass

            # 方式二：getexif()（PIL >= 6.0，支持更多格式）
            if not exif_data:
                try:
                    raw = img.getexif()
                    if raw:
                        exif_data = {k: v for k, v in raw.items()}
                except Exception:
                    pass

            if not exif_data:
                # 无 EXIF，使用文件修改时间作为降级方案
                result.datetime_original = _get_file_mtime(file_path)
                result.needs_review = True
                return result

            # 提取拍摄时间（DateTimeOriginal 优先）
            dt_str = None
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, "")
                if tag_name == "DateTimeOriginal":
                    dt_str = str(value)
                    break
                elif tag_name == "DateTime" and not dt_str:
                    dt_str = str(value)

            if dt_str:
                from app.utils.timezone_utils import parse_exif_datetime
                result.datetime_original = parse_exif_datetime(dt_str)

            if not result.datetime_original:
                result.datetime_original = _get_file_mtime(file_path)

            # 提取 GPS 信息
            gps_info = {}
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, "")
                if tag_name == "GPSInfo":
                    for gps_tag_id, gps_value in value.items():
                        gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                        gps_info[gps_tag_name] = gps_value
                    break

            if gps_info:
                lat = _convert_gps_to_decimal(gps_info.get("GPSLatitude"))
                lon = _convert_gps_to_decimal(gps_info.get("GPSLongitude"))

                if lat is not None and lon is not None:
                    lat_ref = gps_info.get("GPSLatitudeRef", "N")
                    lon_ref = gps_info.get("GPSLongitudeRef", "E")

                    if str(lat_ref).upper() == "S":
                        lat = -lat
                    if str(lon_ref).upper() == "W":
                        lon = -lon

                    result.latitude = round(lat, 7)
                    result.longitude = round(lon, 7)
                    result.has_gps = True

    except ImportError:
        result.error = "Pillow 未安装"
    except Exception as e:
        logger.warning(f"提取照片元数据失败 {file_path}: {e}")
        result.error = str(e)
        # 降级：使用文件时间
        result.datetime_original = _get_file_mtime(file_path)
        result.needs_review = True

    # 有时间但无 GPS，标记为待审核（不是错误，只是需要关注）
    if not result.has_gps:
        result.needs_review = True

    return result


# ============================================================
# 视频元数据提取
# ============================================================

def _parse_iso6709(gps_str: str) -> tuple[Optional[float], Optional[float]]:
    """
    解析 ISO 6709 格式的 GPS 字符串
    例如："+27.9878+086.9263+8850CRSWGS_84/"
         "+39.9042+116.4074+43/"
    """
    # 匹配格式：+DD.dddd+DDD.dddd 或 -DD.dddd-DDD.dddd
    pattern = r"([+-]\d+\.?\d*)([+-]\d+\.?\d*)"
    match = re.search(pattern, gps_str)
    if match:
        try:
            lat = float(match.group(1))
            lon = float(match.group(2))
            return lat, lon
        except ValueError:
            pass
    return None, None


def extract_video_metadata(file_path: str) -> MediaFileData:
    """
    提取视频文件的元数据（创建时间 + GPS）

    注意：视频的 creation_time 通常是 UTC 时间，需要转换为本地时间
    """
    result = MediaFileData(
        file_path=file_path,
        file_name=os.path.basename(file_path),
        file_type="video",
        file_size_bytes=os.path.getsize(file_path),
    )

    try:
        import mutagen
        from mutagen.mp4 import MP4

        media = mutagen.File(file_path)
        if media is None:
            result.datetime_original = _get_file_mtime(file_path)
            result.needs_review = True
            return result

        creation_time_str = None
        lat, lon = None, None

        # ---- MP4/MOV 格式 ----
        if isinstance(media, MP4):
            # 创建时间：©day 标签（部分设备写入）
            if "©day" in media:
                creation_time_str = media["©day"][0]

            # 苹果 QuickTime GPS 标签（iPhone 视频）
            qt_gps_key = "----:com.apple.quicktime.location.ISO6709"
            if qt_gps_key in media:
                try:
                    gps_bytes = media[qt_gps_key][0]
                    if hasattr(gps_bytes, "value"):
                        gps_str = gps_bytes.value.decode("utf-8", errors="ignore")
                    else:
                        gps_str = bytes(gps_bytes).decode("utf-8", errors="ignore")
                    lat, lon = _parse_iso6709(gps_str)
                except Exception as e:
                    logger.debug(f"解析 QuickTime GPS 失败: {e}")

        # ---- 其他格式，尝试通用标签 ----
        else:
            for key in ("creation_time", "date", "year"):
                if hasattr(media, "tags") and media.tags and key in media.tags:
                    val = media.tags[key]
                    creation_time_str = str(val[0]) if isinstance(val, list) else str(val)
                    break

        # 解析创建时间（ISO 格式或 EXIF 格式）
        if creation_time_str:
            raw_dt = _parse_video_datetime(creation_time_str)
            if raw_dt:
                from app.utils.timezone_utils import utc_to_local
                # 视频时间通常是 UTC，转为本地时间
                result.datetime_original = utc_to_local(raw_dt, lat=lat, lon=lon)

        if not result.datetime_original:
            result.datetime_original = _get_file_mtime(file_path)

        # GPS
        if lat is not None and lon is not None:
            result.latitude = round(lat, 7)
            result.longitude = round(lon, 7)
            result.has_gps = True

    except ImportError:
        result.error = "mutagen 未安装"
    except Exception as e:
        logger.warning(f"提取视频元数据失败 {file_path}: {e}")
        result.error = str(e)
        result.datetime_original = _get_file_mtime(file_path)
        result.needs_review = True

    if not result.has_gps:
        result.needs_review = True

    return result


def _parse_video_datetime(dt_str: str) -> Optional[datetime]:
    """解析视频文件中的日期时间字符串，支持多种格式"""
    from app.utils.timezone_utils import parse_exif_datetime

    dt_str = dt_str.strip()

    # ISO 8601 格式：2025-09-10T08:23:00Z 或 2025-09-10T08:23:00.000000Z
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(dt_str[:len(fmt) + 2], fmt)
        except ValueError:
            continue

    # EXIF 格式
    return parse_exif_datetime(dt_str)


# ============================================================
# 通用入口
# ============================================================

def extract_metadata(file_path: str) -> Optional[MediaFileData]:
    """
    根据文件类型自动选择提取方式

    Returns:
        MediaFileData，若文件格式不支持则返回 None
    """
    file_type = get_file_type(file_path)
    if file_type == "photo":
        return extract_photo_metadata(file_path)
    elif file_type == "video":
        return extract_video_metadata(file_path)
    return None


def _get_file_mtime(file_path: str) -> Optional[datetime]:
    """获取文件的最后修改时间作为降级时间"""
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)
    except Exception:
        return None
