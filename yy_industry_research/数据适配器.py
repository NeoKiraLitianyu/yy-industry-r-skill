from __future__ import annotations

import json
import importlib.util
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

from .凭据 import 读取NeoStar连接配置, 读取凭据配置
from .数据路由 import 标准候选, 规范化TDX结果, 规范化Yixin结果
from .相关性 import 评估膜材相关性


def _读取凭据(env_file: str | Path | None = None) -> dict[str, str]:
    values = 读取凭据配置()
    if env_file:
        for key, value in 读取NeoStar连接配置(env_file).items():
            values.setdefault(key, value)
    return values


def _读取Yixin密钥() -> str:
    return _读取凭据().get("YIXIN_API_KEY", "")


class Yixin适配器:
    名称 = "yixin"
    优先级 = 10

    def __init__(
        self,
        transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        查询上限: int = 8,
        每类结果数: int = 10,
        timeout: int = 12,
    ):
        self._transport = transport or self._请求
        self.查询上限 = max(1, 查询上限)
        self.每类结果数 = max(1, min(50, 每类结果数))
        self.timeout = timeout

    def _请求(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        key = _读取Yixin密钥()
        if not key:
            raise PermissionError("Yixin API key 缺失")
        req = urllib.request.Request(
            "https://openapi.billionsintelligence.com" + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json", "X-API-KEY": key},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))

    def 检索(self, 请求: dict[str, Any]) -> Iterable[标准候选]:
        queries = [str(item).strip() for item in 请求.get("查询词", []) if str(item).strip()]
        if not queries:
            queries = [str(请求["行业"])]
        for query in queries[: self.查询上限]:
            for source_type in ("report", "academic", "announcement"):
                payload = {
                    "query": query,
                    "source": source_type,
                    "count": self.每类结果数,
                    "search_mode": "advanced",
                }
                time_range = 请求.get("时间范围")
                if time_range:
                    payload["time_range"] = time_range
                data = self._transport("/api/v2/search", payload)
                candidates = 规范化Yixin结果((data or {}).get("result") or [], source_type)
                for candidate in candidates:
                    if str(请求.get("行业", "")) == "半导体膜材":
                        relevance = 评估膜材相关性(candidate)
                        candidate.元数据["相关性"] = relevance
                        if not relevance["是否相关"]:
                            continue
                    yield candidate


class _TDXMcpClient:
    def __init__(self, timeout: int = 15, env_file: str | Path | None = None):
        config = _读取凭据(env_file)
        self.url = config.get("TDX_MCP_URL") or "https://txmcp.tdx.com.cn:3001/txmcp"
        self.key = config.get("TDX_MCP_API_KEY", "")
        self.timeout = timeout
        self.session_id = ""

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            self.session_id = self.session_id or str(response.headers.get("Mcp-Session-Id") or "")
            raw = response.read().decode("utf-8", "replace")
        if raw.lstrip().startswith("event:"):
            raw = "\n".join(line[5:].strip() for line in raw.splitlines() if line.startswith("data:"))
        return json.loads(raw)

    def _ensure_session(self) -> None:
        if self.session_id:
            return
        self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "yy-industry-r-skill", "version": "1.0"},
                },
            }
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_session()
        obj = self._post(
            {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000) % 1_000_000,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            }
        )
        result = obj.get("result") or {}
        texts = [item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"]
        for text in texts:
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                start = text.find("{")
                if start >= 0:
                    try:
                        return json.loads(text[start:])
                    except ValueError:
                        pass
        return result

    def reports(self, query: str, top_k: int = 10) -> dict[str, Any]:
        return self._call("wenda_report_query", {"query": query, "top_k": top_k})

    def notices(self, query: str, top_k: int = 10) -> dict[str, Any]:
        return self._call("wenda_notice_query", {"query": query, "top_k": top_k})


class TDX适配器:
    名称 = "tdx"
    优先级 = 20

    def __init__(self, client: Any | None = None, enabled: bool | None = None, 每次上限: int = 6, env_file: str | Path | None = None):
        config = _读取凭据(env_file)
        self.client = client or _TDXMcpClient(env_file=env_file)
        self.enabled = (config.get("TDX_MCP_ENABLED") == "1") if enabled is None else enabled
        self.每次上限 = max(1, 每次上限)

    def 检索(self, 请求: dict[str, Any]) -> Iterable[标准候选]:
        if not self.enabled:
            raise PermissionError("TDX MCP 未启用；计费源必须显式授权")
        queries = [str(item).strip() for item in 请求.get("查询词", []) if str(item).strip()]
        if not queries:
            queries = [str(请求["行业"])]
        calls = 0
        有效响应 = False
        for query in queries:
            if calls >= self.每次上限:
                break
            report_response = self.client.reports(query, top_k=10)
            if report_response is not None:
                有效响应 = True
                yield from 规范化TDX结果(report_response or {}, "report")
            calls += 1
            if calls >= self.每次上限:
                break
            notice_response = self.client.notices(query, top_k=10)
            if notice_response is not None:
                有效响应 = True
                yield from 规范化TDX结果(notice_response or {}, "announcement")
            calls += 1
        if not 有效响应:
            raise RuntimeError("TDX 原生客户端未取得有效响应（握手、认证或服务状态异常）")


def 创建TDX适配器(
    neostar_root: str | Path | None,
    *,
    enabled: bool | None = None,
    每次上限: int = 6,
    env_file: str | Path | None = None,
) -> TDX适配器:
    """NeoStar 内优先复用其原生计费/预算客户端，分发版回退独立客户端。"""

    if neostar_root:
        module_path = (
            Path(neostar_root).resolve()
            / "二级市场交易"
            / "KiraQuant"
            / "data"
            / "tdx_mcp_adapter.py"
        )
        if module_path.is_file():
            try:
                spec = importlib.util.spec_from_file_location("neostar_tdx_mcp_adapter", module_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    client = module.TdxMcpClient(enabled=enabled)
                    adapter = TDX适配器(client=client, enabled=enabled, 每次上限=每次上限, env_file=env_file)
                    adapter.名称 = "tdx/NeoStar原生"
                    return adapter
            except Exception:
                # 回退客户端仍保留完整回执，不能因本地桥接失败中断其他来源。
                pass
    return TDX适配器(enabled=enabled, 每次上限=每次上限, env_file=env_file)


class NeoStar本地适配器:
    名称 = "NeoStar本地"
    优先级 = 30
    _子目录 = (
        ("星图数据库/产业图谱研究", "NeoStar星图"),
        ("星图数据库/NeoData/industry", "NeoStar星图"),
        ("一级市场机会/_知识库", "NeoStar一级知识库"),
    )
    _文本后缀 = {".md", ".txt", ".json", ".jsonl", ".csv"}
    _资料后缀 = _文本后缀 | {".pdf", ".docx", ".xlsx"}

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def 检索(self, 请求: dict[str, Any]) -> Iterable[标准候选]:
        terms = [str(item).strip().lower() for item in 请求.get("查询词", []) if str(item).strip()]
        if not terms:
            terms = [str(请求["行业"]).lower()]
        limit = int(请求.get("最大结果数", 80))
        emitted = 0
        for relative, source_type in self._子目录:
            base = (self.root / relative).resolve()
            if not base.is_dir() or self.root not in base.parents:
                continue
            for path in base.rglob("*"):
                if emitted >= limit:
                    return
                if not path.is_file() or path.suffix.lower() not in self._资料后缀:
                    continue
                haystack = path.name.lower()
                if path.suffix.lower() in self._文本后缀:
                    try:
                        haystack += " " + path.read_text(encoding="utf-8", errors="ignore")[:2_000_000].lower()
                    except OSError:
                        continue
                matched = [term for term in terms if term in haystack]
                if not matched:
                    continue
                emitted += 1
                yield 标准候选(
                    原始链接=str(path),
                    标题=path.stem,
                    发现通道=["NeoStar本地"],
                    地区="中国",
                    来源类型=source_type,
                    来源名称="NeoStar",
                    语言="zh",
                    可信度=7,
                    摘要=f"本地命中：{', '.join(matched[:5])}",
                    元数据={"local_path": str(path), "matched_terms": matched},
                )


class 公开网页适配器:
    名称 = "公开网页"
    优先级 = 90

    def __init__(self, search: Callable[..., Iterable[Any]] | None = None, 行业包路径: str | Path | None = None):
        if search is None:
            from .检索 import 执行检索

            search = 执行检索
        self.search = search
        self.行业包路径 = Path(行业包路径).resolve() if 行业包路径 else None

    def 检索(self, 请求: dict[str, Any]) -> Iterable[标准候选]:
        maximum = int(请求.get("最大结果数", 80))
        found = self.search(
            str(请求["行业"]),
            行业包路径=self.行业包路径,
            include_global=bool(请求.get("包含全球", True)),
            max_queries_per_region=int(请求.get("每区查询上限", 12)),
            max_candidates=maximum,
        )
        for item in found:
            yield 标准候选(
                原始链接=str(item.source_uri),
                标题=str(item.title),
                发现通道=["公开网页"],
                地区=str(item.region),
                来源类型=str(item.source_type),
                发布日期=getattr(item, "published_at", None),
                摘要=str(getattr(item, "summary", "") or ""),
                来源名称=str(getattr(item, "source_name", "") or ""),
                语言=str(getattr(item, "language", "") or "zh"),
                可信度=int(getattr(item, "source_credibility", 5) or 5),
            )
