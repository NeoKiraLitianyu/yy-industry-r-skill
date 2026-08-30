from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from yy_industry_research.出版 import 构建出版模型, 视觉令牌
from yy_industry_research.图表 import 支持图表类型, 渲染图表_svg


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "industry-packs" / "半导体膜材"
CHARTS = PACK / "charts.json"
FACTS = json.loads((PACK / "curated_facts.json").read_text(encoding="utf-8"))["facts"]
MAPPING = json.loads((PACK / "curated_mapping.json").read_text(encoding="utf-8"))["relations"]
CONTENT = json.loads((PACK / "research_analysis.json").read_text(encoding="utf-8"))
VALID_FACT_IDS = {
    str(item["fact_id"])
    for item in FACTS
    if str(item.get("verification_status") or "") in {"已验证", "单一来源"}
}
FACTS_BY_ID = {str(item["fact_id"]): item for item in FACTS if item.get("fact_id")}
MARKDOWN = "# 半导体膜材行业研究\n\n用于测试出版模型。"


def _load_chart_specs() -> list[dict[str, object]]:
    return json.loads(CHARTS.read_text(encoding="utf-8"))["charts"]


def _构造最小事实(
    fact_id: str,
    *,
    status: str = "已验证",
    source_uri: str | None = None,
) -> dict[str, object]:
    return {
        "fact_id": fact_id,
        "module": "定义与边界",
        "claim": f"{fact_id} claim",
        "verification_status": status,
        "source_uris": [source_uri or f"https://example.com/{fact_id}.pdf"],
        "locator": f"{fact_id} locator",
    }


def _构造最小内容(
    *,
    executive_basis: str = "[F-001]",
    section_basis: str = "[F-002]",
    paragraph: str = "章节正文 [F-002]",
) -> dict[str, object]:
    return {
        "as_of": "2026-08-30",
        "执行摘要": {
            "核心结论": "这是执行摘要。",
            "依据": executive_basis,
        },
        "章节": [
            {
                "module": "定义与边界",
                "title": "行业边界",
                "依据": section_basis,
                "正文": [paragraph],
            }
        ],
    }


def _构造最小图表(*, fact_ids: list[str] | None = None, model_label: str | None = None) -> dict[str, object]:
    spec: dict[str, object] = {
        "id": "chart-mini",
        "type": "bar",
        "title": "最小柱状图",
        "as_of": "2026-08-30",
        "basis": "柱状图依据",
        "bars": [{"label": "A", "value": 1, "unit": "x"}],
    }
    if fact_ids is not None:
        spec["fact_ids"] = fact_ids
    if model_label is not None:
        spec["model_label"] = model_label
    return spec


