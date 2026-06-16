"""
地图生成服务

使用 Folium 生成交互式 HTML 地图：
  - 行程轨迹线（按时间顺序连接 GPS 点）
  - 城市热点标记（半径随照片数量缩放）
  - 点击热点 → 通过 postMessage 通知父页面展示照片

前端通过 <iframe srcDoc="..."> 嵌入，监听 window.message 事件。
"""
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 热点颜色：对应不同城市（最多 13 种）
_HEX_COLORS = [
    "#3B82F6",  # blue
    "#10B981",  # emerald
    "#F59E0B",  # amber
    "#EF4444",  # red
    "#8B5CF6",  # violet
    "#EC4899",  # pink
    "#06B6D4",  # cyan
    "#84CC16",  # lime
    "#F97316",  # orange
    "#14B8A6",  # teal
    "#A855F7",  # purple
    "#FB923C",  # light orange
    "#64748B",  # slate
]


def _get_datetime(f) -> datetime:
    """从 MediaFile 解析拍摄时间，解析失败返回 datetime.min"""
    if f.datetime_original:
        try:
            dt = datetime.fromisoformat(f.datetime_original)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except (ValueError, AttributeError):
            pass
    return datetime.min


def _empty_map_html(reason: str = "没有含 GPS 信息的照片") -> str:
    """返回一个简单的空白地图页面"""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>body{{margin:0;background:#0f172a;color:#64748b;font-family:system-ui;
display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:12px;}}</style>
</head>
<body>
<div style="font-size:40px;">🗺️</div>
<div style="font-size:16px;">{reason}</div>
<div style="font-size:13px;opacity:0.6;">先完成扫描和逆地理编码，GPS 照片会出现在这里</div>
</body>
</html>"""


def generate_map_html(files) -> str:
    """
    根据 MediaFile 列表生成 Folium 交互地图 HTML 字符串。

    Args:
        files: MediaFile 对象列表（来自数据库）

    Returns:
        完整的 HTML 字符串，可直接嵌入 <iframe srcDoc>
    """
    try:
        import folium
    except ImportError:
        return _empty_map_html("folium 未安装，请运行: pip install folium")

    # 过滤：只保留有有效 GPS 坐标的文件
    gps_files = [
        f for f in files
        if f.has_gps and f.latitude is not None and f.longitude is not None
    ]

    if not gps_files:
        return _empty_map_html()

    # 按拍摄时间排序
    gps_sorted = sorted(gps_files, key=_get_datetime)

    # 地图中心（所有 GPS 点的质心）
    lats = [f.latitude for f in gps_sorted]
    lngs = [f.longitude for f in gps_sorted]
    center_lat = sum(lats) / len(lats)
    center_lng = sum(lngs) / len(lngs)

    # 创建 Folium 地图
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=8,
        tiles="CartoDB positron",   # 浅色简洁底图
        attr="© OpenStreetMap contributors © CartoDB",
    )

    # ── 行程轨迹线（虚线，连接所有 GPS 点）────────────────────
    track_coords = [(f.latitude, f.longitude) for f in gps_sorted]
    if len(track_coords) > 1:
        folium.PolyLine(
            track_coords,
            weight=2,
            color="#3B82F6",
            opacity=0.45,
            dash_array="6 4",
            tooltip="行程轨迹",
        ).add_to(m)

    # ── 城市热点标记 ──────────────────────────────────────────
    city_files: dict[str, list] = defaultdict(list)
    for f in gps_sorted:
        key = f.city or "未知地点"
        city_files[key].append(f)

    for idx, (city, file_list) in enumerate(city_files.items()):
        color = _HEX_COLORS[idx % len(_HEX_COLORS)]
        count = len(file_list)

        # 热点位置 = 该城市文件的 GPS 质心
        c_lat = sum(f.latitude for f in file_list) / count
        c_lng = sum(f.longitude for f in file_list) / count

        # 热点半径按文件数对数缩放（最小 10，最大 25）
        import math
        radius = min(10 + int(math.log2(count + 1) * 4), 26)

        # postMessage 数据（不含完整路径，由父页面另查）
        city_safe = city.replace("'", "\\'").replace('"', '\\"')
        province_safe = (file_list[0].province or "").replace("'", "\\'")

        popup_html = (
            f'<div style="font-family:system-ui,sans-serif;padding:4px 2px;min-width:160px;">'
            f'<div style="font-weight:700;font-size:14px;color:{color};margin-bottom:5px;">📍 {city}</div>'
            f'<div style="font-size:12px;color:#64748b;margin-bottom:10px;">{count} 张照片/视频</div>'
            f'<button style="background:{color};color:#fff;border:none;padding:6px 14px;'
            f'border-radius:4px;cursor:pointer;font-size:13px;width:100%;" '
            f'onclick="(function(){{'
            f'window.parent.postMessage({{'
            f'type:\'tripmap_click\','
            f'city:\'{city_safe}\','
            f'province:\'{province_safe}\','
            f'lat:{c_lat},'
            f'lng:{c_lng},'
            f'total:{count}'
            f'}},\'*\');}})()">查看照片 →</button>'
            f'</div>'
        )

        folium.CircleMarker(
            location=[c_lat, c_lng],
            radius=radius,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.65,
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=f"📍 {city}（{count} 张）",
        ).add_to(m)

    # ── 自动缩放到所有点 ──────────────────────────────────────
    if len(track_coords) >= 2:
        min_lat = min(lats)
        max_lat = max(lats)
        min_lng = min(lngs)
        max_lng = max(lngs)
        m.fit_bounds([[min_lat, min_lng], [max_lat, max_lng]], padding=[30, 30])

    return m.get_root().render()
