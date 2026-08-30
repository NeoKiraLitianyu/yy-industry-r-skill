from __future__ import annotations

import re
import urllib.parse as _urlparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup  # type: ignore

from .行业包 import 读取行业包


HTML_SEARCH_URL = "https://duckduckgo.com/html/"
BING_SEARCH_URL = "https://www.bing.com/search"
_ALLOWED_EXTS = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".pptx", ".txt", ".md"}
TIMEOUT_SECONDS = 18
DEFAULT_MAX_RESULTS = 8


SOURCE_CLASS_RULES: list[tuple[str, list[str], list[str], int, list[str]]] = [
    ("政府", ["gov.cn", "gov.", "sec", "un.org", "worldbank.org", "asean.org"], ["政策", "公告", "统计", "制度", "报告"], 10, ["zh", "en"]),
    ("协会", ["china-semi.org", "semiconchina", "sme.org", "association", "society", "iee.org"], ["协会", "学会", "研讨", "论坛", "会员"], 8, ["zh", "en"]),
    ("券商", ["sectors", "equity", "research", "analyst", "institution"], ["研报", "研究", "收益", "目标价", "评级", "券商"], 7, ["zh", "en"]),
    ("咨询机构", ["mcw", "bain", "deloitte", "mckinsey", "pwc", "kpmg", "bcg", "bcg.", "gt", "idc"], ["咨询", "策略", "市场规模", "路线图"], 7, ["zh", "en"]),
    ("公司", [".com", ".cn", ".org", ".hk"], ["公司", "公告", "财报", "年报", "投资者", "业绩"], 6, ["zh", "en"]),
    ("媒体", ["baidu.com", "finance.sina", "wallstreetcn", "reuters.com", "bloomberg", "ft.com"], ["转载", "快讯", "新闻", "日报"], 4, ["zh", "en"]),
]


@dataclass(frozen=True, slots=True)
class 候选来源:
    source_uri: str
    title: str
    source_type: str
    region: str
    source_credibility: int
    language: str
    published_at: str | None = None
    summary: str | None = None
    source_name: str | None = None

    def 转字典(self) -> dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "title": self.title,
            "source_type": self.source_type,
            "region": self.region,
            "source_credibility": self.source_credibility,
            "language": self.language,
            "published_at": self.published_at,
            "summary": self.summary,
            "source_name": self.source_name,
        }


