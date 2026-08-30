from __future__ import annotations

from typing import Any

from .数据路由 import 标准候选


_膜材高信号词 = (
    "ALD",
    "原子层沉积",
    "CVD",
    "化学气相沉积",
    "PVD",
    "物理气相沉积",
    "前驱体",
    "precursor",
    "薄膜",
    "thin film",
    "成膜",
    "沉积材料",
    "溅射靶材",
    "sputtering target",
    "High-k",
    "high k",
    "Low-k",
    "low k",
    "金属栅",
    "metal gate",
    "阻挡层",
    "barrier layer",
    "衬垫层",
    "liner",
)

_膜材需求关联词 = (
    "GAA",
    "gate-all-around",
    "DRAM电容",
    "3D NAND",
    "高深宽比",
    "HAR",
    "背面供电",
    "backside power",
    "互连材料",
)


def 评估膜材相关性(候选: 标准候选) -> dict[str, Any]:
    """只根据候选自身标题与摘要评分，绝不把检索词当成命中证据。"""

    title = str(候选.标题 or "")
    summary = str(候选.摘要 or "")
    title_lower = title.lower()
    summary_lower = summary.lower()
    hits: list[str] = []
    score = 0.0

    for term in _膜材高信号词:
        normalized = term.lower()
        if normalized in title_lower:
            score += 3.0
            hits.append(term)
        elif normalized in summary_lower:
            score += 1.5
            hits.append(term)

    for term in _膜材需求关联词:
        normalized = term.lower()
        if normalized in title_lower:
            score += 1.5
            hits.append(term)
        elif normalized in summary_lower:
            score += 0.75
            hits.append(term)

    unique_hits = list(dict.fromkeys(hits))
    return {
        "是否相关": score >= 2.0,
        "得分": round(score, 2),
        "命中词": unique_hits,
        "证据范围": "标题与摘要",
    }
