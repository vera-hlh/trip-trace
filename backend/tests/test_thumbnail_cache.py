"""M5.1：缩略图落盘缓存"""
import asyncio
import os
import time

from PIL import Image

from app.api.media import cleanup_thumbnail_cache, get_thumbnail


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


def test_thumbnail_cache_cleanup_by_age_and_size(tmp_path, monkeypatch):
    cache_dir = tmp_path / "thumbs"
    cache_dir.mkdir()
    monkeypatch.setenv("TRIPRACE_THUMBNAIL_DIR", str(cache_dir))

    now = time.time()
    old = cache_dir / "old.jpg"
    mid = cache_dir / "mid.jpg"
    fresh = cache_dir / "fresh.jpg"
    for path, age_days in ((old, 40), (mid, 10), (fresh, 1)):
        path.write_bytes(b"x" * 100)
        os.utime(path, (now - age_days * 86400, now - age_days * 86400))

    removed = cleanup_thumbnail_cache(max_bytes=1000, max_age_days=30)
    assert removed["removed"] == 1
    assert not old.exists()
    assert mid.exists() and fresh.exists()

    # 容量超限：按 mtime 从旧到新删到 80% 以下
    removed = cleanup_thumbnail_cache(max_bytes=150, max_age_days=0)
    assert removed["removed"] >= 1
    total = sum(p.stat().st_size for p in cache_dir.glob("*.jpg"))
    assert total <= 150

