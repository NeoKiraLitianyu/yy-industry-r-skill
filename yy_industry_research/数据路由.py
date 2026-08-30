from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import hashlib
import os
from pathlib import Path
from typing import Any, Iterable, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(slots=True)
class 标准候选:
    原始链接: str
    标题: str
    发现通道: list[str] | str
    地区: str
    来源类型: str = "未知"
    发布日期: str | None = None
    摘要: str = ""
    来源名称: str = ""
    语言: str = "zh"
    可信度: int = 5
    元数据: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.发现通道, str):
            self.发现通道 = [self.发现通道]

    def 转候选字典(self) -> dict[str, Any]:
        payload = {
            "source_uri": self.原始链接,
            "title": self.标题,
            "source_type": self.来源类型,
            "region": self.地区,
            "language": self.语言,
            "source_credibility": self.可信度,
            "published_at": self.发布日期,
            "summary": self.摘要,
            "source_name": self.来源名称,
            "discovery_channels": list(self.发现通道),
            "provider_metadata": self.元数据,
        }
        if self.元数据.get("local_path"):
            payload["local_path"] = self.元数据["local_path"]
        return payload


@dataclass(frozen=True, slots=True)
class 适配器回执:
    适配器: str
    状态: str
    候选数: int
    错误: str | None = None
    时间: str = ""


@dataclass(slots=True)
class 路由结果:
    候选: list[标准候选]
    回执: list[适配器回执]


class 数据源适配器(Protocol):
    名称: str
    优先级: int

    def 检索(self, 请求: dict[str, Any]) -> Iterable[标准候选]: ...


def _规范链接(uri: str) -> str:
    parts = urlsplit(uri.strip())
    if not parts.scheme:
        return uri.strip().lower()
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"spm", "from", "source"}
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


class 数据源路由器:
    def __init__(self, 适配器: Iterable[数据源适配器]):
        self._适配器 = sorted(适配器, key=lambda item: int(item.优先级))

    def 检索(self, 行业: str, 最大结果数: int = 80, **参数: Any) -> 路由结果:
        请求 = {"行业": 行业, "最大结果数": 最大结果数, **参数}
        合并: dict[str, 标准候选] = {}
        回执: list[适配器回执] = []
        for adapter in self._适配器:
            try:
                found = list(adapter.检索(请求))
                回执.append(
                    适配器回执(
                        适配器=adapter.名称,
                        状态="成功",
                        候选数=len(found),
                        时间=datetime.now().isoformat(timespec="seconds"),
                    )
                )
            except Exception as exc:
                回执.append(
                    适配器回执(
                        适配器=adapter.名称,
                        状态="降级",
                        候选数=0,
                        错误=str(exc),
                        时间=datetime.now().isoformat(timespec="seconds"),
                    )
                )
                continue

            for candidate in found:
                key = _规范链接(candidate.原始链接) or candidate.标题.strip().lower()
                if key in 合并:
                    existing = 合并[key]
                    for channel in candidate.发现通道:
                        if channel not in existing.发现通道:
                            existing.发现通道.append(channel)
                    existing.可信度 = max(existing.可信度, candidate.可信度)
                    if not existing.发布日期 and candidate.发布日期:
                        existing.发布日期 = candidate.发布日期
                    if len(candidate.摘要) > len(existing.摘要):
                        existing.摘要 = candidate.摘要
                    continue
                合并[key] = candidate

        return 路由结果(list(合并.values())[:最大结果数], 回执)


