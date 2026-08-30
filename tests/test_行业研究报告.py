from __future__ import annotations

from pathlib import Path

from yy_industry_research.索引 import 初始化行业索引, 写入来源, 写入文档, 写入事实
from yy_industry_research.资料库 import 初始化资料库
from yy_industry_research.验证 import 执行全量交叉验证
from scripts.行业研究 import _build_run_report


def test_报告_包含交叉验证与来源明细(tmp_path: Path) -> None:
    root = 初始化资料库(tmp_path / "行业库", "半导体膜材", None)
    db_path = root / "行业索引.sqlite"
    初始化行业索引(db_path)

    source_id = 写入来源(
        db_path,
        source_key="test-source-key",
        source_name="测试来源",
        source_type="公司",
        source_uri="https://example.com/report.pdf",
        region="中国",
        source_country="CN",
        language="zh",
        credibility=8,
        title="测试来源",
    )
    raw_file = root / "原始资料" / "中国" / "测试文件.pdf"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text("示例内容", encoding="utf-8")

    doc_id = 写入文档(
        db_path,
        source_id=source_id,
        doc_type="text",
        raw_path=raw_file,
        filename=raw_file.name,
        file_sha256="sha",
        simhash_64="sim",
        parse_status="success",
        content_sha256="csha",
    )

    写入事实(
        db_path,
        source_id=source_id,
        fact_key="行业.半导体膜材.市场规模",
        fact_type="extracted_numeric",
        fact_value="80亿元",
        unit="亿元",
        time_range="2026",
    )

    validation = 执行全量交叉验证(db_path)

    report = {
        "行业": "半导体膜材",
        "资料库": str(root),
        "处理时间": "2026-01-01T00:00:00",
        "输入项数": 1,
        "documents": 1,
        "facts": 1,
        "maps": 1,
        "重复跳过": 0,
        "风险项": 0,
        "parse_fail": 0,
        "validation": validation,
        "sources": ["测试来源 | https://example.com/report.pdf"],
        "count": {"sources": 1, "documents": 1, "facts": 1},
    }

    json_path, md_path = _build_run_report(root, db_path, report, "半导体膜材")
    markdown = md_path.read_text(encoding="utf-8")

    assert "## 13. 关键事实—证据—验证矩阵" in markdown
    assert "## 数据来源、原始素材与引用清单" in markdown
    assert "|来源|类型|地区|可信度|文件|解析状态|原始链接|" in markdown
    assert "https://example.com/report.pdf" in markdown
    assert "## 投资结论仪表盘" in markdown
    assert "**核心结论：**" not in markdown
