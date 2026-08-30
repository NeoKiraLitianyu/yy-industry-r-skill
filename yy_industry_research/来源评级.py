from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class 来源评级:
    层级: str
    权威性: str
    直接性: str
    时效性: str
    独立性: str
    分数: int
    理由: tuple[str, ...]


def _日期(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def 评级来源(source: dict, 基准日期: str | None = None) -> 来源评级:
    source_type = str(source.get("source_type") or source.get("来源类型") or "未知")
    uri = str(source.get("source_uri") or source.get("原始链接") or "")
    primary = bool(source.get("is_primary") or source.get("是否一手来源"))
    domain = urlsplit(uri).netloc.lower()
    理由: list[str] = []

    if source_type in {"政府协会", "政府", "监管", "标准"} or domain.endswith(".gov.cn"):
        authority, score = "高", 92
        理由.append("政府、监管、标准或权威协会来源")
    elif source_type in {"公司一手", "公司财报", "公司公告", "学术标准"}:
        authority, score = "高", 88
        理由.append("公司披露、学术论文或标准原文")
    elif source_type in {"券商咨询", "券商研报", "咨询机构", "行业媒体"}:
        authority, score = "中", 74
        理由.append("专业机构二手研究")
    else:
        authority, score = "低", 52
        理由.append("来源类型尚未进入权威白名单")

    directness = "一手" if primary or source_type in {"政府协会", "公司一手", "公司财报", "公司公告", "学术标准"} else "二手"
    if directness == "一手":
        score += 4
        理由.append("可直接定位到原始发布主体")

    base = _日期(基准日期) or date.today()
    published = _日期(str(source.get("published_at") or source.get("发布日期") or ""))
    if published is None:
        freshness = "未知"
        score -= 6
        理由.append("发布日期缺失")
    else:
        age = max(0, (base - published).days)
        if age <= 365:
            freshness = "新近"
            理由.append("一年内发布")
        elif age <= 730:
            freshness = "可用"
            score -= 4
            理由.append("一至两年内发布")
        else:
            freshness = "基础资料"
            score -= 10
            理由.append("超过两年，仅作基础资料")

    independence = "独立" if not source.get("original_source_family") else "同源族"
    if independence == "同源族":
        score -= 8
        理由.append("转载、镜像或同一原稿不计独立来源")

    score = max(0, min(100, score))
    level = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    return 来源评级(level, authority, directness, freshness, independence, score, tuple(理由))
