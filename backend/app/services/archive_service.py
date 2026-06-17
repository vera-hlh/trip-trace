"""
智能归档算法服务

将按时间排序的媒体文件列表切分为大行程和子行程，支持：
  - 大行程切分（时间间隔 > 30 天）
  - 小行程切分（地点变化 + 时间间隔 > 2 小时）
  - 同地点合并（不切分，无论时间间隔多长）
  - GPS 漂移过滤（短时间地点变化视为漂移）
  - 地点回归自动处理（A→B→A 模式，第二次 A 为新行程）
  - 文件夹命名生成（YYYY-MM_行程名 / 序号_地点_MMDD-MMDD）
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 配置参数（全部可配置）
# ============================================================

@dataclass
class ArchiveConfig:
    """归档算法配置参数"""
    # 大行程时间阈值（天）：超过此值切分为新的大行程
    big_trip_threshold_days: int = 30

    # 小行程时间阈值（小时）：地点变化且超过此值则切分
    small_trip_threshold_hours: float = 2.0

    # GPS 漂移过滤：地点变化但时间间隔 < 此值（小时）则视为 GPS 漂移
    gps_drift_threshold_hours: float = 0.5

    # 文件夹命名中的日期格式
    date_fmt: str = "%m%d"

    # 是否启用地点回归检测（A→B→A 时强制切分第二次 A）
    enable_location_return_detection: bool = True


# ============================================================
# 数据结构
# ============================================================

@dataclass
class MediaItem:
    """
    归档算法的输入单元：一个媒体文件的最小元数据

    字段说明：
      - file_path: 文件完整路径
      - datetime_original: 拍摄时间（本地时间）
      - location_key: 地点标识（如 "CN/云南省/昆明市"），用于比较是否换地点
      - city: 城市名（用于文件夹命名）
      - has_gps: 是否有 GPS 信息
    """
    file_path: str
    file_name: str
    datetime_original: Optional[datetime]
    location_key: str = ""  # 用于行程切分比较
    city: str = ""           # 用于文件夹命名
    country_code: str = ""
    has_gps: bool = False


@dataclass
class SubTrip:
    """子行程（一个具体的地点行程段）"""
    sequence_num: int            # 在大行程中的序号（从 1 开始）
    location_label: str          # 主要地点标签（如 "昆明"）
    start_date: datetime
    end_date: datetime
    items: list[MediaItem] = field(default_factory=list)
    user_modified: bool = False  # 是否经过用户手动修改

    @property
    def trip_name(self) -> str:
        """
        生成子行程文件夹名称
        格式：序号_地点_MMDD-MMDD
        例：01_昆明_0910-0913
        """
        start_str = self.start_date.strftime("%m%d")
        end_str = self.end_date.strftime("%m%d")
        return f"{self.sequence_num:02d}_{self.location_label}_{start_str}-{end_str}"

    @property
    def file_count(self) -> int:
        return len(self.items)


@dataclass
class BigTrip:
    """大行程（包含多个子行程）"""
    year: int
    month: int
    start_date: datetime
    end_date: datetime
    sub_trips: list[SubTrip] = field(default_factory=list)
    display_name: str = ""       # 用户自定义名称

    @property
    def folder_name(self) -> str:
        """
        生成大行程文件夹名称
        格式：YYYY-MM_行程名
        例：2025-09_云南之旅
        """
        main_location = self._get_main_location()
        if self.display_name:
            return f"{self.year:04d}-{self.month:02d}_{self.display_name}"
        return f"{self.year:04d}-{self.month:02d}_{main_location}之旅"

    def _get_main_location(self) -> str:
        """找出出现次数最多的地点作为大行程主要地点"""
        from collections import Counter
        if not self.sub_trips:
            return "旅行"
        labels = [t.location_label for t in self.sub_trips if t.location_label]
        if not labels:
            return "旅行"
        return Counter(labels).most_common(1)[0][0]

    @property
    def total_files(self) -> int:
        return sum(t.file_count for t in self.sub_trips)


# ============================================================
# 归档算法核心
# ============================================================

def _location_key_to_label(location_key: str) -> str:
    """
    将地点键（如 "CN/Yunnan/Kunming"）转为简短标签（如 "Kunming"）
    取最后一个非空 path 段
    """
    if not location_key:
        return "未知地点"
    parts = [p for p in location_key.split("/") if p.strip()]
    return parts[-1] if parts else "未知地点"


def _get_location_city(item: MediaItem) -> str:
    """从 MediaItem 获取城市名（优先用 city 字段）"""
    return item.city or _location_key_to_label(item.location_key) or "未知"


def segment_into_trips(
    items: list[MediaItem],
    config: Optional[ArchiveConfig] = None,
) -> list[BigTrip]:
    """
    将媒体文件列表切分为大行程和子行程

    算法步骤：
    1. 按拍摄时间排序（无时间的文件放末尾）
    2. 一次遍历，按规则切分
    3. 将子行程组合为大行程

    Args:
        items: 媒体文件列表（含时间和位置信息）
        config: 归档算法配置，None 时使用默认值

    Returns:
        大行程列表，每个大行程包含有序子行程
    """
    if config is None:
        config = ArchiveConfig()

    if not items:
        return []

    # 1. 按时间排序（无时间的放到末尾）
    has_time = [it for it in items if it.datetime_original is not None]
    no_time = [it for it in items if it.datetime_original is None]
    sorted_items = sorted(has_time, key=lambda x: x.datetime_original)

    if not sorted_items:
        # 全部没有时间，创建单个"待分类"子行程
        return _make_unclassified_trip(items)

    # 2. 切分为子行程片段
    sub_trip_segments: list[list[MediaItem]] = []
    current_segment: list[MediaItem] = [sorted_items[0]]

    for i in range(1, len(sorted_items)):
        prev = sorted_items[i - 1]
        curr = sorted_items[i]

        time_diff_hours = (curr.datetime_original - prev.datetime_original).total_seconds() / 3600
        time_diff_days = time_diff_hours / 24

        # 规则1：大行程边界（超过 30 天）
        if time_diff_days > config.big_trip_threshold_days:
            sub_trip_segments.append(current_segment)
            current_segment = [curr]
            continue

        prev_loc = prev.location_key
        curr_loc = curr.location_key

        # 规则2：同一地点 → 直接合并（无论时间多长）
        if curr_loc and prev_loc and curr_loc == prev_loc:
            current_segment.append(curr)
            continue

        # 规则3：地点不同
        if time_diff_hours < config.gps_drift_threshold_hours:
            # GPS 漂移过滤（地点变化但时间差很小）
            current_segment.append(curr)
        elif time_diff_hours > config.small_trip_threshold_hours:
            # 正常地点切换 → 切分
            sub_trip_segments.append(current_segment)
            current_segment = [curr]
        else:
            # 时间差在 [drift, threshold] 之间，合并
            current_segment.append(curr)

    sub_trip_segments.append(current_segment)

    # 处理无时间文件：追加到最后一个子行程
    if no_time:
        sub_trip_segments[-1].extend(no_time)

    # 3. 将子行程段组合为大行程
    big_trips = _build_big_trips(sub_trip_segments, config)
    return big_trips


def _build_big_trips(
    segments: list[list[MediaItem]],
    config: ArchiveConfig,
) -> list[BigTrip]:
    """
    将子行程片段列表组合为大行程

    逻辑：
    - 相邻两段时间差 > 30 天 → 新大行程
    - 同一大行程内按序号编排子行程
    """
    if not segments:
        return []

    big_trips: list[BigTrip] = []
    current_big: Optional[BigTrip] = None
    sub_seq: int = 1  # 当前大行程的子行程序号

    for seg in segments:
        if not seg:
            continue

        # 获取该片段的时间范围
        seg_times = [it.datetime_original for it in seg if it.datetime_original]
        if not seg_times:
            continue

        seg_start = min(seg_times)
        seg_end = max(seg_times)

        # 获取主要地点（出现次数最多的城市）
        from collections import Counter
        cities = [_get_location_city(it) for it in seg if it.has_gps]
        main_city = Counter(cities).most_common(1)[0][0] if cities else "未知"

        # 判断是否需要开始新的大行程
        need_new_big = (current_big is None)
        if current_big is not None:
            # 与上一个子行程的时间差
            last_sub_end = max(
                it.datetime_original for sub in current_big.sub_trips
                for it in sub.items if it.datetime_original
            )
            gap_days = (seg_start - last_sub_end).total_seconds() / 86400
            if gap_days > config.big_trip_threshold_days:
                need_new_big = True

        if need_new_big:
            current_big = BigTrip(
                year=seg_start.year,
                month=seg_start.month,
                start_date=seg_start,
                end_date=seg_end,
            )
            big_trips.append(current_big)
            sub_seq = 1

        # 创建子行程
        sub = SubTrip(
            sequence_num=sub_seq,
            location_label=main_city,
            start_date=seg_start,
            end_date=seg_end,
            items=seg,
        )
        current_big.sub_trips.append(sub)
        current_big.end_date = max(current_big.end_date, seg_end)
        sub_seq += 1

    return big_trips


def _make_unclassified_trip(items: list[MediaItem]) -> list[BigTrip]:
    """为无时间文件创建一个占位大行程"""
    now = datetime.now()
    sub = SubTrip(
        sequence_num=1,
        location_label="待分类",
        start_date=now,
        end_date=now,
        items=items,
    )
    big = BigTrip(
        year=now.year,
        month=now.month,
        start_date=now,
        end_date=now,
        sub_trips=[sub],
        display_name="待分类",
    )
    return [big]


# ============================================================
# 无 GPS 文件时间就近位置推断
# ============================================================

def infer_location_for_gps_less(
    items: list[MediaItem],
    time_window_hours: float = 2.0,
) -> list[MediaItem]:
    """
    为「有时间戳但无 GPS」的文件，根据时间窗口内前后相邻的有 GPS 文件推断位置。

    推断规则（按优先级）：
      1. 前后都在窗口内且位置相同 → 推断该位置（最可信）
      2. 仅前方有 GPS 文件         → 采用前方位置
      3. 仅后方有 GPS 文件         → 采用后方位置
      4. 前后位置不同（路途中）    → 不推断，保持无位置
      5. 超出时间窗口              → 不推断

    Args:
        items: MediaItem 列表（来自数据库）
        time_window_hours: 推断时间窗口（小时），与小行程阈值对齐

    Returns:
        新列表，其中 GPS-less 文件的 location_key/city 已被推断填充（has_gps 仍为 False）
    """
    from datetime import timedelta
    from dataclasses import replace as dc_replace

    # 只有含时间戳且有 GPS 且有位置信息的文件才能作为参考
    gps_ref = sorted(
        [it for it in items if it.has_gps and it.datetime_original and it.location_key],
        key=lambda x: x.datetime_original,
    )

    if not gps_ref:
        return items  # 没有参考文件，无法推断

    window = timedelta(hours=time_window_hours)
    result: list[MediaItem] = []

    for item in items:
        # 只处理：有时间戳 + 无GPS
        if item.has_gps or not item.datetime_original:
            result.append(item)
            continue

        dt = item.datetime_original

        # 找前方（dt 之前）最近的 GPS 文件（在时间窗口内）
        prev_ref: Optional[MediaItem] = None
        for ref in reversed(gps_ref):
            if ref.datetime_original <= dt:
                if dt - ref.datetime_original <= window:
                    prev_ref = ref
                break

        # 找后方（dt 之后）最近的 GPS 文件（在时间窗口内）
        next_ref: Optional[MediaItem] = None
        for ref in gps_ref:
            if ref.datetime_original >= dt:
                if ref.datetime_original - dt <= window:
                    next_ref = ref
                break

        # 推断逻辑
        inferred_loc_key = ""
        inferred_city = ""

        if prev_ref and next_ref:
            if prev_ref.location_key == next_ref.location_key:
                # 前后位置相同 → 推断（最可信）
                inferred_loc_key = prev_ref.location_key
                inferred_city = prev_ref.city
            # else: 前后不同（路途中），不推断
        elif prev_ref:
            inferred_loc_key = prev_ref.location_key
            inferred_city = prev_ref.city
        elif next_ref:
            inferred_loc_key = next_ref.location_key
            inferred_city = next_ref.city

        if inferred_loc_key:
            # 用推断位置创建新的 MediaItem（has_gps 仍为 False，标记原本无GPS）
            result.append(dc_replace(
                item,
                location_key=inferred_loc_key,
                city=inferred_city,
            ))
            logger.debug(
                f"GPS推断：{item.file_name} → {inferred_city or inferred_loc_key}"
            )
        else:
            result.append(item)  # 无法推断，保持原样

    return result


# ============================================================
# 归档预览（生成文件移动计划）
# ============================================================

@dataclass
class ArchivePreviewItem:
    """一个文件的归档计划"""
    original_path: str
    target_path: str             # 归档后的目标路径
    big_trip_folder: str         # 大行程文件夹名
    sub_trip_folder: str         # 子行程文件夹名
    file_name: str


def generate_archive_preview(
    big_trips: list[BigTrip],
    output_base: str,
) -> list[ArchivePreviewItem]:
    """
    根据大行程列表生成归档预览（文件移动计划）

    Args:
        big_trips: segment_into_trips() 的返回值
        output_base: 归档输出根目录（如 "C:\\Users\\Eva\\Pictures\\归档"）

    Returns:
        每个文件的移动计划列表
    """
    import os
    preview = []

    for big in big_trips:
        big_folder = big.folder_name
        for sub in big.sub_trips:
            sub_folder = sub.trip_name
            for item in sub.items:
                target_path = os.path.join(
                    output_base,
                    big_folder,
                    sub_folder,
                    item.file_name,
                )
                preview.append(ArchivePreviewItem(
                    original_path=item.file_path,
                    target_path=target_path,
                    big_trip_folder=big_folder,
                    sub_trip_folder=sub_folder,
                    file_name=item.file_name,
                ))

    return preview
