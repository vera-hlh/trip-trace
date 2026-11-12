"""best_location_label 回归测试

原 `backend/test_best_label.py` 是脚本式自测，这里收编为 pytest 参数化用例。
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.archive_service import MediaItem


def make_item(**kwargs) -> MediaItem:
    return MediaItem(
        file_path="x",
        file_name="x",
        datetime_original=datetime(2025, 1, 1),
        **kwargs,
    )


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"city": "漠河市"}, "漠河"),
        ({"city": "延边朝鲜族自治州"}, "延边"),
        ({"city": "漠河市", "township": "北极镇"}, "漠河北极镇"),
        ({"city": "漠河市", "poi": "冰雪大世界"}, "漠河冰雪大世界"),
        ({"city": "漠河市", "poi": "漠河站"}, "漠河站"),
        ({"city": "漠河市", "township": "漠河北极镇"}, "漠河北极镇"),
        (
            {"city": "漠河市", "township": "北极镇", "poi": "龙江第一湾风景区"},
            "漠河龙江第一湾风景区",
        ),
        (
            {"city": "漠河市", "district": "漠河市区", "township": "北极镇"},
            "漠河北极镇",
        ),
        ({"poi": "冰雪大世界"}, "冰雪大世界"),
        ({}, ""),
        (
            {"city": "延边朝鲜族自治州", "poi": "长白山天池"},
            "延边长白山天池",
        ),
        ({"city": "昆明市"}, "昆明"),
        ({"city": "昆明市", "district": "西山区"}, "昆明西山区"),
    ],
    ids=[
        "city-only-mohe",
        "city-only-yanbian",
        "city-township",
        "city-poi",
        "poi-contains-city",
        "township-contains-city",
        "poi-priority",
        "township-priority",
        "poi-only",
        "empty",
        "yanbian-poi",
        "kunming",
        "kunming-district",
    ],
)
def test_best_location_label(kwargs, expected):
    assert make_item(**kwargs).best_location_label == expected
