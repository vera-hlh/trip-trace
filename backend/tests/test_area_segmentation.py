"""Phase 2：景区边界参与子行程切分"""
from datetime import datetime, timedelta

from app.services.archive_service import (
    ArchiveConfig,
    MediaItem,
    infer_location_for_gps_less,
    segment_into_trips,
)


def _item(name, dt, area, key_suffix=None):
    suffix = key_suffix if key_suffix is not None else area
    return MediaItem(
        file_path=f"C:/in/{name}",
        file_name=name,
        datetime_original=dt,
        location_key=f"CN/湖北省/宜昌市/{suffix}" if suffix else "CN/湖北省/宜昌市",
        city="宜昌市",
        province="湖北省",
        area_name=area,
        has_gps=True,
    )


def test_area_change_splits_even_with_short_time_gap():
    start = datetime(2026, 2, 11, 10, 0, 0)
    items = [
        _item("a1.jpg", start, "三峡大坝旅游区"),
        _item("a2.jpg", start + timedelta(minutes=5), "三峡大坝旅游区"),
        _item("b1.jpg", start + timedelta(minutes=10), "三峡人家风景区"),
        _item("b2.jpg", start + timedelta(minutes=15), "三峡人家风景区"),
    ]
    bigs = segment_into_trips(items, ArchiveConfig())
    assert len(bigs) == 1
    assert [s.area_name for s in bigs[0].sub_trips] == [
        "三峡大坝旅游区", "三峡人家风景区"
    ]
    assert [s.location_label for s in bigs[0].sub_trips] == [
        "三峡大坝旅游区", "三峡人家风景区"
    ]


def test_same_area_merges_without_time_split():
    start = datetime(2026, 2, 11, 10, 0, 0)
    items = [
        _item("a1.jpg", start, "三峡大坝旅游区"),
        _item("a2.jpg", start + timedelta(minutes=5), "三峡大坝旅游区"),
        _item("a3.jpg", start + timedelta(minutes=10), "三峡大坝旅游区"),
    ]
    bigs = segment_into_trips(items, ArchiveConfig())
    assert len(bigs) == 1
    assert len(bigs[0].sub_trips) == 1
    assert bigs[0].sub_trips[0].area_name == "三峡大坝旅游区"


def test_no_area_falls_back_to_location_key():
    start = datetime(2026, 2, 11, 10, 0, 0)
    items = [
        _item("a1.jpg", start, "", "三峡大坝旅游区"),
        _item("a2.jpg", start + timedelta(minutes=5), "", "三峡大坝旅游区"),
        _item("b1.jpg", start + timedelta(hours=3), "", "三峡人家风景区"),
        _item("b2.jpg", start + timedelta(hours=3, minutes=5), "", "三峡人家风景区"),
    ]
    bigs = segment_into_trips(items, ArchiveConfig())
    assert len(bigs[0].sub_trips) == 2


def test_gps_less_inference_propagates_area():
    start = datetime(2026, 2, 11, 10, 0, 0)
    ref_a = _item("a.jpg", start, "三峡大坝旅游区")
    mid = MediaItem(
        file_path="C:/in/mid.jpg",
        file_name="mid.jpg",
        datetime_original=start + timedelta(minutes=2),
        city="宜昌市",
        province="湖北省",
        has_gps=False,
    )
    ref_b = _item("b.jpg", start + timedelta(minutes=4), "三峡大坝旅游区")
    result = infer_location_for_gps_less([ref_a, mid, ref_b], time_window_hours=2)
    inferred = next(x for x in result if x.file_name == "mid.jpg")
    assert inferred.area_name == "三峡大坝旅游区"
    assert inferred.location_key.endswith("三峡大坝旅游区")
