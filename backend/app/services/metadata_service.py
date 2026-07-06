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


def scan_folder(folder_path: str) -> tuple[list[str], list[str]]:
    """
    递归扫描文件夹，返回所有支持的媒体文件路径列表。

    Returns:
        (media_files, skipped_dirs):
          - media_files: 支持的媒体文件完整路径列表（已排序）
          - skipped_dirs: 因权限不足被跳过的目录路径列表
    """
    media_files = []
    skipped_dirs: list[str] = []
    all_extensions = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS

    def _onerror(error: OSError) -> None:
        """处理 os.walk 遇到无访问权限目录的情况"""
        path = getattr(error, "filename", None) or str(error)
        skipped_dirs.append(str(path))
        logger.warning(f"扫描时跳过目录（无访问权限）: {path}")

    for root, dirs, files in os.walk(folder_path, onerror=_onerror):
        # 跳过隐藏目录（以 . 开头）
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            ext = Path(filename).suffix.lower()
            if ext in all_extensions:
                media_files.append(os.path.join(root, filename))

    return sorted(media_files), skipped_dirs


# ============================================================
# 照片元数据提取
# ============================================================

# ============================================================
# 坐标系转换工具（GCJ-02 → WGS-84）
# ============================================================

def _gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """
    将 GCJ-02（火星坐标）逆转换为 WGS-84（国际GPS标准）

    仅对中国大陆境内的坐标有效（大约在 72°E~135°E, 3°N~53°N 范围内）。
    境外坐标直接返回原值。

    算法来源：公开的 GCJ-02 偏移量计算公式（逆变换近似）
    精度：约 1-3 米以内
    """
    import math

    def _is_in_china(lng: float, lat: float) -> bool:
        """粗略判断坐标是否在中国大陆范围内"""
        return 72.0 < lng < 137.8 and 0.8 < lat < 55.8

    if not _is_in_china(lng, lat):
        return lng, lat  # 境外坐标无需转换

    a = 6378245.0  # 克拉索夫斯基椭球体长半轴
    ee = 0.00669342162296594323  # 第一偏心率平方

    def _transform_lat(x: float, y: float) -> float:
        ret = (-100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y
               + 0.2*math.sqrt(abs(x)))
        ret += (20.0*math.sin(6.0*x*math.pi)
                + 20.0*math.sin(2.0*x*math.pi)) * 2.0 / 3.0
        ret += (20.0*math.sin(y*math.pi)
                + 40.0*math.sin(y/3.0*math.pi)) * 2.0 / 3.0
        ret += (160.0*math.sin(y/12.0*math.pi)
                + 320.0*math.sin(y*math.pi/30.0)) * 2.0 / 3.0
        return ret

    def _transform_lng(x: float, y: float) -> float:
        ret = (300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y
               + 0.1*math.sqrt(abs(x)))
        ret += (20.0*math.sin(6.0*x*math.pi)
                + 20.0*math.sin(2.0*x*math.pi)) * 2.0 / 3.0
        ret += (20.0*math.sin(x*math.pi)
                + 40.0*math.sin(x/3.0*math.pi)) * 2.0 / 3.0
        ret += (150.0*math.sin(x/12.0*math.pi)
                + 300.0*math.sin(x/30.0*math.pi)) * 2.0 / 3.0
        return ret

    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)

    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1.0 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)

    dlat = (dlat * 180.0) / ((a * (1.0 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)

    # GCJ-02 = WGS-84 + offset  →  WGS-84 = GCJ-02 - offset
    wgs_lat = lat - dlat
    wgs_lng = lng - dlng
    return wgs_lng, wgs_lat


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

                    # ── 坐标系检测与转换 ──────────────────────────────
                    # 读取 GPSMapDatum（EXIF tag 0x0012）
                    # 标准设备写入 WGS-84，部分国产老机型/第三方 App 写入 GCJ-02
                    map_datum = str(gps_info.get("GPSMapDatum", "WGS-84")).strip().upper()
                    if "GCJ" in map_datum:
                        # 检测到 GCJ-02 → 做逆转换到 WGS-84
                        lon, lat = _gcj02_to_wgs84(lon, lat)
                        logger.debug(
                            f"GPS 坐标系 GCJ-02 已转换为 WGS-84: "
                            f"({result.file_name}: lat={lat:.6f}, lon={lon:.6f})"
                        )

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
