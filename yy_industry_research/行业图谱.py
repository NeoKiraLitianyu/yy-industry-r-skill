from __future__ import annotations

from typing import Any, Iterable


def 建立证据Mapping(行业包: dict[str, Any], 事实: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    nodes = {str(item) for values in 行业包.get("nodes", {}).values() for item in values}
    relations = {str(item) for item in 行业包.get("relations", [])}
    正式: list[dict[str, Any]] = []
    待验证: list[dict[str, Any]] = []

    for fact in 事实:
        subject = str(fact.get("subject", "")).strip()
        predicate = str(fact.get("predicate", "")).strip()
        obj = str(fact.get("object", "")).strip()
        record = dict(fact)
        record["taxonomy_subject_match"] = subject in nodes
        record["taxonomy_object_match"] = obj in nodes
        record["relation_allowed"] = not relations or predicate in relations
        verified = fact.get("verification_status") == "已验证"
        traceable = bool(fact.get("evidence_id") and fact.get("source_id"))
        if subject and predicate and obj and verified and traceable and record["relation_allowed"]:
            正式.append(record)
        else:
            待验证.append(record)
    return {"正式关系": 正式, "待验证关系": 待验证}
