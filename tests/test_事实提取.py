from __future__ import annotations

from pathlib import Path

from yy_industry_research.事实提取 import 提取事实候选
from yy_industry_research.行业包 import 读取行业包


def test_提取事实候选_按语义锚点分离() -> None:
    root = Path(__file__).resolve().parents[1]
    行业包 = 读取行业包(root, "半导体膜材")
    text = (
        "2026 年半导体膜材 ALD 前驱体 产能 120000 吨。"
        "市场规模达到 80 亿元，预计同比增长 12%，需求增长明显。"
    )
    facts = 提取事实候选(text, "半导体膜材", 行业包)

    keys = {item["fact_key"] for item in facts}
    assert "行业.半导体膜材.产能" in keys
    assert "行业.半导体膜材.市场规模" in keys
    assert "行业.半导体膜材.增长率" in keys

    values = {item["fact_value"] for item in facts}
    assert any(v.startswith("120000") for v in values)
    assert any(v.startswith("80") and v.endswith("亿元") for v in values)
    assert "12%" in values


def test_提取事实候选_过滤年份噪声() -> None:
    facts = 提取事实候选("报告期为 2026 年，基期为 2025 年。", "半导体膜材", {})
    assert facts == []
