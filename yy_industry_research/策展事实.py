from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


_来源族别名 = {
    "semi china": "semi",
    "semi 中国": "semi",
    "linx consulting / semi": "semi-linx",
    "台积电": "tsmc",
    "工业和信息化部": "miit",
}
_默认Mapping关系 = {
    "材料用于工艺", "工艺形成薄膜", "薄膜构成器件结构", "器件结构驱动需求",
    "公司供应材料", "公司服务客户", "原料约束材料", "设备兼容材料",
    "制程节点提升用量", "认证壁垒影响替代", "国产化创造投资机会", "风险反证结论",
    "对应工艺", "形成薄膜", "用于器件", "面向节点", "节点关联公司",
    "公司布局材料", "供应产品", "客户状态",
}


def _来源族(name: str) -> str:
    text = re.sub(r"\s+", " ", str(name or "").strip().lower())
    if text in _来源族别名:
        return _来源族别名[text]
    text = re.sub(r"\b(china|中国区|中国)\b", "", text).strip(" -/()")
    return text or "未知来源"


def _来源记录族(source: dict[str, Any], uri: str) -> str:
    host = (urlparse(uri).hostname or "").lower().removeprefix("www.")
    if host:
        return host
    return _来源族(str(source.get("source_name") or ""))


def _关系三元组(value: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(str(value.get(field) or "").strip() for field in ("subject", "predicate", "object"))


def _事实支持关系(fact: dict[str, Any], relation: dict[str, Any]) -> bool:
    expected = _关系三元组(relation)
    candidates: list[dict[str, Any]] = []
    direct = {field: fact.get(field) for field in ("subject", "predicate", "object")}
    if all(str(value or "").strip() for value in direct.values()):
        candidates.append(direct)
    for item in fact.get("mapping_relations", []) or []:
        if isinstance(item, dict):
            candidates.append(item)
        elif isinstance(item, (list, tuple)) and len(item) == 3:
            candidates.append(dict(zip(("subject", "predicate", "object"), item)))
    return bool(expected[0] and expected[1] and expected[2]) and any(
        _关系三元组(candidate) == expected for candidate in candidates
    )


def _扩展来源记录(source: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield dict(source)
    for document in source.get("documents", []) or []:
        if isinstance(document, dict):
            expanded = dict(source)
            expanded.update(document)
            yield expanded


def _来源记录已归档(source: dict[str, Any], library_root: Path | None) -> bool:
    raw_path = str(source.get("raw_path") or "").strip()
    if not raw_path or not Path(raw_path).is_file():
        return False
    resolved = Path(raw_path).resolve()
    return library_root is None or resolved.is_relative_to(library_root)


def 门控Mapping(
    mapping: dict[str, Any] | Iterable[dict[str, Any]],
    来源目录: Iterable[dict[str, Any]],
    *,
    资料库: str | Path | None = None,
    允许事实编号: set[str] | None = None,
    事实目录: Iterable[dict[str, Any]] | None = None,
    允许关系: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """重新门控外部传入的 Mapping，不信任调用方标注的“正式关系”。"""

    if isinstance(mapping, dict):
        candidates = list(mapping.get("正式关系", [])) + list(mapping.get("待验证关系", []))
    else:
        candidates = list(mapping)
    source_index: dict[str, list[dict[str, Any]]] = {}
    for source in 来源目录:
        uri = str(source.get("source_uri") or "").strip()
        if uri:
            source_index.setdefault(uri, []).extend(_扩展来源记录(source))

    library_root = Path(资料库).resolve() if 资料库 is not None else None
    fact_index = {
        str(fact.get("fact_id") or "").strip(): dict(fact)
        for fact in (事实目录 or [])
        if str(fact.get("fact_id") or "").strip()
    }
    formal: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        key = (
            str(record.get("relation_id") or record.get("evidence_id") or ""),
            str(record.get("subject") or ""),
            str(record.get("predicate") or ""),
            str(record.get("object") or ""),
        )
        if key in seen:
            continue
        seen.add(key)

        uris = [str(uri).strip() for uri in record.get("source_uris", []) if str(uri).strip()]
        archived_uris: list[str] = []
        families: set[str] = set()
        for uri in uris:
            for source in source_index.get(uri, []):
                raw_path = str(source.get("raw_path") or "").strip()
                if not raw_path or not Path(raw_path).is_file():
                    continue
                resolved = Path(raw_path).resolve()
                if library_root is not None and not resolved.is_relative_to(library_root):
                    continue
                archived_uris.append(uri)
                families.add(_来源记录族(source, uri))
                break

        fact_ids = [str(item).strip() for item in record.get("fact_ids", []) if str(item).strip()]
        complete = all(str(record.get(field) or "").strip() for field in ("subject", "predicate", "object"))
        facts_valid = bool(fact_ids) and (允许事实编号 is None or set(fact_ids) <= 允许事实编号)
        fact_statuses = [
            str(fact_index.get(fact_id, {}).get("verification_status") or "").strip()
            for fact_id in fact_ids
            if fact_index
        ]
        fact_statuses_valid = not fact_index or all(status == "已验证" for status in fact_statuses)
        fact_source_uris = {
            str(uri).strip()
            for fact_id in fact_ids
            for uri in fact_index.get(fact_id, {}).get("source_uris", [])
            if str(uri).strip()
        }
        source_uris_match_facts = not fact_index or not uris or set(uris) <= fact_source_uris
        semantic_binding_valid = bool(fact_ids) and bool(fact_index) and all(
            _事实支持关系(fact_index.get(fact_id, {}), record) for fact_id in fact_ids
        )
        allowed_relations = 允许关系 if 允许关系 is not None else _默认Mapping关系
        relation_allowed = str(record.get("predicate") or "") in allowed_relations and record.get("relation_allowed") is not False
        all_sources_archived = bool(uris) and set(uris) == set(archived_uris)
        input_status = str(record.get("verification_status") or record.get("status") or "").strip()
        verified = (
            input_status == "已验证"
            and len(families) >= 2
            and fact_statuses_valid
            and source_uris_match_facts
            and semantic_binding_valid
            and all_sources_archived
        )

        record["source_uris"] = list(dict.fromkeys(archived_uris))
        record["source_id"] = "；".join(sorted(families))
        record["evidence_id"] = str(record.get("evidence_id") or record.get("relation_id") or "")
        if verified:
            record["verification_status"] = "已验证"
            record["status"] = "已验证"
        elif any(status in {"存在冲突", "冲突"} for status in fact_statuses) or input_status in {"存在冲突", "冲突"}:
            record["verification_status"] = "存在冲突"
            record["status"] = "待验证"
        elif any(status in {"证据不足", "证据缺失"} for status in fact_statuses) or input_status in {"证据不足", "证据缺失"}:
            record["verification_status"] = "证据不足"
            record["status"] = "待验证"
        elif input_status == "单一来源" or len(families) < 2:
            record["verification_status"] = "单一来源"
            record["status"] = "待验证"
        else:
            record["verification_status"] = "待验证"
            record["status"] = "待验证"
        reasons: list[str] = []
        if not complete:
            reasons.append("关系字段不完整")
        if not relation_allowed:
            reasons.append("关系谓词未获准")
        if not facts_valid:
            reasons.append("事实编号缺失或无效")
        if not fact_statuses_valid:
            reasons.append("引用事实未全部已验证")
        if not source_uris_match_facts:
            reasons.append("关系来源未对应引用事实来源")
        if not semantic_binding_valid:
            reasons.append("引用事实未结构化支持该关系")
        if not archived_uris:
            reasons.append("原始素材未归档")
        elif not all_sources_archived:
            reasons.append("关系存在未归档来源")
        if len(families) < 2:
            reasons.append("独立来源族不足2个")
        if input_status != "已验证":
            reasons.append("原关系未达到已验证状态")
        record["mapping_gate_note"] = "；".join(reasons)

        if complete and relation_allowed and facts_valid and all_sources_archived and verified:
            formal.append(record)
        else:
            pending.append(record)
    return {"正式关系": formal, "待验证关系": pending}


def 装载策展事实(
    path: str | Path,
    来源目录: Iterable[dict[str, Any]],
    *,
    资料库: str | Path | None = None,
) -> list[dict[str, Any]]:
    """装载分析师策展事实，并以实际归档来源和独立机构数重新门控状态。"""

    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_facts = obj.get("facts", []) if isinstance(obj, dict) else []
    catalog: dict[str, list[dict[str, Any]]] = {}
    for item in 来源目录:
        uri = str(item.get("source_uri", "")).strip()
        if uri:
            catalog.setdefault(uri, []).extend(_扩展来源记录(item))
    library_root = Path(资料库).resolve() if 资料库 is not None else None
    result: list[dict[str, Any]] = []

    for raw in raw_facts:
        if not isinstance(raw, dict) or not raw.get("claim") or not raw.get("module"):
            continue
        fact = dict(raw)
        uris = [str(uri) for uri in fact.get("source_uris", []) if str(uri).strip()]
        if not uris and fact.get("source_uri"):
            uris = [str(fact["source_uri"])]
        archived_records = {
            uri: next(
                (record for record in catalog.get(uri, []) if _来源记录已归档(record, library_root)),
                None,
            )
            for uri in uris
        }
        available = [uri for uri in uris if archived_records.get(uri) is not None]
        missing = [uri for uri in uris if archived_records.get(uri) is None]
        families = {
            _来源记录族(archived_records[uri] or {}, uri)
            for uri in available
        }

        status = str(fact.get("verification_status") or "单一来源")
        notes: list[str] = []
        if not available:
            status = "证据缺失"
            notes.append("引用来源尚未归档")
        elif status == "已验证" and missing:
            status = "单一来源"
        elif status == "已验证" and len(families) < 2:
            status = "单一来源"
            notes.append("引用虽有多条，但属于同一来源族")
        if missing:
            notes.append(f"{len(missing)}条引用未归档")

        fact["source_uris"] = available
        fact["source_uri"] = available[0] if available else ""
        fact["source_families"] = sorted(families)
        fact["verification_status"] = status
        fact["verification_note"] = "；".join(notes) or str(fact.get("verification_note") or "")
        result.append(fact)
    return result


def 装载策展Mapping(
    path: str | Path,
    来源目录: Iterable[dict[str, Any]],
    允许关系: set[str],
) -> dict[str, list[dict[str, Any]]]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_relations = obj.get("relations", []) if isinstance(obj, dict) else []
    catalog = {str(item.get("source_uri", "")): item for item in 来源目录}
    formal: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for raw in raw_relations:
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        uris = [str(uri) for uri in record.get("source_uris", []) if str(uri).strip()]
        available = [uri for uri in uris if uri in catalog]
        families = {_来源族(str(catalog[uri].get("source_name", ""))) for uri in available}
        relation_id = str(record.get("relation_id") or "")
        record["evidence_id"] = relation_id
        record["source_id"] = "；".join(sorted(families))
        record["source_uris"] = available
        record["relation_allowed"] = str(record.get("predicate")) in 允许关系
        record["verification_status"] = (
            "已验证"
            if record.get("verification_status") == "已验证" and len(families) >= 2
            else "待验证"
        )
        complete = all(str(record.get(key, "")).strip() for key in ("subject", "predicate", "object", "evidence_id"))
        if complete and record["relation_allowed"] and record["verification_status"] == "已验证":
            formal.append(record)
        else:
            pending.append(record)
    return {"正式关系": formal, "待验证关系": pending}
