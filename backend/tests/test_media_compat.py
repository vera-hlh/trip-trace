"""M4.2：HEIC 支持与视频 creation_time"""
from datetime import datetime, timezone

import piexif
from PIL import Image
from pillow_heif import register_heif_opener

from app.services import metadata_service
from app.services.metadata_service import (
    _read_mp4_creation_time,
    extract_photo_metadata,
    extract_video_metadata,
)


def test_heic_exif_time_and_gps(tmp_path):
    register_heif_opener()
    path = tmp_path / "iphone.heic"
    exif = {
        "0th": {},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: "2025:09:10 09:23:00"},
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: "N",
            piexif.GPSIFD.GPSLatitude: ((25, 1), (2, 1), (2000, 100)),
            piexif.GPSIFD.GPSLongitudeRef: "E",
            piexif.GPSIFD.GPSLongitude: ((102, 1), (43, 1), (600, 100)),
        },
        "1st": {},
        "thumbnail": None,
    }
    Image.new("RGB", (32, 32), (120, 160, 200)).save(
        path, format="HEIF", exif=piexif.dump(exif)
    )

    result = extract_photo_metadata(str(path))
    assert result.time_source == "exif"
    assert result.datetime_original == datetime(2025, 9, 10, 9, 23, 0)
    assert result.has_gps is True
    assert abs(result.latitude - 25.0389) < 0.001
    assert abs(result.longitude - 102.7183) < 0.001
    assert result.needs_review is False


def test_photo_without_exif_marks_review(tmp_path):
    path = tmp_path / "plain.jpg"
    Image.new("RGB", (16, 16), (10, 20, 30)).save(path, format="JPEG")

    result = extract_photo_metadata(str(path))
    assert result.time_source == "mtime"
    assert result.datetime_original is not None
    assert result.needs_review is True


def _box(box_type: bytes, payload: bytes) -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + box_type + payload


def test_mp4_mvhd_creation_time(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    epoch = datetime(1904, 1, 1, tzinfo=timezone.utc)
    target = datetime(2025, 9, 10, 8, 0, 0, tzinfo=timezone.utc)
    creation = int((target - epoch).total_seconds())
    mvhd = (
        b"\x00\x00\x00\x00"
        + creation.to_bytes(4, "big")
        + b"\x00" * 4
        + (1000).to_bytes(4, "big")
        + (5000).to_bytes(4, "big")
        + b"\x00" * 80
    )
    data = (
        _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
        + _box(b"moov", _box(b"mvhd", mvhd))
    )
    path.write_bytes(data)

    assert _read_mp4_creation_time(str(path)) == target

    # 避免 CI 上 ffprobe 抢先返回，强制走 mvhd
    monkeypatch.setattr(metadata_service, "_ffprobe_creation_time", lambda _: None)
    result = extract_video_metadata(str(path))
    assert result.time_source == "mvhd"
    # 无 GPS 时按 Asia/Shanghai 回退：UTC 08:00 → 16:00
    assert result.datetime_original == datetime(2025, 9, 10, 16, 0, 0)
    assert result.needs_review is True
