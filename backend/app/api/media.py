"""
媒体文件接口

GET /api/media/thumbnail  - 返回压缩后的缩略图（JPEG）
GET /api/media/info       - 获取单个文件的元数据
"""
import io
import logging
import os
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


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
        from PIL import Image

        with Image.open(decoded_path) as img:
            # 应用 EXIF 方向校正（手机竖拍/横拍时像素数据与显示方向不一致）
            # ImageOps.exif_transpose 读取 EXIF Orientation tag 并自动旋转/翻转
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)

            # 转为 RGB（处理 RGBA、P 等模式，exif_transpose 后可能改变模式）
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # 等比缩放
            orig_w, orig_h = img.size
            if orig_w > width:
                ratio = width / orig_w
                new_h = int(orig_h * ratio)
                img = img.resize((width, new_h), Image.LANCZOS)

            # 输出到内存 buffer
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            buf.seek(0)
            jpeg_bytes = buf.read()

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=3600",  # 缓存 1 小时
                "Content-Length": str(len(jpeg_bytes)),
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
