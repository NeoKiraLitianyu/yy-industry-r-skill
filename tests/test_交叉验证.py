from __future__ import annotations

from pathlib import Path

from yy_industry_research.索引 import 初始化行业索引, 写入事实, 写入来源
from yy_industry_research.验证 import 执行全量交叉验证


def _source(db: Path, key: str, name: str, uri: str) -> int:
    return 写入来源(
        db,
        source_key=key,
        source_name=name,
        source_type="券商咨询",
        source_uri=uri,
        region="中国",
        credibility=8,
    )


def test_同一机构多链接不算两个独立来源(tmp_path: Path):
    db = tmp_path / "研究.sqlite"
    初始化行业索引(db)
    a = _source(db, "a", "中信证券", "https://a.example/report-1")
    b = _source(db, "b", "中信证券", "https://b.example/report-2")
    写入事实(db, a, "市场规模.2025", "extracted_numeric", "100", "亿元", "2025")
    写入事实(db, b, "市场规模.2025", "extracted_numeric", "100", "亿元", "2025")

    result = 执行全量交叉验证(db)

    assert result == {"total": 1, "passed": 0, "pending": 1, "conflicted": 0}


def test_taxonomy关键词命中不进入硬事实交叉验证(tmp_path: Path):
    db = tmp_path / "研究.sqlite"
    初始化行业索引(db)
    a = _source(db, "a", "机构甲", "https://a.example/report")
    b = _source(db, "b", "机构乙", "https://b.example/report")
    写入事实(db, a, "industry:半导体膜材:ALD前驱体", "keyword_match", "命中")
    写入事实(db, b, "industry:半导体膜材:ALD前驱体", "keyword_match", "命中")

    result = 执行全量交叉验证(db)

    assert result == {"total": 0, "passed": 0, "pending": 0, "conflicted": 0}
