from __future__ import annotations

import json
import re
from pathlib import Path

from yy_industry_research.报告 import 生成深度研究报告


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "industry-packs" / "半导体膜材"
ANALYSIS = PACK / "research_analysis.json"
FACTS = PACK / "curated_facts.json"
MAPPING = PACK / "curated_mapping.json"
TAXONOMY = PACK / "taxonomy.json"

_FACT_REF = re.compile(r"\[(F-\d+)\]")
_LEGACY_MODULES = [
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
_REQUIRED_CHAIN = ["对应工艺", "形成薄膜", "用于器件", "面向节点", "供应产品", "客户状态"]
_DIRECTED_PATH_STEPS = [
    ("材料", "对应工艺", "工艺"),
    ("工艺", "形成薄膜", "薄膜"),
    ("薄膜", "用于器件", "器件/应用"),
    ("器件/应用", "面向节点", "节点/结构"),
    ("节点/结构", "节点关联公司", "公司"),
    ("公司", "供应产品", "产品"),
    ("产品", "客户状态", "客户状态"),
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fact_ids(facts: list[dict]) -> set[str]:
    return {str(item["fact_id"]) for item in facts}


def _sources_for(facts: list[dict], archive_root: Path) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    archive_root.mkdir(parents=True, exist_ok=True)
    for fact in facts:
        for uri in fact.get("source_uris", []):
            uri_text = str(uri)
            if not uri_text or uri_text in seen:
                continue
            seen.add(uri_text)
            raw_path = archive_root / f"source-{len(seen):03d}.txt"
            raw_path.write_text(f"archived source for {uri_text}", encoding="utf-8")
            sources.append({"source_uri": uri_text, "raw_path": str(raw_path)})
    return sources


def _layers_by_node(taxonomy: dict) -> dict[str, str]:
    return {
        str(node): str(layer)
        for layer, nodes in taxonomy.get("layers", {}).items()
        for node in nodes
    }


def _find_directed_layer_path(relations: list[dict], taxonomy: dict) -> list[dict]:
    layers = _layers_by_node(taxonomy)
    by_subject: dict[str, list[dict]] = {}
    for relation in relations:
        by_subject.setdefault(str(relation.get("subject") or ""), []).append(relation)

    def search(current: str, step_index: int, path: list[dict]) -> list[dict] | None:
        if step_index == len(_DIRECTED_PATH_STEPS):
            return path
        expected_subject_layer, expected_predicate, expected_object_layer = _DIRECTED_PATH_STEPS[step_index]
        if layers.get(current) != expected_subject_layer:
            return None
        for relation in by_subject.get(current, []):
            target = str(relation.get("object") or "")
            if relation.get("predicate") != expected_predicate:
                continue
            if layers.get(target) != expected_object_layer:
                continue
            result = search(target, step_index + 1, path + [relation])
            if result is not None:
                return result
        return None

    for node, layer in layers.items():
        if layer != _DIRECTED_PATH_STEPS[0][0]:
            continue
        found = search(node, 0, [])
        if found is not None:
            return found
    return []


def test_publication_content_has_twenty_two_granular_chapters_and_keeps_legacy_modules() -> None:
    data = _load(ANALYSIS)
    facts = _load(FACTS)["facts"]
    valid_fact_ids = _fact_ids(facts)

    assert [section["module"] for section in data["章节"]] == _LEGACY_MODULES
    chapters = data["出版章节"]
    assert len(chapters) == 22
    assert [chapter["id"] for chapter in chapters] == [f"P-{index:02d}" for index in range(1, 23)]

    for chapter in chapters:
        assert {key for key in ("id", "title", "module", "thesis", "paragraphs", "fact_ids", "tables", "investment_implications", "uncertainties")} <= set(chapter)
        assert chapter["module"] in _LEGACY_MODULES or chapter["module"] in {"情景分析", "风险与反证", "数据来源与原始素材"}
        assert len(chapter["paragraphs"]) >= 2
        if chapter["id"] != "P-22":
            assert chapter["fact_ids"], chapter["id"]
        assert set(chapter["fact_ids"]) <= valid_fact_ids
        referenced = {
            fact_id
            for paragraph in chapter["paragraphs"]
            for fact_id in _FACT_REF.findall(str(paragraph))
        }
        assert referenced <= set(chapter["fact_ids"]), chapter["id"]
        assert referenced or chapter["id"] == "P-22"


def test_every_formal_fact_has_required_provenance_and_quality_gate_fields() -> None:
    facts = _load(FACTS)["facts"]

    assert len(facts) >= 100
    assert len(_fact_ids(facts)) == len(facts)
    for fact in facts:
        assert str(fact.get("fact_id") or "").startswith("F-")
        assert str(fact.get("module") or "").strip()
        assert str(fact.get("claim") or "").strip()
        assert fact.get("verification_status") in {"已验证", "单一来源", "存在冲突", "证据不足"}
        assert fact.get("source_uris")
        assert str(fact.get("locator") or "").strip()
        assert str(fact.get("as_of") or "").strip()
        if fact["verification_status"] == "单一来源":
            assert len(fact["source_uris"]) == 1 or "同一来源族" in str(fact.get("verification_note") or "")


def test_mapping_covers_material_to_customer_chain_with_fact_provenance() -> None:
    facts = _load(FACTS)["facts"]
    valid_fact_ids = _fact_ids(facts)
    relations = _load(MAPPING)["relations"]
    predicates = {item["predicate"] for item in relations}

    assert set(_REQUIRED_CHAIN) <= predicates
    for relation in relations:
        assert relation.get("fact_ids"), relation.get("relation_id")
        assert set(relation["fact_ids"]) <= valid_fact_ids
        assert relation.get("source_uris"), relation.get("relation_id")
        assert relation.get("verification_status") in {"已验证", "单一来源", "待验证"}

    chain_objects = {item["object"] for item in relations if item["predicate"] in _REQUIRED_CHAIN}
    assert {"ALD", "High-k栅介质薄膜", "GAA环绕栅极", "N2/A14", "DIPAS/BDEAS/HCDS/TEOS前驱体", "客户验证状态待披露"} <= chain_objects


def test_curated_mapping_has_real_directed_path_from_material_to_customer_status() -> None:
    facts = _load(FACTS)["facts"]
    facts_by_id = {str(fact["fact_id"]): fact for fact in facts}
    relations = _load(MAPPING)["relations"]
    taxonomy = _load(TAXONOMY)

    path = _find_directed_layer_path(relations, taxonomy)

    assert path, "curated_mapping must expose a directed material->process->film->device->node->company->product->customer-status path"
    assert [edge["predicate"] for edge in path] == [step[1] for step in _DIRECTED_PATH_STEPS]
    for edge, (subject_layer, _predicate, object_layer) in zip(path, _DIRECTED_PATH_STEPS):
        assert _layers_by_node(taxonomy)[edge["subject"]] == subject_layer
        assert _layers_by_node(taxonomy)[edge["object"]] == object_layer
        assert edge.get("fact_ids"), edge.get("relation_id")
        assert edge.get("source_uris"), edge.get("relation_id")
        assert edge.get("status") in {"已验证", "待验证"}, edge.get("relation_id")
        assert edge.get("verification_status") in {"已验证", "单一来源"}, edge.get("relation_id")
        relation_uris = {str(uri) for uri in edge.get("source_uris", [])}
        fact_uris = {
            str(uri)
            for fact_id in edge.get("fact_ids", [])
            for uri in facts_by_id[str(fact_id)].get("source_uris", [])
        }
        assert relation_uris <= fact_uris, edge.get("relation_id")
        if edge.get("source_basis") == "单一公司口径":
            assert edge["verification_status"] == "单一来源", edge.get("relation_id")
            assert edge["status"] == "待验证", edge.get("relation_id")

    graph = {}
    for relation in relations:
        graph.setdefault(relation["subject"], []).append(relation)

    expected_nodes = [
        "PVD高纯溅射靶材",
        "PVD物理气相沉积",
        "导电层/阻挡层/接触层",
        "晶圆制造金属化",
        "90-3nm",
        "江丰电子",
        "钽/铜靶材（90-3nm）",
        "客户侧公开验证缺口",
    ]
    expected_predicates = ["对应工艺", "形成薄膜", "用于器件", "面向节点", "节点关联公司", "供应产品", "客户状态"]
    for start, end, predicate in zip(expected_nodes, expected_nodes[1:], expected_predicates):
        assert any(item["object"] == end and item["predicate"] == predicate for item in graph.get(start, [])), (start, predicate, end)


def test_taxonomy_names_key_material_process_device_and_package_branches() -> None:
    taxonomy = _load(TAXONOMY)
    node_names = set(taxonomy["nodes"])
    layer_text = json.dumps(taxonomy.get("layers", {}), ensure_ascii=False)

    assert {"ALD前驱体", "CVD前驱体", "High-k介质", "Low-k介质", "PVD高纯溅射靶材"} <= node_names
    assert {"GAA环绕栅极", "DRAM电容", "3D NAND高深宽比结构", "先进封装薄膜"} <= node_names
    assert "金属化" in layer_text
    assert "先进封装" in layer_text


def test_f101_source_and_locator_match_semi_techcet_public_record() -> None:
    fact = next(item for item in _load(FACTS)["facts"] if item["fact_id"] == "F-101")
    source_text = " ".join(fact["source_uris"]).lower()
    claim_and_locator = f"{fact.get('claim', '')} {fact.get('locator', '')}"

    assert "semi.org" in source_text
    assert "techcet.com" in source_text
    assert "SEMI" in claim_and_locator
    assert "TECHCET" in claim_and_locator
    assert "Materials Market Data" in claim_and_locator or "CVD/ALD" in claim_and_locator
    assert not any(token in claim_and_locator for token in ("Yixin", "TDX", "MCP", "公开搜索"))


def test_f148_f149_distinguish_certification_stage_from_order_process() -> None:
    facts = {item["fact_id"]: item for item in _load(FACTS)["facts"]}
    f148 = facts["F-148"]["claim"]
    f149 = facts["F-149"]["claim"]

    assert f148 != f149
    assert "认证阶段" in f148 or "认证门槛" in f148
    assert "订单流程" not in f148
    assert "订单流程" in f149 or "月度或季度订单" in f149


def test_report_renders_publication_chapters_without_bypassing_fact_archive_gate(tmp_path: Path) -> None:
    content = _load(ANALYSIS)
    facts = _load(FACTS)["facts"]
    output = tmp_path / "report.md"

    生成深度研究报告(
        output,
        行业="半导体膜材",
        资料库=tmp_path,
        事实=facts,
        来源清单=_sources_for(facts, tmp_path / "原始资料"),
        映射={"正式关系": _load(MAPPING)["relations"], "待验证关系": []},
        研究内容=content,
    )

    text = output.read_text(encoding="utf-8")
    assert "## 1. 执行摘要与投资结论" in text
    assert "## 22. 事实—原文—定位—验证矩阵和来源附录" in text
    assert "## 23. 行业 Mapping 与投资机会地图" in text
    assert "## 10. 3D NAND 高深宽比和填充需求" in text
    assert "## 9. DRAM 与未来 3D DRAM" in text
    assert "本节待回答问题" not in text
    assert "## 24. 情景分析、敏感性与催化剂" not in text
    assert "## 25. 风险、反证与待验证事项" not in text
    assert text.index("## 23. 行业 Mapping 与投资机会地图") < text.index("## 24. 关键事实—证据—验证矩阵")
    assert text.index("## 24. 关键事实—证据—验证矩阵") < text.index("## 数据来源、原始素材与引用清单")


def test_report_regates_caller_forced_formal_mappings(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    raw_a = tmp_path / "原始资料" / "a.html"
    raw_b = tmp_path / "原始资料" / "b.html"
    raw_company = tmp_path / "原始资料" / "company.html"
    raw_a.parent.mkdir(parents=True)
    raw_a.write_text("A", encoding="utf-8")
    raw_b.write_text("B", encoding="utf-8")
    raw_company.write_text("company", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.html"
    outside.write_text("outside", encoding="utf-8")
    sources = [
        {"source_uri": "https://a.example/report", "source_name": "imec", "raw_path": str(raw_a)},
        {"source_uri": "https://b.example/report", "source_name": "Linx", "raw_path": str(raw_b)},
        {"source_uri": "https://company.example/report", "source_name": "Lam Research", "raw_path": str(raw_company)},
        {"source_uri": "https://outside.example/report", "source_name": "Outside", "raw_path": str(outside)},
    ]
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
            "claim": "公司披露客户状态",
            "verification_status": "单一来源",
            "source_uris": ["https://company.example/report"],
            "locator": "company",
        },
        {
            "fact_id": "F-003",
            "module": "风险与反证",
            "claim": "冲突事实",
            "verification_status": "存在冲突",
            "source_uris": ["https://a.example/report", "https://b.example/report"],
            "locator": "conflict",
        },
        {
            "fact_id": "F-004",
            "module": "定义与边界",
            "claim": "资料库外事实",
            "verification_status": "已验证",
            "source_uris": ["https://outside.example/report"],
            "locator": "outside",
        },
    ]
    relations = [
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
            "subject": "强塞单源公司",
            "predicate": "客户状态",
            "object": "强塞客户状态",
            "verification_status": "已验证",
            "fact_ids": ["F-002"],
            "source_uris": ["https://company.example/report"],
        },
        {
            "relation_id": "R-CONFLICT",
            "subject": "强塞冲突",
            "predicate": "对应工艺",
            "object": "不应正式",
            "verification_status": "已验证",
            "fact_ids": ["F-003"],
            "source_uris": ["https://a.example/report", "https://b.example/report"],
        },
        {
            "relation_id": "R-MISSING-FACT",
            "subject": "强塞缺事实",
            "predicate": "对应工艺",
            "object": "不应正式",
            "verification_status": "已验证",
            "fact_ids": ["F-999"],
            "source_uris": ["https://a.example/report", "https://b.example/report"],
        },
        {
            "relation_id": "R-OUTSIDE",
            "subject": "强塞外部原文",
            "predicate": "对应工艺",
            "object": "不应正式",
            "verification_status": "已验证",
            "fact_ids": ["F-004"],
            "source_uris": ["https://outside.example/report"],
        },
    ]

    生成深度研究报告(
        output,
        行业="半导体膜材",
        资料库=tmp_path,
        事实=facts,
        来源清单=sources,
        映射={"正式关系": relations, "待验证关系": []},
    )

    text = output.read_text(encoding="utf-8")
    assert "|ALD前驱体|对应工艺|ALD|已验证|" in text
    assert "强塞客户状态" not in text
    assert "强塞冲突" not in text
    assert "强塞缺事实" not in text
    assert "强塞外部原文" not in text
    assert "- 待验证关系：4 条；不得进入确定性产业图谱。" in text


def test_report_revalidates_caller_supplied_formal_mapping(tmp_path: Path) -> None:
    content = _load(ANALYSIS)
    facts = _load(FACTS)["facts"]
    relations = _load(MAPPING)["relations"]
    malicious = dict(relations[0])
    malicious["verification_status"] = "单一来源"
    output = tmp_path / "report.md"

    生成深度研究报告(
        output,
        行业="半导体膜材",
        资料库=tmp_path,
        事实=facts,
        来源清单=_sources_for(facts, tmp_path / "原始资料"),
        映射={"正式关系": [malicious], "待验证关系": []},
        研究内容=content,
    )

    text = output.read_text(encoding="utf-8")
    assert "尚无通过证据门控的正式关系" in text
    assert "待验证关系：1 条" in text
