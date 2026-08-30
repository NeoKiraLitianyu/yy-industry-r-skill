from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

import sqlite3

from .索引 import 库索引, 写入运行记录


def 检查来源重复(库路径: Path, 文件路径: Path, file_sha: str) -> bool:
    # 用于快速判断是否重复；内部表层面不做精确语义对比
    with 库索引(库路径).连接 as connection:
        row = connection.execute("SELECT COUNT(1) FROM 文档 WHERE file_sha256 = ?", (file_sha,)).fetchone()
        return int(row[0]) > 0


def 记录验证结果(库路径: Path, fact_key: str, status: str, summary: str, sources: list[dict], details: dict) -> None:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO 验证 (fact_key, status, summary, created_at, sources_json, details_json)
            VALUES (?, ?, ?, datetime('now'), ?, ?)
            """,
            (
                fact_key,
                status,
                summary,
                json.dumps(sources, ensure_ascii=False),
                json.dumps(details, ensure_ascii=False),
            ),
        )


def 交叉验证样例(statements: List[Dict[str, str]]) -> Dict[str, List[str]]:
    缺口 = []
    冲突 = []
    fact_values: dict[str, set[str]] = {}
    fact_sources: dict[str, set[str]] = {}
    for item in statements:
        if not item.get("fact_key") or not item.get("fact_value"):
            缺口.append("缺少 fact_key/fact_value")
            continue
        if not item.get("source"):
            缺口.append(f"{item['fact_key']} 无来源")
        fact = item["fact_key"].strip()
        fact_values.setdefault(fact, set()).add(str(item.get("fact_value", "")))
        fact_sources.setdefault(fact, set()).add(str(item.get("source", "")))

    for fact, values in fact_values.items():
        if len(values) == 1:
            continue
        conflict_sources = sorted(fact_sources.get(fact, []))
        conflicts = "；".join(sorted(values))
        冲突.append(f"{fact} 不一致（{conflicts}，来源：{', '.join(conflict_sources)}）")

    return {"缺口": 缺口, "冲突": 冲突}


def 统计验证结果(库路径: Path) -> dict[str, int]:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        total = cursor.execute("SELECT COUNT(1) FROM 验证").fetchone()[0]
        passed = cursor.execute("SELECT COUNT(1) FROM 验证 WHERE status='通过'").fetchone()[0]
        pending = cursor.execute("SELECT COUNT(1) FROM 验证 WHERE status='待补充'").fetchone()[0]
        conflicted = cursor.execute("SELECT COUNT(1) FROM 验证 WHERE status='冲突'").fetchone()[0]
    return {"total": int(total), "passed": int(passed), "pending": int(pending), "conflicted": int(conflicted)}


def 执行全量交叉验证(库路径: Path) -> dict[str, int]:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            SELECT f.fact_key, f.id, f.fact_value, f.fact_type, s.credibility, s.id, s.source_uri, s.source_name
            FROM 事实 f
            JOIN 来源 s ON s.id = f.source_id
            WHERE f.fact_type <> 'keyword_match'
            ORDER BY f.fact_key, f.created_at DESC
            """
        ).fetchall()

    buckets: dict[str, list[tuple[str, int, str, str]]] = defaultdict(list)
    for fact_key, _fact_id, fact_value, _fact_type, credibility, source_id, source_uri, source_name in rows:
        buckets[str(fact_key)].append(
            (
                str(fact_value),
                int(credibility or 5),
                str(source_uri or ""),
                str(source_name or ""),
            )
        )

    passed = 0
    pending = 0
    conflicted = 0
    for fact_key, values in buckets.items():
        # 至少两个独立来源才判定为可交叉验证通过
        source_values: dict[str, set[str]] = defaultdict(set)
        family_uris: dict[str, set[str]] = defaultdict(set)
        counts: dict[str, int] = Counter()
        for v, _, uri, name in values:
            key = f"{uri}::{v}"
            source_values[uri].add(key)
            family = str(name or "").strip().casefold() or str(uri).split("/", 3)[2].casefold()
            family_uris[family].add(uri)
            counts[v] += 1
        unique = list(counts.keys())
        details = {
            "values": counts,
            "evidence_count": len(values),
            "source_count": len(source_values),
            "independent_source_families": len(family_uris),
            "source_families": {family: sorted(uris) for family, uris in family_uris.items()},
        }
        independent_sources = len([s for s in family_uris if s])

        if len(unique) == 1 and independent_sources >= 2:
            status = "通过"
            summary = f"{fact_key} 在 {len(values)} 个来源中一致"
            sources = [{"fact_value": unique[0], "source_count": independent_sources, "uris": list(source_values.keys())}]
            passed += 1
        elif len(unique) == 0:
            status = "待补充"
            summary = f"{fact_key} 未检测到可比对数值"
            sources = []
            pending += 1
        elif len(unique) == 1 and independent_sources < 2:
            status = "待补充"
            summary = f"{fact_key} 目前仅 {independent_sources} 个来源，无法形成交叉验证"
            sources = [{"fact_value": unique[0], "source_count": independent_sources, "uris": list(source_values.keys())}]
            pending += 1
        else:
            status = "冲突"
            summary = f"{fact_key} 出现 {len(unique)} 种取值，需保留冲突路径"
            top = sorted(counts.items(), key=lambda i: i[1], reverse=True)
            sources = [{"fact_value": v, "evidence_count": c} for v, c in top]
            conflicted += 1
        记录验证结果(库路径, fact_key, status, summary, sources, details)

    写入运行记录(
        库路径,
        "verification",
        "cross-validation",
        "completed",
        f"facts={len(buckets)}|passed={passed}|pending={pending}|conflict={conflicted}",
    )
    return {"total": len(buckets), "passed": passed, "pending": pending, "conflicted": conflicted}
