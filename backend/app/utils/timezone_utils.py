"""
时区处理工具
- 根据 GPS 坐标查询时区
- UTC 时间转换为本地时间（用于视频 creation_time）
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

# 懒加载 timezonefinder，避免启动时加载 54MB 数据文件
_tf = None


def _get_timezone_finder():
    global _tf
    if _tf is None:
        try:
            from timezonefinder import TimezoneFinder
            _tf = TimezoneFinder()
        except ImportError:
            logger.warning("timezonefinder 未安装，UTC 转换将使用默认 +8 时区")
    return _tf


def get_timezone_from_coords(lat: float, lon: float) -> Optional[str]:
    """
    根据 GPS 坐标获取时区名称（如 "Asia/Shanghai"）

    Args:
        lat: 纬度
        lon: 经度

    Returns:
        时区名称字符串，失败时返回 None
    """
    tf = _get_timezone_finder()
    if tf is None:
        return None
    try:
        tz_name = tf.timezone_at(lat=lat, lng=lon)
        return tz_name
    except Exception as e:
        logger.warning(f"时区查询失败 ({lat}, {lon}): {e}")
        return None


def utc_to_local(
    utc_dt: datetime,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    fallback_tz: str = "Asia/Shanghai",
) -> datetime:
    """
    将 UTC 时间转换为本地时间

    Args:
        utc_dt: UTC datetime 对象（naive 或 aware 均可）
        lat: 纬度（用于查询准确时区），可选
        lon: 经度，可选
        fallback_tz: 无法查询时区时的默认时区（默认中国 +8）

    Returns:
        本地时间的 naive datetime（已去除 tzinfo）
    """
    # 确保是 UTC aware datetime
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)

    # 尝试根据坐标获取精确时区
    tz_name = None
    if lat is not None and lon is not None:
        tz_name = get_timezone_from_coords(lat, lon)

    # 降级到 fallback_tz
    if not tz_name:
        tz_name = fallback_tz

    try:
        local_tz = pytz.timezone(tz_name)
        local_dt = utc_dt.astimezone(local_tz)
        # 返回 naive datetime（去除 tzinfo，与照片 EXIF 格式一致）
        return local_dt.replace(tzinfo=None)
    except Exception as e:
        logger.warning(f"时区转换失败 ({tz_name}): {e}")
        # 最终降级：直接 +8
        from datetime import timedelta
        return (utc_dt + timedelta(hours=8)).replace(tzinfo=None)


def parse_exif_datetime(dt_str: str) -> Optional[datetime]:
    """
    解析 EXIF 日期时间字符串（格式：'YYYY:MM:DD HH:MM:SS'）

    Returns:
        datetime 对象，解析失败返回 None
    """
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        # 尝试 ISO 格式
        try:
            return datetime.fromisoformat(dt_str.strip())
        except ValueError:
            logger.warning(f"无法解析日期时间: {dt_str}")
            return None
