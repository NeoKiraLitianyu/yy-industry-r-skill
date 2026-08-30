from __future__ import annotations

from pathlib import Path

import pytest

from yy_industry_research.来源评级 import 评级来源
from yy_industry_research.行业图谱 import 建立证据Mapping
from yy_industry_research.深度研究 import 生成研究框架, 检查研究覆盖
from yy_industry_research.报告 import 生成深度研究报告
from yy_industry_research.策展事实 import 装载策展事实, 装载策展Mapping


_完整正文模块 = [
    "定义与边界",
    "技术与工艺",
    "需求驱动",
    "市场规模",
    "供应链与利润池",
    "竞争格局",
    "中国国产化",
    "可比公司与资本化",
    "一级市场投资判断",
]


def _完整研究内容(*, reference: str = "[F-001]") -> dict:
    sections = []
    for module in _完整正文模块:
        section = {
            "module": module,
            "title": f"{module}分析",
            "核心判断": f"{module}的核心判断。",
            "依据": reference,
            "正文": [f"{module}的连续分析正文。{reference}"],
            "投资含义": [f"{module}的投资含义。"],
        }
        if module == "技术与工艺":
            section["表格"] = [
                {
                    "标题": "关键技术路线对照",
                    "依据": reference,
                    "列": ["路线", "关键材料", "投资含义"],
                    "行": [["ALD", "高k与金属前驱体", "客户验证比规划产能更重要"]],
                }
            ]
        sections.append(section)
    return {
        "version": "1.1.0",
        "as_of": "2026-08-30",
        "执行摘要": {
            "投资评级": "积极关注",
            "核心结论": "机会来自材料验证闭环，而不是名义扩产。",
            "关键判断": ["GAA和高层3D NAND提高单位晶圆薄膜复杂度。"],
            "依据": reference,
        },
        "章节": sections,
    }


def test_来源评级不是单一分数而是多维证据():
    评级 = 评级来源(
        {
            "source_type": "政府协会",
            "source_uri": "https://www.gov.cn/example",
            "published_at": "2026-08-01",
            "is_primary": True,
        },
        基准日期="2026-08-30",
    )

    assert 评级.层级 == "A"
    assert 评级.权威性 == "高"
    assert 评级.直接性 == "一手"
    assert 评级.时效性 == "新近"
    assert 评级.理由


def test_行业Mapping只接纳带证据和验证状态的正式关系():
    行业包 = {
        "nodes": {"材料": ["ALD前驱体"], "工艺": ["ALD"], "应用": ["GAA"]},
        "relations": ["用于", "驱动需求"],
    }
    事实 = [
        {
            "subject": "ALD前驱体",
            "predicate": "用于",
            "object": "GAA",
            "evidence_id": "E-001",
            "source_id": "S-001",
            "verification_status": "已验证",
        },
        {
            "subject": "ALD前驱体",
            "predicate": "驱动需求",
            "object": "先进制程",
            "verification_status": "证据不足",
        },
    ]

    mapping = 建立证据Mapping(行业包, 事实)

    assert len(mapping["正式关系"]) == 1
    assert mapping["正式关系"][0]["evidence_id"] == "E-001"
    assert len(mapping["待验证关系"]) == 1


def test_深度研究框架覆盖技术市场供应链竞争资本化与投资判断():
    框架 = 生成研究框架("半导体膜材")
    必需模块 = {
        "定义与边界",
        "技术与工艺",
        "需求驱动",
        "市场规模",
        "供应链与利润池",
        "竞争格局",
        "中国国产化",
        "可比公司与资本化",
        "一级市场投资判断",
        "风险与反证",
        "数据来源与原始素材",
    }

    assert 必需模块 <= set(框架.模块)
    assert len(框架.研究问题) >= 35


def test_覆盖检查把未交叉验证和无定位来源列为硬缺口(tmp_path: Path):
    结果 = 检查研究覆盖(
        生成研究框架("半导体膜材"),
        事实=[
            {
                "module": "市场规模",
                "claim": "市场规模为100亿元",
                "verification_status": "单一来源",
                "source_uri": "https://example.com",
                "locator": "",
            }
        ],
        来源清单=[{"source_uri": "https://example.com", "raw_path": str(tmp_path / "不存在.pdf")}],
    )

    assert "市场规模" in 结果.未达标模块
    assert 结果.未交叉验证事实 == 1
    assert 结果.缺少定位事实 == 1
    assert 结果.缺少原始素材 == 1