def _原子写(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".临时")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def 保存路由结果(result: 路由结果, 输出目录: str | Path) -> dict[str, Path]:
    root = Path(输出目录).resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidates = root / f"多源候选_{stamp}.jsonl"
    receipt = root / f"数据源回执_{stamp}.json"
    for item in result.候选:
        if item.元数据.get("metadata_only") and "://" in item.原始链接:
            scheme = item.原始链接.split("://", 1)[0].lower()
            if scheme in {"yixin", "tdx", "mcp"}:
                digest = hashlib.sha256(item.原始链接.encode("utf-8")).hexdigest()[:24]
                raw_path = root / "MCP原始回执" / f"{scheme}_{digest}.json"
                _原子写(
                    raw_path,
                    json.dumps(
                        {
                            "原始标识": item.原始链接,
                            "标题": item.标题,
                            "来源名称": item.来源名称,
                            "来源类型": item.来源类型,
                            "发布日期": item.发布日期,
                            "发现通道": item.发现通道,
                            "原始元数据": item.元数据,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                )
                item.元数据["local_path"] = str(raw_path)
    candidate_text = "\n".join(json.dumps(item.转候选字典(), ensure_ascii=False) for item in result.候选)
    if candidate_text:
        candidate_text += "\n"
    _原子写(candidates, candidate_text)
    _原子写(
        receipt,
        json.dumps(
            {
                "生成时间": datetime.now().isoformat(timespec="seconds"),
                "候选数": len(result.候选),
                "回执": [asdict(item) for item in result.回执],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return {"候选清单": candidates, "运行回执": receipt}


def _来源类型(source_type: str) -> str:
    return {
        "report": "券商咨询",
        "academic": "学术标准",
        "announcement": "公司一手",
        "expert": "专家访谈",
        "web": "网络来源",
    }.get(source_type, "网络来源")


def 规范化Yixin结果(原始结果: Iterable[dict[str, Any]], source_type: str = "report") -> list[标准候选]:
    out: list[标准候选] = []
    for group in 原始结果:
        entries = group.get("content") if isinstance(group.get("content"), list) else [group]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or entry.get("name") or "").strip()
            link = str(entry.get("link") or entry.get("url") or "").strip()
            if not title:
                continue
            metadata_only = not bool(link)
            if metadata_only:
                digest = hashlib.sha256(
                    f"{source_type}|{group.get('query', '')}|{title}|{entry.get('date', '')}".encode("utf-8")
                ).hexdigest()[:20]
                link = f"yixin://{source_type}/{digest}"
            text = title + " " + str(entry.get("snippet") or entry.get("content") or "")
            region = "中国" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "全球"
            source_name = str(
                entry.get("source")
                or entry.get("publisher")
                or (entry.get("extra") or {}).get("institution")
                or ""
            ).strip()
            if not source_name and source_type == "announcement":
                source_name = title.replace("：", ":").split(":", 1)[0].strip()
            source_name = source_name or "Yixin"
            out.append(
                标准候选(
                    原始链接=link,
                    标题=title,
                    发现通道=[f"Yixin/{source_type}"],
                    地区=region,
                    来源类型=_来源类型(source_type),
                    发布日期=str(entry.get("date") or entry.get("published_at") or "") or None,
                    摘要=str(entry.get("snippet") or entry.get("introduction") or entry.get("content") or "")[:500],
                    来源名称=source_name,
                    语言="zh" if region == "中国" else "en",
                    可信度=8 if source_type in {"report", "academic", "announcement"} else 6,
                    元数据={
                        "query": group.get("query", ""),
                        "raw_source": source_type,
                        "metadata_only": metadata_only,
                        "title": title,
                        "snippet": str(entry.get("snippet") or entry.get("content") or "")[:5000],
                        "date": entry.get("date"),
                        "extra": entry.get("extra") or {},
                    },
                )
            )
    return out


def 规范化TDX结果(原始结果: dict[str, Any] | list[Any], source_type: str = "report") -> list[标准候选]:
    if isinstance(原始结果, dict):
        entries = 原始结果.get("data") or 原始结果.get("result") or 原始结果.get("reports") or []
        if not isinstance(entries, list):
            entries = [原始结果]
    else:
        entries = 原始结果
    out: list[标准候选] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or entry.get("标题") or entry.get("name") or "").strip()
        link = str(entry.get("url") or entry.get("link") or entry.get("原文链接") or "").strip()
        if not title or not link:
            continue
        out.append(
            标准候选(
                原始链接=link,
                标题=title,
                发现通道=[f"TDX/{source_type}"],
                地区="中国",
                来源类型="公司一手" if source_type == "announcement" else "券商咨询",
                发布日期=str(entry.get("date") or entry.get("发布日期") or "") or None,
                摘要=str(entry.get("summary") or entry.get("摘要") or "")[:500],
                来源名称=str(entry.get("org") or entry.get("机构") or "TDX"),
                语言="zh",
                可信度=8,
                元数据={"raw_source": source_type},
            )
        )
    return out
