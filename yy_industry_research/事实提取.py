from __future__ import annotations

import re
from typing import Any


_NUM_RE = re.compile(
    r"(?<![A-Za-z])"
    r"(?P<value>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:(?P<value_unit>\s*(?:亿元|美元|万元|亿|百亿元|百亿|千亿|万亿|万|千|百|十|%|个百分点|t|kg|吨|万吨|亿元|美元/年|美元/每吨|台|片|块|元|元/亩|元/平方米|台次|个)?))",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"[。！？!;；,\n]")
_WINDOW_WORDS = [
    "市场规模",
    "规模",
    "市场需求",
    "需求",
    "产能",
    "出货",
    "出货量",
    "产量",
    "营收",
    "收入",
    "采购",
    "增长",
    "同比",
    "环比",
    "价格",
    "供应",
    "投资",
    "产值",
    "占比",
    "份额",
    "导入",
    "毛利",
    "市占率",
    "成本",
    "订单",
    "库存",
    "产线",
    "装机",
]

_ANCHOR_TO_KEY = {
    "规模": "市场规模",
    "市场规模": "市场规模",
    "市场需求": "需求",
    "需求": "需求",
    "采购": "采购",
    "增长": "增长率",
    "同比": "增长率",
    "环比": "增长率",
    "价格": "价格",
    "供应": "供应",
    "产量": "产量",
    "出货": "出货量",
    "出货量": "出货量",
    "产值": "产值",
    "营收": "营收",
    "收入": "营收",
    "投资": "投资",
    "占比": "市场份额",
    "份额": "市场份额",
    "市占率": "市场份额",
    "毛利": "盈利能力",
    "成本": "成本",
    "订单": "订单",
    "库存": "库存",
    "产能": "产能",
    "装机": "装机量",
}


def _clean_number(value: str) -> str:
    return value.replace(",", "").strip()


def _normalize_value_unit(value_unit: str | None) -> str:
    if not value_unit:
        return ""
    return value_unit.strip().replace(" ", "")


def _is_year_token(token: str) -> bool:
    if re.fullmatch(r"(19|20)\d{2}", token):
        return True
    return False


def _iter_keywords(行业包: dict[str, Any] | None) -> list[str]:
    keys: list[str] = []
    if not 行业包:
        return _WINDOW_WORDS
    taxonomy = 行业包.get("taxonomy", {})
    core = taxonomy.get("core_terms", [])
    if isinstance(core, list):
        keys.extend([str(item).lower() for item in core if str(item).strip()])
    if not keys:
        return _WINDOW_WORDS
    return list(dict.fromkeys([k for k in keys if k]))


def _find_anchor(sentence: str, match_start: int, match_end: int, keywords: list[str]) -> str | None:
    lower = sentence.lower()
    best_anchor: str | None = None
    best_score: int | None = None
    best_len = 0
    best_priority = 99

    def _priority(anchor: str) -> int:
        if anchor in {"增长", "同比", "环比", "增速", "增长率"}:
            return 0
        if anchor in {"需求", "市场需求"}:
            return 1
        return 2

    before: list[tuple[int, int, int, str]] = []
    after: list[tuple[int, int, int, str]] = []
    for anchor in keywords + _WINDOW_WORDS:
        for m in re.finditer(re.escape(anchor), lower):
            dist = min(abs(m.start() - match_end), abs(m.end() - match_start))
            if m.end() <= match_start:
                before.append((dist, _priority(anchor), len(anchor), anchor))
            elif m.start() >= match_end:
                after.append((dist, _priority(anchor), len(anchor), anchor))
            else:
                continue

    for bucket in (before, after):
        if not bucket:
            continue
        bucket.sort(key=lambda item: (item[0], item[1], -item[2]))
        return bucket[0][3]

    for anchor in keywords + _WINDOW_WORDS:
        for m in re.finditer(re.escape(anchor), lower):
            dist = min(abs(m.start() - match_end), abs(m.end() - match_start))
            priority = _priority(anchor)
            score = dist
            if (
                best_score is None
                or score < best_score
                or (score == best_score and priority < best_priority)
                or (score == best_score and priority == best_priority and len(anchor) > best_len)
            ):
                best_score = score
                best_anchor = anchor
                best_len = len(anchor)
                best_priority = priority
    if best_anchor is None:
        return None
    if best_score is not None and best_score > 28:
        return None
    return best_anchor


def _anchor_to_key(anchor: str) -> str:
    return _ANCHOR_TO_KEY.get(anchor, anchor)


def _extract_year_in_sentence(sentence: str) -> str | None:
    year = re.search(r"(19|20)\d{2}", sentence)
    if year:
        return year.group(0)
    return None


def 提取事实候选(文本: str, 行业: str, 行业包: dict[str, Any] | None = None) -> list[dict[str, str]]:
    if not 文本:
        return []

    facts: list[dict[str, str]] = []
    keywords = _iter_keywords(行业包)
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(文本) if s.strip()]
    for sentence in sentences:
        for num_match in _NUM_RE.finditer(sentence):
            value_raw = _clean_number(num_match.group("value"))
            if not value_raw or _is_year_token(value_raw):
                continue
            if len(value_raw) > 20:
                continue
            unit = _normalize_value_unit(num_match.group("value_unit"))
            anchor = _find_anchor(sentence.lower(), num_match.start(), num_match.end(), keywords)
            if not anchor:
                continue
            value_key = f"{value_raw}{unit}" if unit else value_raw
            if len(value_key) > 80:
                continue

            fact_key = _anchor_to_key(anchor.strip())
            year = _extract_year_in_sentence(sentence)
            line_snip = sentence[max(0, num_match.start() - 28): min(len(sentence), num_match.end() + 28)]
            facts.append(
                {
                    "fact_key": f"行业.{行业}.{fact_key}",
                    "fact_type": "extracted_numeric",
                    "fact_value": value_key,
                    "unit": unit or "未知",
                    "time_range": year or "未知",
                    "evidence": line_snip,
                    "quote": line_snip,
                    "source_credibility": "6",
                }
            )

    # 去重：同一 fact_key + fact_value 保留单一证据，最多保留 300 条
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in facts:
        marker = (item["fact_key"], item["fact_value"])
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
        if len(out) >= 300:
            break
    return out