def test_最终报告按证据状态写结论且来源附录必须在最后(tmp_path: Path):
    output = tmp_path / "报告.md"
    生成深度研究报告(
        output,
        行业="半导体膜材",
        资料库=tmp_path,
        事实=[
            {
                "module": "市场规模",
                "claim": "2025年全球市场规模为100亿美元",
                "verification_status": "已验证",
                "source_uri": "https://semi.example/report.pdf",
                "locator": "第12页",
            },
            {
                "module": "中国国产化",
                "claim": "国产化率达到50%",
                "verification_status": "单一来源",
                "source_uri": "https://broker.example/report.pdf",
                "locator": "第8页",
            },
        ],
        来源清单=[
            {
                "source_id": "S-001",
                "source_name": "SEMI",
                "source_uri": "https://semi.example/report.pdf",
                "raw_path": str(tmp_path / "原始资料" / "semi.pdf"),
                "rating": "A",
            }
        ],
        映射={"正式关系": [], "待验证关系": []},
    )

    text = output.read_text(encoding="utf-8")
    assert "2025年全球市场规模为100亿美元" in text
    assert "[已验证]" in text
    assert "国产化率达到50%" in text and "[单一来源]" in text
    assert text.rfind("## 数据来源、原始素材与引用清单") > text.rfind("## 风险、反证与待验证事项")
    assert text.rstrip().endswith("https://semi.example/report.pdf |")


