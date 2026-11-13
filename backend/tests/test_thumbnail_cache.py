"""M5.1：缩略图落盘缓存"""
import asyncio

from PIL import Image

from app.api.media import get_thumbnail


def test_thumbnail_cache_hit(tmp_path, monkeypatch):
    async def run():
        cache_dir = tmp_path / "thumbs"
        monkeypatch.setenv("TRIPRACE_THUMBNAIL_DIR", str(cache_dir))

        image_path = tmp_path / "photo.jpg"
        Image.new("RGB", (800, 600), (90, 120, 160)).save(image_path, format="JPEG")

        first = await get_thumbnail(path=str(image_path), width=120, quality=70)
        assert first.headers["x-thumbnail-cache"] == "miss"
        assert len(first.body) > 0
        cached = list(cache_dir.glob("*.jpg"))
        assert len(cached) == 1

        second = await get_thumbnail(path=str(image_path), width=120, quality=70)
        assert second.headers["x-thumbnail-cache"] == "hit"
        assert second.body == first.body

    asyncio.run(run())
