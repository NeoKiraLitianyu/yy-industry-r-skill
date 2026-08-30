from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .策展事实 import 门控Mapping


_事实引用模式 = re.compile(r"\[(F-\d+)\]")
_图表类型 = {"bar", "heatmap", "flow", "matrix", "ladder", "radar", "evidence"}
_允许事实状态 = {"已验证", "单一来源"}
_固定紫色令牌 = {
    "primary_purple": "#4B2E83",
    "violet": "#7456A8",
    "surface_soft": "#F4F0FA",
    "paper": "#FAF9F7",
    "ink": "#211B2B",
    "muted_text": "#706779",
    "rule": "#DED6E8",
}


def 视觉令牌() -> dict[str, str]:
    return dict(_固定紫色令牌)


def 支持图表类型() -> set[str]:
    return set(_图表类型)


def _提取事实编号(value: Any) -> list[str]:
    if isinstance(value, str):
        return _事实引用模式.findall(value)
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_提取事实编号(item))
        return result
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            result.extend(_提取事实编号(item))
        return result
    return []


def _去重事实编号(fact_ids: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in fact_ids:
        fact_id = str(item).strip()
        if fact_id and fact_id not in seen:
            seen.add(fact_id)
            result.append(fact_id)
    return result


def _声明事实编号(value: Any) -> list[str]:
    fact_ids = _提取事实编号(value)
    if isinstance(value, dict):
        explicit = value.get("fact_ids") or value.get("事实编号") or []
        if isinstance(explicit, list):
            fact_ids.extend(str(item) for item in explicit if str(item).strip())
    return _去重事实编号(fact_ids)


def _建立来源索引(sources: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        uri = str(source.get("source_uri") or "").strip()
        if not uri:
            continue
        index.setdefault(uri, []).append(dict(source))
    return index


def _来源可访问(source: Mapping[str, Any]) -> bool:
    raw_path = str(source.get("raw_path") or "").strip()
    return bool(raw_path) and Path(raw_path).is_file()


def _校验事实引用(
    scope: str,
    fact_ids: Iterable[str],
    fact_index: Mapping[str, dict[str, Any]],
    source_index: Mapping[str, list[dict[str, Any]]],
) -> list[str]:
    normalized = _去重事实编号(fact_ids)
    if not normalized:
        raise ValueError(f"{scope} 必须引用至少一条事实锚点")

    for fact_id in normalized:
        fact = fact_index.get(fact_id)
        if fact is None:
            raise ValueError(f"{scope} 引用了不存在的事实：{fact_id}")
        status = str(fact.get("verification_status") or "").strip()
        if status not in _允许事实状态:
            raise ValueError(f"{scope} 引用了不允许的事实状态：{fact_id} -> {status or '空'}")
        uris = [str(item).strip() for item in fact.get("source_uris", []) if str(item).strip()]
        if not uris and str(fact.get("source_uri") or "").strip():
            uris = [str(fact["source_uri"]).strip()]
        if not uris:
            raise ValueError(f"{scope} 引用事实缺少 source_uri：{fact_id}")
        if not any(_来源可访问(source) for uri in uris for source in source_index.get(uri, [])):
            raise ValueError(f"{scope} 引用事实没有可访问的归档原文：{fact_id}")
    return normalized


def _追踪文本(fact_ids: Iterable[str], *, model_label: str = "") -> str:
    normalized = _去重事实编号(fact_ids)
    anchors = f"事实锚点：{'、'.join(normalized)}" if normalized else ""
    label = str(model_label or "").strip()
    if label and anchors:
        return f"{label}；{anchors}"
    return anchors or label


def _校验图表声明(
    spec: dict[str, Any],
    fact_index: Mapping[str, dict[str, Any]],
    source_index: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    chart_id = str(spec.get("id") or "").strip()
    chart_type = str(spec.get("type") or "").strip()
    title = str(spec.get("title") or "").strip()
    as_of = str(spec.get("as_of") or "").strip()
    basis = str(spec.get("basis") or "").strip()
    model_label = str(spec.get("model_label") or "").strip()
    if not chart_id:
        raise ValueError("图表声明缺少id")
    if chart_type not in _图表类型:
        raise ValueError(f"图表类型不支持：{chart_type or '空'}")
    if not title or not as_of or not basis:
        raise ValueError(f"图表声明缺少标题/时点/依据：{chart_id}")
    if model_label and model_label != "内部模型假设":
        raise ValueError(f"图表声明只允许 model_label=内部模型假设：{chart_id}")

    fact_scope = str(spec.get("fact_scope") or "").strip()
    if fact_scope and fact_scope != "all":
        raise ValueError(f"图表声明 fact_scope 只允许 all：{chart_id}")
    if fact_scope == "all" and chart_type != "evidence":
        raise ValueError(f"只有 evidence 图表允许 fact_scope=all：{chart_id}")
    fact_ids = _去重事实编号(fact_index if fact_scope == "all" else spec.get("fact_ids", []))
    if fact_scope == "all":
        if not fact_ids:
            raise ValueError(f"图表 {chart_id} 的全事实范围为空")
    elif fact_ids:
        _校验事实引用(f"图表 {chart_id}", fact_ids, fact_index, source_index)
    elif model_label != "内部模型假设":
        raise ValueError(f"图表声明缺少事实引用或内部模型标签：{chart_id}")
    validated = dict(spec)
    if fact_ids:
        validated["fact_ids"] = fact_ids
    validated["trace"] = _追踪文本(fact_ids, model_label=model_label)
    return validated


def _校验出版章节形状(content: dict[str, Any]) -> None:
    sections = content.get("出版章节")
    if sections is None:
        return
    if not isinstance(sections, list) or len(sections) != 22:
        raise ValueError("出版模型要求出版章节恰好为22章")
    expected = [f"P-{index:02d}" for index in range(1, 23)]
    actual = [str(item.get("id") or "") if isinstance(item, dict) else "" for item in sections]
    if actual != expected:
        raise ValueError("出版章节ID必须从P-01连续到P-22")


def _章节声明(
    content: dict[str, Any],
    fact_index: Mapping[str, dict[str, Any]],
    source_index: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    executive = content.get("执行摘要") or content.get("executive_summary") or {}
    if isinstance(executive, dict):
        label = str(executive.get("核心结论") or executive.get("conclusion") or "").strip()
        basis = str(executive.get("依据") or executive.get("evidence") or "").strip()
        if label:
            fact_ids = _校验事实引用("执行摘要", _提取事实编号(executive), fact_index, source_index)
            declarations.append(
                {
                    "id": "executive-summary",
                    "kind": "executive_summary",
                    "label": label,
                    "basis": basis,
                    "fact_ids": fact_ids,
                    "trace": _追踪文本(fact_ids),
                }
            )

    section_groups = [
        ("section", content.get("章节") or content.get("sections") or []),
        ("publication_section", content.get("出版章节") or []),
    ]
    for kind, sections in section_groups:
        if not isinstance(sections, list):
            continue
        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            label = str(section.get("title") or section.get("标题") or section.get("module") or "").strip()
            basis = str(section.get("依据") or section.get("evidence") or "").strip()
            if label:
                fact_ids = _校验事实引用(
                    f"章节 {label or index}",
                    _声明事实编号(section),
                    fact_index,
                    source_index,
                )
                declarations.append(
                    {
                        "id": str(section.get("id") or f"{kind}-{index:02d}"),
                        "kind": kind,
                        "label": label,
                        "basis": basis,
                        "fact_ids": fact_ids,
                        "trace": _追踪文本(fact_ids),
                    }
                )
    return declarations


def 构建出版模型(
    markdown: str,
    content: dict[str, Any],
    facts: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    mappings: list[dict[str, Any]] | dict[str, Any],
    chart_specs: list[dict[str, Any]],
    资料库: str | Path | None = None,
) -> dict[str, Any]:
    _校验出版章节形状(content)
    fact_index = {
        str(item.get("fact_id")): dict(item)
        for item in facts
        if str(item.get("fact_id") or "").strip()
    }
    source_index = _建立来源索引(sources)
    section_declarations = _章节声明(content, fact_index, source_index)
    validated_specs = [_校验图表声明(spec, fact_index, source_index) for spec in chart_specs]
    if len(validated_specs) < 12:
        raise ValueError("出版模型至少需要12个图表声明")

    chart_declarations = [
        {
            "id": str(spec["id"]),
            "kind": "chart",
            "label": str(spec["title"]),
            "basis": str(spec["basis"]),
            "fact_ids": [str(item) for item in spec.get("fact_ids", []) if str(item).strip()],
            "model_label": str(spec.get("model_label") or ""),
            "chart_type": str(spec["type"]),
            "trace": str(spec.get("trace") or _追踪文本(spec.get("fact_ids", []), model_label=str(spec.get("model_label") or ""))),
        }
        for spec in validated_specs
    ]
    declarations = chart_declarations + section_declarations
    if len(declarations) < 14:
        raise ValueError("出版模型至少需要14个声明")

    mapping_candidates = (
        list(mappings.get("正式关系", [])) + list(mappings.get("待验证关系", []))
        if isinstance(mappings, dict)
        else list(mappings)
    )
    if mapping_candidates and 资料库 is None:
        raise ValueError("出版模型包含 Mapping 时必须提供资料库边界")
    gated_mappings = 门控Mapping(
        mappings,
        sources,
        资料库=资料库,
        允许事实编号={
            fact_id
            for fact_id, fact in fact_index.items()
            if fact.get("verification_status") == "已验证"
        },
        事实目录=facts,
    )
    return {
        "markdown": str(markdown),
        "as_of": str(content.get("as_of") or ""),
        "tokens": 视觉令牌(),
        "content": dict(content),
        "facts": [dict(item) for item in facts],
        "fact_index": fact_index,
        "sources": [dict(item) for item in sources],
        "mappings": gated_mappings,
        "charts": validated_specs,
        "claim_declarations": declarations,
    }