def test_策展事实必须引用已归档来源且两家独立机构才能标记已验证(tmp_path: Path):
    fact_file = tmp_path / "curated_facts.json"
    fact_file.write_text(
        __import__("json").dumps(
            {
                "facts": [
                    {
                        "fact_id": "F-001",
                        "module": "需求驱动",
                        "claim": "GAA提升高k金属栅薄膜复杂度",
                        "verification_status": "已验证",
                        "source_uris": ["https://imec.example/g", "https://tsmc.example/a"],
                        "locator": "imec段落；TSMC年报",
                    },
                    {
                        "fact_id": "F-002",
                        "module": "市场规模",
                        "claim": "2025年市场规模732亿美元",
                        "verification_status": "已验证",
                        "source_uris": ["https://semi.example/en", "https://semi.example/zh"],
                        "locator": "新闻稿",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_dir = tmp_path / "原始资料"
    raw_dir.mkdir()
    catalog = []
    for index, (uri, source_name) in enumerate(
        [
            ("https://imec.example/g", "imec"),
            ("https://tsmc.example/a", "TSMC"),
            ("https://semi.example/en", "SEMI"),
            ("https://semi.example/zh", "SEMI China"),
        ]
    ):
        raw = raw_dir / f"source-{index}.html"
        raw.write_text(uri, encoding="utf-8")
        catalog.append({"source_uri": uri, "source_name": source_name, "raw_path": str(raw)})

    facts = 装载策展事实(fact_file, catalog, 资料库=tmp_path)

    assert facts[0]["verification_status"] == "已验证"
    assert facts[0]["source_uri"] == "https://imec.example/g"
    assert facts[1]["verification_status"] == "单一来源"
    assert "同一来源族" in facts[1]["verification_note"]


def test_策展事实的已验证状态要求每条引用都有库内原文(tmp_path: Path):
    fact_file = tmp_path / "curated_facts.json"
    fact_file.write_text(
        __import__("json").dumps(
            {
                "facts": [
                    {
                        "fact_id": "F-001",
                        "module": "技术与工艺",
                        "claim": "双来源技术事实",
                        "verification_status": "已验证",
                        "source_uris": ["https://a.example/report", "https://b.example/report"],
                        "locator": "A；B",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw = tmp_path / "原始资料" / "a.html"
    raw.parent.mkdir()
    raw.write_text("A", encoding="utf-8")
    catalog = [
        {"source_uri": "https://a.example/report", "source_name": "同名来源", "raw_path": str(raw)},
        {"source_uri": "https://b.example/report", "source_name": "伪造为独立来源"},
    ]

    facts = 装载策展事实(fact_file, catalog, 资料库=tmp_path)

    assert facts[0]["verification_status"] != "已验证"
    assert facts[0]["source_uris"] == ["https://a.example/report"]
    assert "1条引用未归档" in facts[0]["verification_note"]


def test_报告质量门拒绝已验证事实的任一未归档来源(tmp_path: Path):
    output = tmp_path / "report.md"
    raw = tmp_path / "原始资料" / "a.html"
    raw.parent.mkdir()
    raw.write_text("A", encoding="utf-8")
    facts = [
        {
            "fact_id": "F-001",
            "module": "技术与工艺",
            "claim": "双来源技术事实",
            "verification_status": "已验证",
            "source_uris": ["https://a.example/report", "https://b.example/report"],
            "locator": "A；B",
        }
    ]
    sources = [
        {"source_uri": "https://a.example/report", "raw_path": str(raw)},
        {"source_uri": "https://b.example/report", "raw_path": ""},
    ]

    with pytest.raises(ValueError, match="F-001|归档原文"):
        生成深度研究报告(
            output,
            行业="半导体膜材",
            资料库=tmp_path,
            事实=facts,
            来源清单=sources,
            映射={"正式关系": [], "待验证关系": []},
            研究内容=_完整研究内容(reference="[F-001]"),
        )


def test_报告支持一项事实展示多个交叉验证来源(tmp_path: Path):
    output = tmp_path / "report.md"
    生成深度研究报告(
        output,
        行业="半导体膜材",
        资料库=tmp_path,
        事实=[
            {
                "module": "技术与工艺",
                "claim": "前驱体能力由纯度、挥发性和输送共同决定",
                "verification_status": "已验证",
                "source_uri": "https://entegris.example/a",
                "source_uris": ["https://entegris.example/a", "https://adeka.example/b"],
                "locator": "技术资料",
            }
        ],
        来源清单=[],
        映射={"正式关系": [], "待验证关系": []},
    )

    text = output.read_text(encoding="utf-8")
    assert "https://entegris.example/a" in text
    assert "https://adeka.example/b" in text


def test_报告把行业分析内容渲染为正文而不是待回答问题骨架(tmp_path: Path):
    output = tmp_path / "report.md"
    raw_path = tmp_path / "原始资料" / "imec.html"
    raw_path_2 = tmp_path / "原始资料" / "tsmc.html"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text("GAA source", encoding="utf-8")
    raw_path_2.write_text("TSMC source", encoding="utf-8")
    生成深度研究报告(
        output,
        行业="半导体膜材",
        资料库=tmp_path,
        事实=[
            {
                "fact_id": "F-001",
                "module": "技术与工艺",
                "claim": "GAA提高保形沉积要求",
                "verification_status": "已验证",
                "source_uri": "https://imec.example/g",
                "source_uris": ["https://imec.example/g", "https://tsmc.example/a"],
                "locator": "技术路线章节",
            }
        ],
        来源清单=[
            {
                "source_name": "imec",
                "source_uri": "https://imec.example/g",
                "raw_path": str(raw_path),
                "rating": "A",
            },
            {
                "source_name": "TSMC",
                "source_uri": "https://tsmc.example/a",
                "raw_path": str(raw_path_2),
                "rating": "A",
            },
        ],
        映射={"正式关系": [], "待验证关系": []},
        研究内容=_完整研究内容(),
    )

    text = output.read_text(encoding="utf-8")
    assert "## 执行摘要与投资结论" in text
    assert "机会来自材料验证闭环" in text
    assert "技术与工艺的连续分析正文" in text
    assert "|ALD|高k与金属前驱体|客户验证比规划产能更重要|" in text
    assert "[F-001]" in text
    assert "本节待回答问题" not in text


def test_分析正文拒绝不存在或没有归档来源的事实引用(tmp_path: Path):
    with pytest.raises(ValueError, match="不存在的事实引用"):
        生成深度研究报告(
            tmp_path / "missing-fact.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=_完整研究内容(reference="[F-999]"),
        )


def test_分析正文拒绝无任何引用的静态结论和资料库外伪归档(tmp_path: Path):
    no_references = _完整研究内容(reference="")
    with pytest.raises(ValueError, match="必须引用至少一条"):
        生成深度研究报告(
            tmp_path / "bypass.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=no_references,
        )

    model_only = _完整研究内容(reference="内部模型假设，非历史统计")
    with pytest.raises(ValueError, match="执行摘要必须引用"):
        生成深度研究报告(
            tmp_path / "model-only-bypass.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=model_only,
        )

    outside = tmp_path.parent / "伪归档.html"
    outside.write_text("not in library", encoding="utf-8")
    with pytest.raises(ValueError, match="不属于本次资料库归档目录"):
        生成深度研究报告(
            tmp_path / "outside.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[
                {
                    "fact_id": "F-001",
                    "module": "技术与工艺",
                    "claim": "GAA提高保形沉积要求",
                    "verification_status": "已验证",
                    "source_uris": ["https://imec.example/g"],
                    "locator": "技术路线章节",
                }
            ],
            来源清单=[
                {
                    "source_name": "imec",
                    "source_uri": "https://imec.example/g",
                    "raw_path": str(outside),
                }
            ],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=_完整研究内容(),
        )


def test_分析正文拒绝空白段落和不完整语义版本(tmp_path: Path):
    blank = _完整研究内容()
    blank["章节"][0]["正文"] = ["   "]
    with pytest.raises(ValueError, match="非空字符串"):
        生成深度研究报告(
            tmp_path / "blank.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=blank,
        )

    bad_version = _完整研究内容()
    bad_version["version"] = "1."
    with pytest.raises(ValueError, match="版本"):
        生成深度研究报告(
            tmp_path / "bad-version.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=bad_version,
        )

    with pytest.raises(ValueError, match="没有可访问的归档原文"):
        生成深度研究报告(
            tmp_path / "missing-source.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[
                {
                    "fact_id": "F-001",
                    "module": "技术与工艺",
                    "claim": "GAA提高保形沉积要求",
                    "verification_status": "已验证",
                    "source_uris": ["https://imec.example/g"],
                    "locator": "技术路线章节",
                }
            ],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=_完整研究内容(),
        )


def test_分析正文拒绝缺章重复模块和错误表格(tmp_path: Path):
    incomplete = _完整研究内容()
    incomplete["章节"] = incomplete["章节"][:-1]
    with pytest.raises(ValueError, match="九个必需模块"):
        生成深度研究报告(
            tmp_path / "incomplete.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=incomplete,
        )

    malformed = _完整研究内容()
    malformed["章节"][1]["表格"][0]["行"] = [["ALD", "少一列"]]
    with pytest.raises(ValueError, match="表格行列数不一致"):
        生成深度研究报告(
            tmp_path / "malformed.md",
            行业="半导体膜材",
            资料库=tmp_path,
            事实=[],
            来源清单=[],
            映射={"正式关系": [], "待验证关系": []},
            研究内容=malformed,
        )


def test_没有分析内容包时保持旧标题和旧证据矩阵表头(tmp_path: Path):
    output = tmp_path / "legacy.md"
    生成深度研究报告(
        output,
        行业="测试行业",
        资料库=tmp_path,
        事实=[],
        来源清单=[],
        映射={"正式关系": [], "待验证关系": []},
    )

    text = output.read_text(encoding="utf-8")
    assert "## 投资结论仪表盘" in text
    assert "|模块|关键事实|状态|定位|来源|" in text


def test_半导体内容包的概率比例和评分阈值就地标为内部模型假设():
    content_path = Path(__file__).parents[1] / "industry-packs" / "半导体膜材" / "research_analysis.json"
    text = content_path.read_text(encoding="utf-8")

    assert text.count("内部模型假设，非历史统计") >= 3
    assert "70分作为进入深度尽调门槛" in text


def test_策展Mapping按关系词表和独立来源门控正式图谱(tmp_path: Path):
    path = tmp_path / "mapping.json"
    path.write_text(
        __import__("json").dumps(
            {
                "relations": [
                    {
                        "relation_id": "R-001",
                        "subject": "GAA环绕栅极",
                        "predicate": "器件结构驱动需求",
                        "object": "高k介质",
                        "verification_status": "已验证",
                        "source_uris": ["https://imec/x", "https://linx/y"],
                    },
                    {
                        "relation_id": "R-002",
                        "subject": "公司",
                        "predicate": "未允许关系",
                        "object": "材料",
                        "verification_status": "已验证",
                        "source_uris": ["https://imec/x", "https://linx/y"],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    catalog = [
        {"source_uri": "https://imec/x", "source_name": "imec"},
        {"source_uri": "https://linx/y", "source_name": "Linx"},
    ]

    mapping = 装载策展Mapping(path, catalog, {"器件结构驱动需求"})

    assert len(mapping["正式关系"]) == 1
    assert mapping["正式关系"][0]["evidence_id"] == "R-001"
    assert len(mapping["待验证关系"]) == 1