def _为事实生成可访问来源(tmp_path: Path, facts: list[dict[str, object]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    archive = tmp_path / "sources"
    archive.mkdir(parents=True, exist_ok=True)
    for index, fact in enumerate(facts, start=1):
        for uri in fact.get("source_uris", []):
            uri_text = str(uri)
            if not uri_text or uri_text in seen:
                continue
            raw_path = archive / f"source-{index:02d}-{len(seen):02d}.txt"
            raw_path.write_text(f"archived for {uri_text}", encoding="utf-8")
            sources.append({"source_uri": uri_text, "raw_path": str(raw_path)})
            seen.add(uri_text)
    return sources


def _构造十二张最小图表(fact_id: str) -> list[dict[str, object]]:
    specs = []
    for index in range(1, 13):
        spec = _构造最小图表(fact_ids=[fact_id])
        spec["id"] = f"chart-mini-{index:02d}"
        specs.append(spec)
    return specs


def test_视觉令牌固定为紫色出版主题() -> None:
    tokens = 视觉令牌()

    assert tokens == {
        "primary_purple": "#4B2E83",
        "violet": "#7456A8",
        "surface_soft": "#F4F0FA",
        "paper": "#FAF9F7",
        "ink": "#211B2B",
        "muted_text": "#706779",
        "rule": "#DED6E8",
    }


def test_半导体行业包声明至少十四个可追溯图表且覆盖七种类型() -> None:
    specs = _load_chart_specs()
    types = {str(item["type"]) for item in specs}

    assert len(specs) >= 14
    assert len({item["id"] for item in specs}) == len(specs)
    assert 支持图表类型() == {"bar", "heatmap", "flow", "matrix", "ladder", "radar", "evidence"}
    assert types == 支持图表类型()
    assert all(str(item.get("title") or "").strip() for item in specs)
    assert all(str(item.get("as_of") or "").strip() for item in specs)
    assert all(str(item.get("basis") or "").strip() for item in specs)


def test_图表声明只引用现有有效事实或显式标注内部模型假设() -> None:
    specs = _load_chart_specs()

    for spec in specs:
        fact_ids = [str(item) for item in spec.get("fact_ids", [])]
        model_label = str(spec.get("model_label") or "")
        if fact_ids:
            assert set(fact_ids) <= VALID_FACT_IDS
        elif spec.get("fact_scope") == "all":
            assert spec["type"] == "evidence"
        else:
            assert model_label == "内部模型假设"


def test_出版模型保留研究内容并附带图表声明校验结果(tmp_path: Path) -> None:
    sources = _为事实生成可访问来源(tmp_path, FACTS)
    model = 构建出版模型(
        markdown=MARKDOWN,
        content=CONTENT,
        facts=FACTS,
        sources=sources,
        mappings=MAPPING,
        chart_specs=_load_chart_specs(),
        资料库=tmp_path,
    )

    assert model["as_of"] == "2026-08-30"
    assert len(model["charts"]) >= 14
    assert len(model["fact_index"]) >= 14
    assert len(model["claim_declarations"]) >= 14
    assert model["content"]["执行摘要"]["核心结论"]
    assert model["markdown"] == MARKDOWN


def test_出版模型校验Mapping并保留正式待验证标签(tmp_path: Path) -> None:
    raw_a = tmp_path / "原始资料" / "a.html"
    raw_b = tmp_path / "原始资料" / "b.html"
    raw_company = tmp_path / "原始资料" / "company.html"
    raw_a.parent.mkdir(parents=True)
    raw_a.write_text("A", encoding="utf-8")
    raw_b.write_text("B", encoding="utf-8")
    raw_company.write_text("company", encoding="utf-8")
    facts = [
        {
            "fact_id": "F-001",
            "module": "定义与边界",
            "claim": "ALD前驱体对应ALD",
            "verification_status": "已验证",
            "source_uris": ["https://a.example/report", "https://b.example/report"],
            "mapping_relations": [
                {"subject": "ALD前驱体", "predicate": "对应工艺", "object": "ALD"}
            ],
            "locator": "A;B",
        },
        {
            "fact_id": "F-002",
            "module": "竞争格局",
            "claim": "公司单一来源客户状态",
            "verification_status": "单一来源",
            "source_uris": ["https://company.example/report"],
            "locator": "company",
        },
    ]
    sources = [
        {"source_uri": "https://a.example/report", "source_name": "imec", "raw_path": str(raw_a)},
        {"source_uri": "https://b.example/report", "source_name": "Linx", "raw_path": str(raw_b)},
        {"source_uri": "https://company.example/report", "source_name": "Lam Research", "raw_path": str(raw_company)},
    ]
    mappings = {
        "正式关系": [
            {
                "relation_id": "R-OK",
                "subject": "ALD前驱体",
                "predicate": "对应工艺",
                "object": "ALD",
                "verification_status": "已验证",
                "fact_ids": ["F-001"],
                "source_uris": ["https://a.example/report", "https://b.example/report"],
            },
            {
                "relation_id": "R-FORCED-SINGLE",
                "subject": "强塞公司",
                "predicate": "客户状态",
                "object": "强塞客户状态",
                "verification_status": "已验证",
                "fact_ids": ["F-002"],
                "source_uris": ["https://company.example/report"],
            },
        ],
        "待验证关系": [
            {
                "relation_id": "R-PENDING",
                "subject": "待验证公司",
                "predicate": "供应产品",
                "object": "待验证产品",
                "verification_status": "单一来源",
                "fact_ids": ["F-002"],
                "source_uris": ["https://company.example/report"],
            }
        ],
    }

    model = 构建出版模型(
        markdown=MARKDOWN,
        content=_构造最小内容(section_basis="[F-001]", paragraph="章节正文 [F-001]"),
        facts=facts,
        sources=sources,
        mappings=mappings,
        chart_specs=_构造十二张最小图表("F-001"),
        资料库=tmp_path,
    )

    assert isinstance(model["mappings"], dict)
    assert [item["relation_id"] for item in model["mappings"]["正式关系"]] == ["R-OK"]
    assert {item["relation_id"] for item in model["mappings"]["待验证关系"]} == {"R-FORCED-SINGLE", "R-PENDING"}


def test_出版模型拒绝把已验证事实洗成语义无关的mapping(tmp_path: Path) -> None:
    raw_a = tmp_path / "原始资料" / "a.html"
    raw_b = tmp_path / "原始资料" / "b.html"
    raw_a.parent.mkdir(parents=True)
    raw_a.write_text("A", encoding="utf-8")
    raw_b.write_text("B", encoding="utf-8")
    facts = [
        {
            "fact_id": "F-001",
            "module": "定义与边界",
            "claim": "ALD前驱体对应ALD",
            "verification_status": "已验证",
            "source_uris": ["https://a.example/report", "https://b.example/report"],
            "mapping_relations": [
                {"subject": "ALD前驱体", "predicate": "对应工艺", "object": "ALD"}
            ],
            "locator": "A;B",
        }
    ]
    sources = [
        {"source_uri": "https://a.example/report", "source_name": "伪造机构甲", "raw_path": str(raw_a)},
        {"source_uri": "https://b.example/report", "source_name": "伪造机构乙", "raw_path": str(raw_b)},
    ]
    mapping = {
        "正式关系": [
            {
                "relation_id": "R-LAUNDERED",
                "subject": "光刻胶",
                "predicate": "对应工艺",
                "object": "CMP",
                "verification_status": "已验证",
                "fact_ids": ["F-001"],
                "source_uris": ["https://a.example/report", "https://b.example/report"],
            }
        ],
        "待验证关系": [],
    }

    model = 构建出版模型(
        markdown=MARKDOWN,
        content={"as_of": "2026-08-30"},
        facts=facts,
        sources=sources,
        mappings=mapping,
        chart_specs=[_构造最小图表(fact_ids=["F-001"], model_label="内部模型假设") for _ in range(14)],
        资料库=tmp_path,
    )

    assert not model["mappings"]["正式关系"]
    assert "引用事实未结构化支持该关系" in model["mappings"]["待验证关系"][0]["mapping_gate_note"]


@pytest.mark.parametrize("chart_id", [f"chart-{index:02d}" for index in range(1, 15)])
def test_每张图都能渲染为离线安全_svg(chart_id: str) -> None:
    spec = next(item for item in _load_chart_specs() if item["id"] == chart_id)
    svg = 渲染图表_svg(spec, FACTS_BY_ID)
    root = ET.fromstring(svg)

    assert svg.startswith("<svg xmlns=")
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert "<title>" in svg
    assert spec["title"] in svg
    assert str(spec["as_of"]) in svg
    assert str(spec["basis"]) in svg
    assert "#4B2E83" in svg
    assert "<script" not in svg
    assert "<foreignObject" not in svg
    assert svg.count("http://www.w3.org/2000/svg") == 1
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in svg
    assert "xlink:href" not in svg


def test_svg会转义用户文本且拒绝缺失事实依据() -> None:
    spec = {
        "id": "escape-check",
        "type": "matrix",
        "title": '矩阵 <b>& "quoted"',
        "as_of": "2026-08-30",
        "basis": 'basis <tag> & "quoted"',
        "fact_ids": ["F-001"],
        "rows": [
            {"label": '行<&>"', "cells": [{"label": '值<&>"', "tone": "high"}]},
        ],
        "columns": ['列<&>"'],
    }

    svg = 渲染图表_svg(spec, FACTS_BY_ID)
    assert "&lt;b&gt;" in svg
    assert "&amp;" in svg
    assert "&quot;quoted&quot;" in svg

    with pytest.raises(ValueError, match="不存在的事实引用"):
        渲染图表_svg(
            {
                "id": "missing-fact",
                "type": "bar",
                "title": "缺失事实",
                "as_of": "2026-08-30",
                "basis": "引用不存在事实",
                "fact_ids": ["F-999"],
                "bars": [{"label": "A", "value": 1, "unit": "x"}],
            },
            FACTS_BY_ID,
        )


def test_出版模型拒绝执行摘要引用证据不足事实(tmp_path: Path) -> None:
    facts = [
        _构造最小事实("F-001", status="证据不足"),
        _构造最小事实("F-002"),
    ]
    sources = _为事实生成可访问来源(tmp_path, facts)

    with pytest.raises(ValueError, match="执行摘要.*证据不足|执行摘要.*不允许"):
        构建出版模型(
            markdown=MARKDOWN,
            content=_构造最小内容(),
            facts=facts,
            sources=sources,
            mappings=[],
            chart_specs=[_构造最小图表(fact_ids=["F-002"])],
        )


def test_出版模型拒绝章节引用不存在事实(tmp_path: Path) -> None:
    facts = [
        _构造最小事实("F-001"),
        _构造最小事实("F-002"),
    ]
    sources = _为事实生成可访问来源(tmp_path, facts)

    with pytest.raises(ValueError, match="section|章节|F-999|不存在"):
        构建出版模型(
            markdown=MARKDOWN,
            content=_构造最小内容(section_basis="[F-999]", paragraph="章节正文 [F-999]"),
            facts=facts,
            sources=sources,
            mappings=[],
            chart_specs=[_构造最小图表(fact_ids=["F-001"])],
        )


def test_出版模型拒绝图表引用缺少可访问归档原文的事实(tmp_path: Path) -> None:
    facts = [
        _构造最小事实("F-001"),
        _构造最小事实("F-002"),
    ]
    sources = _为事实生成可访问来源(tmp_path, [facts[0]])

    with pytest.raises(ValueError, match="F-002|原文|raw_path|来源"):
        构建出版模型(
            markdown=MARKDOWN,
            content=_构造最小内容(section_basis="[F-001]", paragraph="章节正文 [F-001]"),
            facts=facts,
            sources=sources,
            mappings=[],
            chart_specs=[_构造最小图表(fact_ids=["F-002"])],
        )


def test_chart14_从传入事实实时聚合证据覆盖而非静态数字() -> None:
    spec = next(item for item in _load_chart_specs() if item["id"] == "chart-14")
    assert spec.get("fact_scope") == "all"
    assert not spec.get("fact_ids")
    assert {"F-102", "F-148", "F-158"} <= set(FACTS_BY_ID)
    relevant_facts = list(FACTS_BY_ID.values())
    verified = sum(1 for fact in relevant_facts if fact.get("verification_status") == "已验证")
    single = sum(1 for fact in relevant_facts if fact.get("verification_status") == "单一来源")
    gap = len(relevant_facts) - verified - single
    svg = 渲染图表_svg(spec, FACTS_BY_ID)

    assert not spec.get("segments")
    assert f"已验证 {verified}" in svg
    assert f"单一来源 {single}" in svg
    assert f"研究缺口/模型 {gap}" in svg

    controlled_facts = {
        "F-001": _构造最小事实("F-001", status="已验证"),
        "F-102": _构造最小事实("F-102", status="单一来源"),
        "F-158": _构造最小事实("F-158", status="存在冲突"),
    }
    controlled_svg = 渲染图表_svg(spec, controlled_facts)
    assert "已验证 1" in controlled_svg
    assert "单一来源 1" in controlled_svg
    assert "研究缺口/模型 1" in controlled_svg


def test_出版模型拒绝伪装成正式关系的单一来源mapping(tmp_path: Path) -> None:
    facts = [_构造最小事实("F-001"), _构造最小事实("F-002")]
    sources = _为事实生成可访问来源(tmp_path, facts)
    mapping = {
        "正式关系": [
            {
                "relation_id": "R-X",
                "subject": "A",
                "predicate": "对应工艺",
                "object": "B",
                "verification_status": "单一来源",
                "source_uris": facts[0]["source_uris"],
                "fact_ids": ["F-001"],
            }
        ],
        "待验证关系": [],
    }

    model = 构建出版模型(
        markdown=MARKDOWN,
        content=_构造最小内容(),
        facts=facts,
        sources=sources,
        mappings=mapping,
        chart_specs=_构造十二张最小图表("F-001"),
        资料库=tmp_path,
    )

    assert not model["mappings"]["正式关系"]
    assert len(model["mappings"]["待验证关系"]) == 1


def test_出版模型拒绝无关双来源和未授权谓词洗白mapping(tmp_path: Path) -> None:
    facts = [_构造最小事实("F-001", status="单一来源", source_uri="https://company.example/report")]
    sources = _为事实生成可访问来源(tmp_path, facts)
    for index, uri in enumerate(("https://a.example/report", "https://b.example/report"), start=1):
        raw = tmp_path / "sources" / f"unrelated-{index}.txt"
        raw.write_text("unrelated", encoding="utf-8")
        sources.append({"source_uri": uri, "raw_path": str(raw), "source_name": f"机构{index}"})
    mapping = {
        "正式关系": [{
            "relation_id": "R-WASH",
            "subject": "A",
            "predicate": "未授权关系",
            "object": "B",
            "verification_status": "已验证",
            "fact_ids": ["F-001"],
            "source_uris": ["https://a.example/report", "https://b.example/report"],
        }],
        "待验证关系": [],
    }

    model = 构建出版模型(
        markdown=MARKDOWN,
        content={"as_of": "2026-08-30"},
        facts=facts,
        sources=sources,
        mappings=mapping,
        chart_specs=[_构造最小图表(fact_ids=["F-001"], model_label="内部模型假设") for _ in range(14)],
        资料库=tmp_path,
    )

    assert not model["mappings"]["正式关系"]
    note = model["mappings"]["待验证关系"][0]["mapping_gate_note"]
    assert "关系谓词未获准" in note
    assert "关系来源未对应引用事实来源" in note


def test_出版模型用资料库边界拒绝双来源库外mapping(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    facts = [{**_构造最小事实("F-001"), "source_uris": ["https://a.example/report", "https://b.example/report"]}]
    sources = []
    for index, uri in enumerate(facts[0]["source_uris"], start=1):
        raw = tmp_path / f"outside-{index}.txt"
        raw.write_text("outside", encoding="utf-8")
        sources.append({"source_uri": uri, "source_name": f"机构{index}", "raw_path": str(raw)})
    mapping = {
        "正式关系": [{
            "relation_id": "R-OUTSIDE",
            "subject": "ALD前驱体",
            "predicate": "对应工艺",
            "object": "ALD",
            "verification_status": "已验证",
            "fact_ids": ["F-001"],
            "source_uris": facts[0]["source_uris"],
        }],
        "待验证关系": [],
    }

    model = 构建出版模型(
        markdown=MARKDOWN,
        content={"as_of": "2026-08-30"},
        facts=facts,
        sources=sources,
        mappings=mapping,
        chart_specs=_构造十二张最小图表("F-001") + [
            {**_构造最小图表(fact_ids=["F-001"]), "id": "chart-extra-13"},
            {**_构造最小图表(fact_ids=["F-001"]), "id": "chart-extra-14"},
        ],
        资料库=library,
    )

    assert not model["mappings"]["正式关系"]
    assert "原始素材未归档" in model["mappings"]["待验证关系"][0]["mapping_gate_note"]


def test_出版模型全事实图允许冲突与缺口进入证据结构(tmp_path: Path) -> None:
    facts = [_构造最小事实("F-001"), _构造最小事实("F-002", status="存在冲突")]
    sources = _为事实生成可访问来源(tmp_path, facts)
    all_scope = {
        "id": "chart-all",
        "type": "evidence",
        "title": "全事实证据结构",
        "as_of": "2026-08-30",
        "basis": "覆盖全部状态",
        "fact_scope": "all",
    }
    charts = [all_scope]
    for index in range(1, 14):
        spec = _构造最小图表(fact_ids=["F-001"])
        spec["id"] = f"chart-regular-{index:02d}"
        charts.append(spec)

    model = 构建出版模型(
        markdown=MARKDOWN,
        content={"as_of": "2026-08-30"},
        facts=facts,
        sources=sources,
        mappings=[],
        chart_specs=charts,
    )

    chart = next(item for item in model["charts"] if item["id"] == "chart-all")
    assert chart["fact_ids"] == ["F-001", "F-002"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_出版模型拒绝非22章或错序编号(mutation: str) -> None:
    content = json.loads(json.dumps(CONTENT, ensure_ascii=False))
    if mutation == "missing":
        content["出版章节"].pop()
    else:
        content["出版章节"][1]["id"] = "P-01"

    with pytest.raises(ValueError, match="22|P-01|连续"):
        构建出版模型(
            markdown=MARKDOWN,
            content=content,
            facts=[],
            sources=[],
            mappings=[],
            chart_specs=[],
        )


def test_svg_trace同时公开内部模型假设与事实锚点() -> None:
    svg = 渲染图表_svg(
        _构造最小图表(fact_ids=["F-001"], model_label="内部模型假设"),
        {"F-001": FACTS_BY_ID["F-001"]},
    )

    assert "内部模型假设；事实锚点：F-001" in svg


@pytest.mark.parametrize(
    ("label", "spec"),
    [
        (
            "bar-empty",
            {
                "id": "bar-empty",
                "type": "bar",
                "title": "空柱状图",
                "as_of": "2026-08-30",
                "basis": "invalid",
                "fact_ids": ["F-001"],
                "bars": [],
            },
        ),
        (
            "heatmap-dimension",
            {
                "id": "heatmap-dimension",
                "type": "heatmap",
                "title": "热力图",
                "as_of": "2026-08-30",
                "basis": "invalid",
                "fact_ids": ["F-001"],
                "columns": ["A", "B"],
                "rows": [{"label": "r1", "cells": [{"label": "x", "tone": "high"}]}],
            },
        ),
        (
            "flow-edge",
            {
                "id": "flow-edge",
                "type": "flow",
                "title": "流程图",
                "as_of": "2026-08-30",
                "basis": "invalid",
                "fact_ids": ["F-001"],
                "nodes": [{"id": "n1", "label": "A", "column": 0, "row": 0}],
                "links": [{"from": "n1", "to": "missing"}],
            },
        ),
        (
            "matrix-dimension",
            {
                "id": "matrix-dimension",
                "type": "matrix",
                "title": "矩阵",
                "as_of": "2026-08-30",
                "basis": "invalid",
                "fact_ids": ["F-001"],
                "columns": ["A", "B"],
                "rows": [{"label": "r1", "cells": [{"label": "1"}, {"label": "2"}, {"label": "3"}]}],
            },
        ),
        (
            "ladder-empty",
            {
                "id": "ladder-empty",
                "type": "ladder",
                "title": "阶梯图",
                "as_of": "2026-08-30",
                "basis": "invalid",
                "fact_ids": ["F-001"],
                "steps": [],
            },
        ),
        (
            "radar-length",
            {
                "id": "radar-length",
                "type": "radar",
                "title": "雷达图",
                "as_of": "2026-08-30",
                "basis": "invalid",
                "fact_ids": ["F-001"],
                "axes": ["客户证据", "成膜性能"],
                "values": [80],
            },
        ),
        (
            "evidence-empty",
            {
                "id": "evidence-empty",
                "type": "evidence",
                "title": "证据图",
                "as_of": "2026-08-30",
                "basis": "invalid",
                "fact_ids": ["F-001"],
                "segments": [],
            },
        ),
    ],
)
def test_非法图表规格必须抛出ValueError而不是静默回退(label: str, spec: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="图表|spec|数据|维度|数值|节点|边|axes|evidence"):
        渲染图表_svg(spec, FACTS_BY_ID)
