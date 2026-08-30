from __future__ import annotations

import json
from pathlib import Path

from yy_industry_research.HTML import 生成出版HTML


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "industry-packs" / "半导体膜材"


def _publication() -> dict:
    return {
        "as_of": "2026-08-30",
        "content": json.loads((PACK / "research_analysis.json").read_text(encoding="utf-8")),
        "facts": json.loads((PACK / "curated_facts.json").read_text(encoding="utf-8"))["facts"],
        "sources": [
            {
                "source_name": "SEMI",
                "source_type": "协会",
                "region": "全球",
                "credibility": 5,
                "parse_status": "已解析",
                "raw_path": "原始资料/全球/semi.html",
                "source_uri": "https://www.semi.org/example",
            },
            {
                "source_name": "中国监管披露",
                "source_type": "监管",
                "region": "中国",
                "credibility": 5,
                "parse_status": "已解析",
                "raw_path": "原始资料/中国/cninfo.pdf",
                "source_uri": "https://static.cninfo.com.cn/example.pdf",
            },
        ],
        "mappings": {"正式关系": [], "待验证关系": []},
        "charts": json.loads((PACK / "charts.json").read_text(encoding="utf-8"))["charts"],
    }


def test_html_contains_print_contract_and_all_sections(tmp_path: Path) -> None:
    output = 生成出版HTML(tmp_path / "report.html", _publication())
    html = output.read_text(encoding="utf-8")

    assert "@page" in html and "size: A4" in html
    assert "#4B2E83" in html and "#FAF9F7" in html
    assert 'class="cover"' in html and 'class="toc"' in html
    assert html.count('class="chart"') >= 12
    assert html.count('class="publication-chapter') == 22
    assert html.rfind("数据来源、原始素材与引用清单") > html.rfind("关键事实—证据—验证矩阵")
    assert html.rfind("数据来源、原始素材与引用清单") > html.rfind("行业 Mapping 与投资机会地图")
    lowered = html.lower()
    assert "<script" not in lowered
    assert "https://fonts" not in lowered
    assert "@import" not in lowered
    assert "foreignobject" not in lowered


def test_html_escapes_research_text_and_keeps_svg_inline(tmp_path: Path) -> None:
    publication = _publication()
    publication["content"]["出版章节"][0]["paragraphs"][0] = '<script>alert("x")</script> & 原文'

    html = 生成出版HTML(tmp_path / "safe.html", publication).read_text(encoding="utf-8")

    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; 原文" in html
    assert "<svg xmlns=" in html
    assert "<script" not in html.lower()
