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
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_HEIF_REGISTERED = False


def _ensure_heif_support() -> None:
    """注册 pillow-heif，使 Image.open 能读取 iPhone HEIC/HEIF。"""
    global _HEIF_REGISTERED
    if _HEIF_REGISTERED:
        return
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        _HEIF_REGISTERED = True
    except ImportError:
        logger.warning("pillow-heif 未安装，HEIC/HEIF 将无法读取 EXIF")

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
    time_source: str = ""       # exif | ffprobe | mvhd | tag | mtime
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

        _ensure_heif_support()

        with Image.open(file_path) as img:
            # 合并 _getexif() 与 getexif()；HEIC 需要通过 IFD 指针展开
            exif_data = {}
            if hasattr(img, "_getexif"):
                try:
                    legacy = img._getexif()
                    if legacy:
                        exif_data.update(dict(legacy))
                except Exception:
                    pass

            try:
                raw = img.getexif()
                if raw:
                    for key, value in raw.items():
                        exif_data.setdefault(key, value)
                    # ExifIFD 指针（0x8769）：DateTimeOriginal 等
                    try:
                        exif_ifd = raw.get_ifd(0x8769)
                        if exif_ifd:
                            exif_data.update(dict(exif_ifd))
                    except Exception:
                        pass
                    # GPS IFD 指针（0x8825）：GPSInfo
                    try:
                        gps_ifd = raw.get_ifd(0x8825)
                        if gps_ifd:
                            exif_data[0x8825] = dict(gps_ifd)
                    except Exception:
                        pass
            except Exception:
                pass

            if not exif_data:
                # 无 EXIF，使用文件修改时间作为降级方案
                result.datetime_original = _get_file_mtime(file_path)
                result.time_source = "mtime"
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
                parsed = parse_exif_datetime(dt_str)
                if parsed:
                    result.datetime_original = parsed
                    result.time_source = "exif"

            if not result.datetime_original:
                result.datetime_original = _get_file_mtime(file_path)
                result.time_source = "mtime"

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
        result.time_source = "mtime"
        result.needs_review = True

    # 无 GPS，或时间来自 mtime（不是真实拍摄时间）→ 需要人工关注
    if not result.has_gps or result.time_source == "mtime":
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


def _parse_utc_datetime(value: str) -> Optional[datetime]:
    """解析 ffprobe/ISO8601 时间，统一返回 UTC aware datetime。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ffprobe_creation_time(file_path: str) -> Optional[datetime]:
    """用 ffprobe 读取 creation_time（format 或 stream 标签）。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_entries",
                "format_tags=creation_time:stream_tags=creation_time",
                "-show_format",
                "-show_streams",
                file_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        payload = json.loads(proc.stdout)
        candidates = [
            (payload.get("format") or {}).get("tags", {}).get("creation_time"),
        ]
        for stream in payload.get("streams") or []:
            candidates.append((stream.get("tags") or {}).get("creation_time"))
        for value in candidates:
            parsed = _parse_utc_datetime(value) if value else None
            if parsed:
                return parsed
    except Exception as exc:
        logger.debug("ffprobe 读取 creation_time 失败 %s: %s", file_path, exc)
    return None


def _iter_mp4_boxes(file_obj, start: int, end: int):
    """遍历 ISO BMFF box，yield (type, payload_start, box_end)。"""
    pos = start
    while pos + 8 <= end:
        file_obj.seek(pos)
        header = file_obj.read(8)
        if len(header) < 8:
            break
        size = int.from_bytes(header[:4], "big")
        box_type = header[4:8]
        header_size = 8
        if size == 1:
            ext = file_obj.read(8)
            if len(ext) < 8:
                break
            size = int.from_bytes(ext, "big")
            header_size = 16
        elif size == 0:
            size = end - pos
        if size < header_size:
            break
        yield box_type, pos + header_size, pos + size
        pos += size


def _read_mp4_creation_time(file_path: str) -> Optional[datetime]:
    """不依赖 ffprobe，直接读取 MP4/MOV 的 mvhd creation_time（UTC）。"""
    try:
        with open(file_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            f.seek(0)

            moov = None
            for box_type, payload_start, box_end in _iter_mp4_boxes(f, 0, file_size):
                if box_type == b"moov":
                    moov = (payload_start, box_end)
                    break
            if not moov:
                return None

            for box_type, payload_start, _ in _iter_mp4_boxes(f, moov[0], moov[1]):
                if box_type != b"mvhd":
                    continue
                f.seek(payload_start)
                version = f.read(1)[0]
                f.read(3)  # flags
                if version == 1:
                    creation = int.from_bytes(f.read(8), "big")
                else:
                    creation = int.from_bytes(f.read(4), "big")
                if not creation:
                    return None
                dt = datetime(1904, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=creation)
                if 1990 <= dt.year <= 2100:
                    return dt
                return None
    except Exception as exc:
        logger.debug("读取 mvhd creation_time 失败 %s: %s", file_path, exc)
    return None


def extract_video_metadata(file_path: str) -> MediaFileData:
    """
    提取视频文件的元数据（创建时间 + GPS）

    时间优先级：
      1. ffprobe creation_time（UTC）
      2. MP4/MOV mvhd creation_time（UTC）
      3. ©day / 通用标签（按 UTC 处理，保持旧行为）
      4. 文件 mtime（标记 needs_review）
    """
    result = MediaFileData(
        file_path=file_path,
        file_name=os.path.basename(file_path),
        file_type="video",
        file_size_bytes=os.path.getsize(file_path),
    )

    creation_time_str = None
    lat, lon = None, None

    try:
        import mutagen
        from mutagen.mp4 import MP4

        media = mutagen.File(file_path)
        if media is not None:
            # ---- MP4/MOV 格式 ----
            if isinstance(media, MP4):
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
    except ImportError:
        result.error = "mutagen 未安装"
    except Exception as e:
        logger.warning(f"提取视频元数据失败 {file_path}: {e}")
        result.error = str(e)

    # 时间：优先 ffprobe / mvhd，其次 ©day，最后 mtime
    creation_dt = _ffprobe_creation_time(file_path)
    time_source = "ffprobe" if creation_dt else ""

    if creation_dt is None:
        creation_dt = _read_mp4_creation_time(file_path)
        if creation_dt:
            time_source = "mvhd"

    if creation_dt is None and creation_time_str:
        parsed = _parse_video_datetime(creation_time_str)
        if parsed:
            creation_dt = parsed
            time_source = "tag"

    if creation_dt is not None:
        from app.utils.timezone_utils import utc_to_local

        result.datetime_original = utc_to_local(creation_dt, lat=lat, lon=lon)
        result.time_source = time_source
    else:
        result.datetime_original = _get_file_mtime(file_path)
        result.time_source = "mtime"

    # GPS
    if lat is not None and lon is not None:
        result.latitude = round(lat, 7)
        result.longitude = round(lon, 7)
        result.has_gps = True

    # 无 GPS，或时间来自 mtime → 需要人工关注
    if not result.has_gps or result.time_source == "mtime":
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