def _safe_region(region: str) -> str:
    if region in {"中国", "全球", "用户"}:
        return region
    return "全球"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _normalize_title(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    return value[:120] if value else "未命名来源"

def _is_attachment(uri: str) -> bool:
    suffix = Path(uri.split("?")[0]).suffix.lower()
    return suffix in _ALLOWED_EXTS


def _domain(uri: str) -> str:
    try:
        return _urlparse.urlparse(uri).netloc.lower()
    except Exception:
        return ""


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _classify_source(uri: str, title: str = "", snippet: str = "") -> tuple[str, int, str]:
    text = f"{uri} {title} {snippet}".lower()
    domain = _domain(uri).lower()
    for source_type, keys, _keywords, score, _langs in SOURCE_CLASS_RULES:
        if any(k in text for k in keys) or any(k in domain for k in keys):
            return source_type, min(max(score, 1), 10), _guess_lang(text)
    if "gov" in domain:
        return "政府", 9, _guess_lang(text)
    return "公司", 6, _guess_lang(text)


def _guess_lang(text: str) -> str:
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return "zh" if cn_chars >= 20 else "en"


def _resolve_region(source_type: str, uri: str, preferred: str | None = None) -> str:
    if preferred in {"中国", "全球"}:
        return preferred
    domain = _domain(uri)
    if ".cn" in domain:
        return "中国"
    return "全球"


def 生成搜索查询矩阵(行业: str, include_global: bool, 行业包路径: Path | None = None) -> dict[str, dict[str, list[str]]]:
    行业包 = 读取行业包(行业包路径 or Path("."), 行业) if 行业包路径 else {}
    base = [行业, f"{行业} 产业链", f"{行业} 市场规模", f"{行业} 需求 12 个月", f"{行业} 产能", f"{行业} 头部公司"]
    china = [f"{行业} 中国 报告", f"{行业} 中国 政策", f"{行业} 中国 龙头企业", f"{行业} 中国 市场竞争"]
    global_terms = [f"{行业} global report", f"{行业} market outlook", f"{行业} supply chain", f"{行业} demand forecast"]

    if 行业包:
        config = 行业包.get("config", {})
        coverage = config.get("覆盖范围", {})
        window = coverage.get("窗口月数")
        关键月 = coverage.get("关键数据月数")
        if isinstance(window, int):
            base.append(f"{行业} 最近 {window} 个月 行业动态")
        if isinstance(关键月, int):
            base.append(f"{行业} 最近 {关键月} 个月 关键指标")

        taxonomy = 行业包.get("taxonomy", {})
        terms = taxonomy.get("query_terms", {})
        if isinstance(terms, dict):
            china.extend([str(x) for x in terms.get("china", []) if str(x).strip()])
            if include_global:
                global_terms.extend([str(x) for x in terms.get("global", []) if str(x).strip()])
        base.extend([str(x) for x in taxonomy.get("core_terms", []) if str(x).strip()])

    query_matrix = {
        "中国": china + base,
    }
    if include_global:
        query_matrix["全球"] = base + global_terms
    return {"区域": query_matrix}


def _parse_search_results(html: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[tuple[str, str, str]] = []
    for a in soup.select("a.result__a"):
        href = a.get("href", "").strip()
        title = _normalize_title(a.get_text(" ", strip=True))
        snippet = ""
        if a.parent is not None:
            parent_text = a.parent.get_text(" ", strip=True)
            if parent_text and title in parent_text:
                snippet = parent_text.replace(title, "", 1)
        if href and href.startswith("http"):
            items.append((href, title, snippet))
    return items


def 搜索网页源(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[tuple[str, str, str]]:
    if max_results <= 0:
        return []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(HTML_SEARCH_URL, params={"q": query}, headers=headers, timeout=TIMEOUT_SECONDS)
    except Exception as exc:
        raise RuntimeError(f"网络搜索失败: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(f"搜索返回非预期状态码: {response.status_code}")

    raw = _parse_search_results(response.text)
    return _dedupe_keep_order([tuple(x) for x in raw])[:max_results]  # type: ignore[arg-type]


def 搜索Bing源(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[tuple[str, str, str]]:
    """通过 Bing HTML 搜索，返回 (href, title, snippet) 列表。

    Bing 国内可达、对中文关键词支持较好，作为 DuckDuckGo 之外的网页搜索回退。
    """
    if max_results <= 0:
        return []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(
            BING_SEARCH_URL,
            params={"q": query, "count": max_results, "mkt": "zh-CN"},
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise RuntimeError(f"Bing 搜索失败: {exc}") from exc
    if response.status_code != 200:
        raise RuntimeError(f"Bing 搜索返回非预期状态码: {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")
    items: list[tuple[str, str, str]] = []
    for node in soup.select("li.b_algo"):
        anchor = node.select_one("h2 a") or node.select_one("a[href]")
        if anchor is None:
            continue
        href = str(anchor.get("href", "")).strip()
        title = _normalize_title(anchor.get_text(" ", strip=True))
        if not href or not title or href.startswith("javascript:"):
            continue
        # 解析 Bing 重定向链接拿到真实 URL
        if "bing.com/ck/a" in href:
            real = _解析Bing重定向(href)
            href = real or href
        snippet = ""
        cap = node.select_one("p") or node.select_one("div.b_caption")
        if cap is not None:
            snippet = cap.get_text(" ", strip=True)[:300]
        if href.startswith("http"):
            items.append((href, title, snippet))
    return _dedupe_keep_order(items)[:max_results]


def _解析Bing重定向(ck_url: str) -> str:
    """从 Bing /ck/a 重定向链接中提取真实目标 URL。"""
    try:
        parsed = _urlparse.urlparse(ck_url)
        params = dict(_urlparse.parse_qsl(parsed.query))
        target = params.get("u")
        if target:
            return target
    except Exception:
        pass
    return ""


def 探测附件(来源页面: str) -> list[str]:
    if _is_attachment(来源页面):
        return [来源页面]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(来源页面, headers=headers, timeout=TIMEOUT_SECONDS)
    except Exception:
        return []

    if response.status_code != 200:
        return []

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type and response.content:
        return [来源页面]

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    链接: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        if not _urlparse.urlparse(href).scheme:
            base = _urlparse.urlparse(来源页面)
            href = _urlparse.urljoin(f"{base.scheme}://{base.netloc}{base.path}", href)
        if _is_attachment(href):
            链接.append(href)
    return _dedupe_keep_order(链接)


def 执行检索(
    行业: str,
    行业包路径: Path | None = None,
    include_global: bool = True,
    max_queries_per_region: int = 12,
    max_candidates: int = 40,
    preferred_region: str | None = None,
) -> list[候选来源]:
    查询矩阵 = 生成搜索查询矩阵(行业, include_global, 行业包路径)
    region_map = 查询矩阵["区域"]
    source_pack = 读取行业包(行业包路径 or Path("."), 行业) if 行业包路径 else {}
    preferreds = [
        "中国" if not preferred_region else _safe_region(preferred_region),
        "全球",
        "中国",
    ]
    preferred_region_score = {region: idx for idx, region in enumerate(preferreds)}

    results: list[候选来源] = []
    for region, queries in region_map.items():
        if preferred_region and region != preferred_region:
            continue
        for query in queries[:max_queries_per_region]:
            try:
                hits = 搜索网页源(query, max_results=6)
            except Exception:
                continue
            for href, title, snippet in hits:
                source_type, score, lang = _classify_source(href, title=title, snippet=snippet)
                region_ = _resolve_region(source_type, href, region)
                if not isinstance(score, int):
                    score = 5
                c = 候选来源(
                    source_uri=href,
                    title=title,
                    source_type=source_type,
                    region=region_,
                    source_credibility=score,
                    language=lang,
                    published_at=None,
                    summary=snippet[:140],
                    source_name=source_pack.get("config", {}).get("来源名称", None),
                )
                if c.source_credibility >= 3:
                    results.append(c)
                if len(results) >= max_candidates:
                    break
            if len(results) >= max_candidates:
                break
        if len(results) >= max_candidates:
            break

    # 同一来源去重与轻排序：优先官方高可信 + 地理匹配
    dedup_map: dict[str, 候选来源] = {}
    for item in results:
        dedup_map[item.source_uri] = item
    merged = list(dedup_map.values())
    merged.sort(
        key=lambda x: (
            preferred_region_score.get(x.region, 99),
            -x.source_credibility,
            x.region,
            x.source_uri,
        )
    )
    return merged[:max_candidates]


def 保存候选清单(候选: list[候选来源], 输出文件: Path) -> int:
    输出文件.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for item in 候选:
        payload = item.转字典()
        payload["candidate_id"] = f"cand-{_timestamp()}-{len(lines):04d}"
        lines.append(payload)
    输出文件.write_text(
        "\n".join([__import__("json").dumps(line, ensure_ascii=False) for line in lines]) + ("\n" if lines else ""),
        encoding="utf-8",
    )
    return len(lines)


def 读取候选清单(来源文件: Path) -> list[候选来源]:
    if not 来源文件.exists():
        return []
    out: list[候选来源] = []
    for raw in 来源文件.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        obj = __import__("json").loads(raw)
        if "source_uri" not in obj:
            continue
        out.append(
            候选来源(
                source_uri=obj.get("source_uri", ""),
                title=obj.get("title", ""),
                source_type=obj.get("source_type", "未知"),
                region=obj.get("region", "全球"),
                source_credibility=int(obj.get("source_credibility", 5)),
                language=obj.get("language", "en"),
                published_at=obj.get("published_at"),
                summary=obj.get("summary"),
                source_name=obj.get("source_name"),
            )
        )
    return out
