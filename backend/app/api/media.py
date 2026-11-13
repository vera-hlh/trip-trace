"""
媒体文件接口

GET /api/media/thumbnail  - 返回压缩后的缩略图（JPEG）
GET /api/media/info       - 获取单个文件的元数据
"""
import asyncio
import hashlib
import io
import logging
import os
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, JSONResponse

from app.core.database import app_data_dir

logger = logging.getLogger(__name__)
router = APIRouter()


def _cache_dir() -> Path:
    override = os.environ.get("TRIPRACE_THUMBNAIL_DIR")
    return Path(override) if override else app_data_dir() / "thumbnails"


def _cache_file(decoded_path: str, width: int, quality: int) -> Path:
    stat = os.stat(decoded_path)
    raw = (
        f"{os.path.normcase(os.path.abspath(decoded_path))}|"
        f"{stat.st_size}|{stat.st_mtime_ns}|{width}|{quality}"
    )
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{key}.jpg"


def _render_thumbnail(decoded_path: str, width: int, quality: int) -> bytes:
    from PIL import Image, ImageOps

    with Image.open(decoded_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        orig_w, orig_h = img.size
        if orig_w > width:
            ratio = width / orig_w
            img = img.resize((width, int(orig_h * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()


def _write_cache(cache_file: Path, data: bytes) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_name(cache_file.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, cache_file)


@router.get("/media/thumbnail")
async def get_thumbnail(
    path: str = Query(..., description="图片完整路径（URL 编码）"),
    width: int = Query(400, ge=50, le=2000, description="目标宽度（像素）"),
    quality: int = Query(75, ge=10, le=95, description="JPEG 质量（10-95）"),
):
    """
    返回压缩后的缩略图（JPEG 格式）

    用于：
    - 前端行程预览缩略图
    - Folium 地图热点弹窗照片
    - 视频导出时的照片帧

    Args:
        path: 照片文件完整路径（Windows 路径，URL 编码）
        width: 缩略图宽度（等比缩放）
        quality: JPEG 质量（默认 75，平衡质量与体积）
    """
    # 解码路径（处理中文路径）
    decoded_path = unquote(path)

    if not os.path.exists(decoded_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {decoded_path}")

    try:
        cache_file = _cache_file(decoded_path, width, quality)

        if cache_file.exists():
            try:
                cached = await asyncio.to_thread(cache_file.read_bytes)
                return Response(
                    content=cached,
                    media_type="image/jpeg",
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "Content-Length": str(len(cached)),
                        "X-Thumbnail-Cache": "hit",
                    },
                )
            except OSError:
                pass

        jpeg_bytes = await asyncio.to_thread(
            _render_thumbnail, decoded_path, width, quality
        )
        try:
            await asyncio.to_thread(_write_cache, cache_file, jpeg_bytes)
        except OSError as exc:
            logger.warning("写入缩略图缓存失败 %s: %s", cache_file, exc)

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Length": str(len(jpeg_bytes)),
                "X-Thumbnail-Cache": "miss",
            },
        )

    except ImportError:
        raise HTTPException(status_code=500, detail="Pillow 未安装")
    except Exception as e:
        logger.error(f"生成缩略图失败 {decoded_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成缩略图失败: {str(e)}")


@router.get("/media/info")
async def get_media_info(
    path: str = Query(..., description="文件完整路径"),
):
    """获取单个文件的元数据"""
    decoded_path = unquote(path)

    if not os.path.exists(decoded_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {decoded_path}")

    try:
        from app.services.metadata_service import extract_metadata

        data = extract_metadata(decoded_path)
        if data is None:
            raise HTTPException(status_code=400, detail="不支持的文件格式")

        return {
            "success": True,
            "data": {
                "file_name": data.file_name,
                "file_type": data.file_type,
                "file_size_mb": round(data.file_size_bytes / (1024 * 1024), 2),
                "datetime_original": (
                    data.datetime_original.isoformat()
                    if data.datetime_original else None
                ),
                "latitude": data.latitude,
                "longitude": data.longitude,
                "has_gps": data.has_gps,
                "needs_review": data.needs_review,
                "error": data.error,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
