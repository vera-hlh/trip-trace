"""
扫描文件夹接口

POST /api/scan
  - 递归扫描文件夹中的所有媒体文件
  - 提取每个文件的元数据（时间、GPS）
  - 存入 SQLite 数据库
  - 通过 SSE 流式推送进度

GET /api/scan/status
  - 获取当前数据库中已扫描的文件统计
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.file import MediaFile
from app.services.metadata_service import scan_folder, extract_metadata

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 请求/响应模型
# ============================================================

class ScanRequest(BaseModel):
    folder_path: str
    options: dict = {}


class GeocodeRequest(BaseModel):
    """地理编码请求参数"""
    trip_type: str = "mixed"   # "domestic"=国内 | "abroad"=境外 | "mixed"=混合


class ScanStatusResponse(BaseModel):
    total_files: int
    with_gps: int
    without_gps: int
    needs_review: int
    videos: int
    photos: int


# ============================================================
# SSE 辅助函数
# ============================================================

def _sse_event(data: dict) -> str:
    """将字典序列化为 SSE 格式"""
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# ============================================================
# 接口实现
# ============================================================

@router.post("/scan")
async def scan_folder_endpoint(
    request: ScanRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    扫描文件夹，提取所有媒体文件元数据（SSE 流式响应）

    SSE 事件类型：
      {"type": "start", "total": N}
      {"type": "progress", "current": N, "total": N, "file": "xxx.jpg",
       "has_gps": bool, "datetime": "2025-09-10T09:23:00"}
      {"type": "skip", "current": N, "total": N, "file": "xxx.jpg", "reason": "already_scanned"}
      {"type": "error", "file": "xxx.jpg", "message": "..."}
      {"type": "complete", "total_files": N, "with_gps": N, "without_gps": N, "errors": N}
    """
    folder_path = request.folder_path

    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {folder_path}")

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # 扫描文件列表
            yield _sse_event({"type": "scanning", "message": "正在枚举文件..."})
            await asyncio.sleep(0)  # 让出控制权，确保 SSE 先发出

            file_paths = scan_folder(folder_path)
            total = len(file_paths)

            if total == 0:
                yield _sse_event({"type": "complete", "total_files": 0,
                                  "with_gps": 0, "without_gps": 0, "errors": 0})
                return

            yield _sse_event({"type": "start", "total": total})

            # 统计
            with_gps = 0
            without_gps = 0
            errors = 0
            skipped = 0

            for idx, file_path in enumerate(file_paths, start=1):
                current = idx
                filename = os.path.basename(file_path)

                try:
                    # 检查是否已扫描（通过原始路径去重）
                    existing = await db.execute(
                        select(MediaFile).where(MediaFile.original_path == file_path)
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        yield _sse_event({
                            "type": "skip", "current": current, "total": total,
                            "file": filename, "reason": "already_scanned"
                        })
                        await asyncio.sleep(0)
                        continue

                    # 提取元数据
                    data = extract_metadata(file_path)
                    if data is None:
                        # 不支持的格式，跳过
                        yield _sse_event({
                            "type": "skip", "current": current, "total": total,
                            "file": filename, "reason": "unsupported_format"
                        })
                        await asyncio.sleep(0)
                        continue

                    # 存入数据库
                    media_file = MediaFile(
                        original_path=data.file_path,
                        current_path=data.file_path,
                        file_name=data.file_name,
                        file_type=data.file_type,
                        datetime_original=(
                            data.datetime_original.isoformat()
                            if data.datetime_original else None
                        ),
                        latitude=data.latitude,
                        longitude=data.longitude,
                        has_gps=data.has_gps,
                        needs_review=data.needs_review,
                    )
                    db.add(media_file)

                    # 每 50 个文件批量提交一次，减少 DB 开销
                    if idx % 50 == 0:
                        await db.flush()

                    if data.has_gps:
                        with_gps += 1
                    else:
                        without_gps += 1

                    if data.error:
                        errors += 1

                    yield _sse_event({
                        "type": "progress",
                        "current": current,
                        "total": total,
                        "file": filename,
                        "file_type": data.file_type,
                        "has_gps": data.has_gps,
                        "datetime": (
                            data.datetime_original.isoformat()
                            if data.datetime_original else None
                        ),
                        "error": data.error,
                    })

                except Exception as e:
                    errors += 1
                    logger.error(f"处理文件失败 {file_path}: {e}", exc_info=True)
                    yield _sse_event({
                        "type": "error",
                        "current": current,
                        "total": total,
                        "file": filename,
                        "message": str(e),
                    })

                await asyncio.sleep(0)  # 协作式多任务，保证 SSE 流畅推送

            # 最终提交所有未提交的记录
            await db.commit()

            yield _sse_event({
                "type": "complete",
                "total_files": total,
                "new_files": total - skipped,
                "skipped": skipped,
                "with_gps": with_gps,
                "without_gps": without_gps,
                "errors": errors,
            })

        except Exception as e:
            logger.error(f"扫描过程中发生未预期错误: {e}", exc_info=True)
            yield _sse_event({"type": "fatal_error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保 SSE 实时推送
        },
    )


@router.get("/scan/status", response_model=ScanStatusResponse)
async def get_scan_status(db: AsyncSession = Depends(get_db)):
    """获取当前数据库中已扫描的文件统计"""
    try:
        total = (await db.execute(select(func.count(MediaFile.id)))).scalar() or 0
        with_gps = (
            await db.execute(
                select(func.count(MediaFile.id)).where(MediaFile.has_gps == True)  # noqa
            )
        ).scalar() or 0
        needs_review = (
            await db.execute(
                select(func.count(MediaFile.id)).where(MediaFile.needs_review == True)  # noqa
            )
        ).scalar() or 0
        videos = (
            await db.execute(
                select(func.count(MediaFile.id)).where(MediaFile.file_type == "video")
            )
        ).scalar() or 0

        return ScanStatusResponse(
            total_files=total,
            with_gps=with_gps,
            without_gps=total - with_gps,
            needs_review=needs_review,
            videos=videos,
            photos=total - videos,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/geocoded")
async def get_geocoded_groups(
    folder_path: str | None = Query(None, description="可选：限定文件夹范围"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取已地理编码的文件，按城市+POI 分组汇总，用于 POI 审核界面。

    返回格式：
    [
      { "city": "哈尔滨市", "province": "黑龙江省",
        "poi": "中央大街", "file_count": 15 },
      { "city": "哈尔滨市", "province": "黑龙江省",
        "poi": "", "file_count": 3 },     ← 无 POI（仅城市）
      ...
    ]
    """
    conditions = [MediaFile.city.is_not(None)]

    if folder_path and folder_path.strip():
        norm = os.path.normpath(folder_path.strip())
        from sqlalchemy import or_
        conditions.append(
            or_(
                MediaFile.original_path.like(f"{norm}%"),
                MediaFile.original_path.like(f"{norm.replace(chr(92), '/')}%"),
            )
        )

    result = await db.execute(
        select(MediaFile).where(*conditions).order_by(MediaFile.datetime_original)
    )
    files = result.scalars().all()

    # 按 (province, city, poi) 分组计数
    groups: dict[tuple, dict] = {}
    for f in files:
        key = (f.province or "", f.city or "", f.poi or "")
        if key not in groups:
            groups[key] = {
                "province": f.province or "",
                "city": f.city or "",
                "poi": f.poi or "",
                "file_count": 0,
            }
        groups[key]["file_count"] += 1

    # 按省份 → 城市 → POI 排序
    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (g["province"], g["city"], g["poi"])
    )

    return {
        "success": True,
        "data": {
            "groups": sorted_groups,
            "total_files": len(files),
            "total_groups": len(sorted_groups),
        },
    }


class PoiGroupUpdateRequest(BaseModel):
    """更新一组文件的 POI 名称"""
    province: str
    city: str
    old_poi: str        # 空字符串表示"无POI"
    new_poi: str        # 更新后的 POI 名称（空字符串=清空）


@router.put("/scan/poi-group")
async def update_poi_group(
    body: PoiGroupUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    批量更新指定 城市+POI 分组下所有文件的 POI 名称。

    用途：POI 审核时，用户对某地点整组重命名（如"中央大街" → "哈尔滨中央大街"）
    """
    from sqlalchemy import and_, or_

    # 构建查询条件
    city_condition = MediaFile.city == body.city
    province_condition = MediaFile.province == body.province

    # old_poi 为空字符串时，匹配 poi IS NULL 或 poi = ''
    if body.old_poi == "":
        poi_condition = or_(MediaFile.poi.is_(None), MediaFile.poi == "")
    else:
        poi_condition = MediaFile.poi == body.old_poi

    result = await db.execute(
        select(MediaFile).where(
            and_(province_condition, city_condition, poi_condition)
        )
    )
    files = result.scalars().all()

    if not files:
        return {"success": False, "error": "未找到匹配的文件"}

    # 批量更新
    updated = 0
    new_poi_value = body.new_poi.strip() or None  # 空字符串转 None
    for f in files:
        f.poi = new_poi_value
        updated += 1

    await db.commit()

    return {
        "success": True,
        "updated": updated,
        "message": f"已将 {updated} 个文件的 POI 更新为「{body.new_poi or '（无）'}」",
    }


@router.delete("/scan/clear")
async def clear_scan_data(db: AsyncSession = Depends(get_db)):
    """清空扫描数据（开发调试用）"""
    from sqlalchemy import delete
    await db.execute(delete(MediaFile))
    await db.commit()
    return {"success": True, "message": "扫描数据已清空"}


@router.post("/scan/geocode")
async def geocode_scanned_files(
    body: GeocodeRequest = None,
    db: AsyncSession = Depends(get_db),
):
    """
    对已扫描的有 GPS 但无城市信息的文件批量做逆地理编码

    三层策略：
      1. 离线 reverse_geocoder（省市，全球覆盖）
      2. POI 聚类复用（同行程同地点不重复调用 API）
      3. 高德地图 API（若已配置 Key，则获取精确中文地名 + POI 景点名）

    trip_type 参数：
      "domestic" = 国内行程（只用高德，境外坐标标记为异常）
      "abroad"   = 境外行程（跳过高德，中国坐标标记为异常）
      "mixed"    = 混合行程（国内高德 + 境外离线，无异常检测）

    返回更新数量统计 + 异常文件摘要
    """
    from app.core.config import settings
    from app.services.geocode_service import (
        get_location,
        translate_cn_location,
        PoiClusterState,
        _is_in_china_bbox,
    )
    from datetime import datetime as _dt

    gaode_key = settings.gaode_api_key  # 读取 .env 中的 Key

    # 查找有 GPS 但尚未地理编码（无 city）的文件，按时间排序
    #
    # 跳过逻辑（city IS NOT NULL → 跳过）：
    #   - 已有 city + POI → 完整处理过，跳过
    #   - 已有 city，无 POI → 也跳过（附近无旅行相关POI是正常结果，不再重复调用API）
    #
    # 典型使用场景：
    #   1. 重复运行：重新扫描同一文件夹时，已处理文件直接跳过
    #   2. 额度中断恢复：API额度耗尽后补充额度，只对未处理文件继续
    #   3. 新增文件补扫：文件夹中新增的照片（无city）自动被识别和处理
    result = await db.execute(
        select(MediaFile)
        .where(
            MediaFile.has_gps == True,    # noqa
            MediaFile.city.is_(None),     # 跳过已有city的文件（已处理过）
        )
        .order_by(MediaFile.datetime_original)
        .limit(500)
    )
    files = result.scalars().all()

    if not files:
        return {"success": True, "updated": 0, "message": "无需要地理编码的文件"}

    updated = 0
    errors = 0
    api_calls = 0

    # POI 聚类状态（跨文件复用，减少高德 API 调用次数）
    poi_clusters: list[PoiClusterState] = []

    for f in files:
        if not f.latitude or not f.longitude:
            continue
        try:
            # 解析拍摄时间（用于 POI 聚类时间判断）
            dt = None
            if f.datetime_original:
                try:
                    dt = _dt.fromisoformat(f.datetime_original)
                    if dt.tzinfo:
                        dt = dt.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    pass

            # 调用三层统一接口
            loc, api_called = await get_location(
                lat=f.latitude,
                lon=f.longitude,
                dt=dt,
                gaode_api_key=gaode_key,
                poi_clusters=poi_clusters,
                time_threshold_hours=settings.small_trip_threshold_hours,
            )

            if api_called:
                api_calls += 1

            if loc:
                if loc.source == "gaode":
                    # 高德返回直接中文，无需翻译
                    f.city = loc.city
                    f.province = loc.province
                    f.district = loc.district
                    f.township = loc.township  # 乡镇级行政区（如北极镇）
                    f.country = loc.country or "中国"
                    f.geocode_source = "gaode"
                elif loc.country_code == "CN":
                    # 离线结果（英文）→ 翻译为中文双语格式
                    cn_city, cn_province = translate_cn_location(loc.city, loc.province)
                    f.city = f"{cn_city} ({loc.city})" if cn_city != loc.city else loc.city
                    f.province = (
                        f"{cn_province} ({loc.province})"
                        if cn_province != loc.province
                        else loc.province
                    )
                    f.district = loc.district
                    f.country = loc.country
                    f.geocode_source = "offline"
                else:
                    # 国外地点，保留英文
                    f.city = loc.city
                    f.province = loc.province
                    f.district = loc.district
                    f.country = loc.country
                    f.geocode_source = "offline"

                # 写入 POI（景点名，高德 API 提供）
                if loc.poi:
                    f.poi = loc.poi

                updated += 1

        except Exception as e:
            errors += 1
            logger.warning(f"地理编码失败 {f.file_name}: {e}")

    await db.commit()

    trip_type = (body.trip_type if body else "mixed")

    # 异常文件检测（按 trip_type 检查坐标是否与行程类型匹配）
    anomaly_files: list[str] = []
    if trip_type in ("domestic", "abroad"):
        all_gps_result = await db.execute(
            select(MediaFile).where(
                MediaFile.has_gps == True,        # noqa
                MediaFile.city.is_not(None),      # 已编码
                MediaFile.latitude.is_not(None),
                MediaFile.longitude.is_not(None),
            )
        )
        all_gps_files = all_gps_result.scalars().all()
        for f in all_gps_files:
            in_china = _is_in_china_bbox(f.latitude, f.longitude)
            is_anomaly = (
                (trip_type == "domestic" and not in_china) or
                (trip_type == "abroad" and in_china)
            )
            if is_anomaly:
                anomaly_files.append(f.file_name)

    gaode_note = f"（高德 API 调用 {api_calls} 次）" if gaode_key else "（未配置高德 Key，仅离线模式）"
    return {
        "success": True,
        "updated": updated,
        "errors": errors,
        "api_calls": api_calls,
        "total_processed": len(files),
        "trip_type": trip_type,
        "anomaly_count": len(anomaly_files),
        "anomaly_files": anomaly_files[:20],  # 最多返回前20个文件名
        "message": f"已为 {updated} 个文件更新地理位置信息 {gaode_note}",
    }
