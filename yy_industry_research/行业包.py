from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List


def 读取行业包(技能根: Path, 行业: str) -> dict:
    pack_dir = 技能根 / "industry-packs" / 行业
    config_path = pack_dir / "配置.json"
    taxonomy_path = pack_dir / "taxonomy.json"
    problem_path = pack_dir / "研究问题.md"
    mapping = {}
    if config_path.exists():
        mapping["config"] = json.loads(config_path.read_text(encoding="utf-8"))
    if taxonomy_path.exists():
        mapping["taxonomy"] = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    if problem_path.exists():
        mapping["research_questions"] = problem_path.read_text(encoding="utf-8")
    optional_json = {
        "source_matrix": "来源矩阵.json",
        "relations": "关系词表.json",
        "search_terms": "检索词.json",
        "pack": "行业包.json",
    }
    for key, filename in optional_json.items():
        path = pack_dir / filename
        if path.exists():
            mapping[key] = json.loads(path.read_text(encoding="utf-8"))
    return mapping


def 构建查询矩阵(行业: str, include_global: bool = True, 行业包: dict | None = None) -> Dict[str, List[str]]:
    base = [行业, f"{行业} 产业链", f"{行业} 市场规模", f"{行业} 需求 24 个月"]
    china = [f"{行业} 中国 报告", f"{行业} 中国 政策", f"{行业} 中国 龙头企业"]
    global_terms = [f"{行业} global report", f"{行业} world market", f"{行业} forecast"]

    if 行业包:
        taxonomy = 行业包.get("taxonomy", {})
        terms = taxonomy.get("query_terms", {})
        if isinstance(terms, dict):
            china.extend([str(x) for x in terms.get("china", []) if str(x).strip()])
            if include_global:
                global_terms.extend([str(x) for x in terms.get("global", []) if str(x).strip()])
        base.extend([str(x) for x in taxonomy.get("core_terms", []) if str(x).strip()])

    matrix = {"中国": base + china}
    if include_global:
        matrix["全球"] = base + global_terms
    return matrix


def 提取行业命中节点(文本: str, 行业包: dict) -> List[str]:
    taxonomy = 行业包.get("taxonomy", {})
    术语 = taxonomy.get("nodes", {})
    命中节点: List[str] = []
    if not isinstance(术语, dict):
        return 命中节点

    标准文本 = re.sub(r"\s+", "", 文本.lower())
    for 节点, 关键词 in 术语.items():
        if not isinstance(关键词, list):
            continue
        for 关键 in 关键词:
            词 = re.sub(r"\s+", "", str(关键).strip().lower())
            if not 词:
                continue
            if 词 in 标准文本:
                命中节点.append(str(节点))
                break
    return 命中节点
