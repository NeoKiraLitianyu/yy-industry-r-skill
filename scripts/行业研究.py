#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import sqlite3
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import requests

技能目录 = Path(__file__).resolve().parents[1]
if str(技能目录) not in sys.path:
    sys.path.insert(0, str(技能目录))

from yy_industry_research.归档 import 归档原始文件
from yy_industry_research.行业包 import 读取行业包, 提取行业命中节点
from yy_industry_research.检索 import 生成搜索查询矩阵, 执行检索, 读取候选清单, 保存候选清单, 探测附件, 搜索网页源, 搜索Bing源
from yy_industry_research.数据路由 import 数据源路由器, 保存路由结果
from yy_industry_research.数据适配器 import NeoStar本地适配器, Yixin适配器, 公开网页适配器, 创建TDX适配器
from yy_industry_research.解析 import 解析文件
from yy_industry_research.事实提取 import 提取事实候选
from yy_industry_research.指纹 import 文件sha256, 生成指纹
from yy_industry_research.资料库 import 初始化资料库
from yy_industry_research.索引 import (
    初始化行业索引,
    查找同文件指纹,
    写入来源,
    写入文档,
    写入运行记录,
    写入映射,
    写入证据,
    写入事实,
    统计来源数,
)
from yy_industry_research.验证 import 执行全量交叉验证, 统计验证结果
from yy_industry_research.报告 import 生成深度研究报告, 校验研究内容
from yy_industry_research.策展事实 import 装载策展事实, 装载策展Mapping

TIMEOUT_SECONDS = 20
REQUEST_TIMEOUT = 20


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="中国与全球行业研究主入口")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("初始化", help="初始化行业资料库")
    init_cmd.add_argument("--行业", required=True)
    init_cmd.add_argument("--资料库", required=True)
    init_cmd.add_argument("--行业包", default=None)

    plan_cmd = sub.add_parser("计划", help="生成检索计划")
    plan_cmd.add_argument("--行业", required=True)
    plan_cmd.add_argument("--资料库", default=None)
    plan_cmd.add_argument("--全球", action="store_true", default=True)
    plan_cmd.add_argument("--行业包", default=None)
    plan_cmd.add_argument("--max-queries-per-region", type=int, default=12)

    run_cmd = sub.add_parser("运行", help="执行研究流程（抓取/归档/解析/验证）")
    run_cmd.add_argument("--行业", required=True)
    run_cmd.add_argument("--资料库", required=True)
    run_cmd.add_argument("--输入", nargs="*", default=[])
    run_cmd.add_argument("--来源清单", default=None, help="候选来源 JSONL（优先）")
    run_cmd.add_argument("--自动检索", action="store_true", help="基于检索计划补抓资料")
    run_cmd.add_argument("--仅公开源", action="store_true", help="不启用 NeoStar/yixin/TDX 增强源")
    run_cmd.add_argument("--禁用-yixin", action="store_true", help="跳过 yixin OpenAPI")
    run_cmd.add_argument("--启用-tdx", action="store_true", help="显式启用按调用计费的 TDX MCP")
    run_cmd.add_argument("--neostar-root", default=None, help="NeoStar 根目录；省略时自动发现或读取 NEOSTAR_ROOT")
    run_cmd.add_argument("--时间范围", default="past 24 months", help="多源检索时间范围")
    run_cmd.add_argument("--全球", action="store_true", default=False, help="检索计划包含全球源")
    run_cmd.add_argument("--max-queries-per-region", type=int, default=12)
    run_cmd.add_argument("--max-candidates", type=int, default=40)
    run_cmd.add_argument("--skip-validation", action="store_true")
    run_cmd.add_argument("--region", choices=["中国", "全球", "用户"], default="用户")
    run_cmd.add_argument("--ignore-parse-fail", action="store_true")

    verify_cmd = sub.add_parser("验收", help="输出结构、索引和阶段状态")
    verify_cmd.add_argument("--资料库", required=True)

    report_cmd = sub.add_parser("报告", help="输出最新中文研究报告")
    report_cmd.add_argument("--资料库", required=True)
    report_cmd.add_argument("--出版PDF", action="store_true", help="证据门通过后生成紫色 HTML/PDF 出版物")
    report_cmd.add_argument("--输出目录", default=None, help="出版物目录；默认写入资料库/研究报告")

    fetch_cmd = sub.add_parser("抓取", help="对外抓取现成的行业报告/研报（不创作新报告）")
    fetch_cmd.add_argument("--主题", required=True, help="要抓取的主题，例如 光模块 或 半导体膜材")
    fetch_cmd.add_argument(
        "--来源",
        default="all",
        help="数据源，逗号分隔：bing/yixin/duckduckgo/all（默认 all=全部可用源）",
    )
    fetch_cmd.add_argument("--数量", type=int, default=10, help="最多抓取结果数（默认10）")
    fetch_cmd.add_argument("--时间范围", default="past 12 months", help="时间范围（yixin 源使用）")
    fetch_cmd.add_argument("--输出目录", default=".", help="PDF/附件下载目录；默认当前目录")
    fetch_cmd.add_argument("--仅列表", action="store_true", help="只列清单，不下载附件")
    fetch_cmd.add_argument("--json", action="store_true", help="输出机器可读 JSON 清单")

    status_cmd = sub.add_parser("状态", help="展示技能基本信息")

    return parser


def _resolve_workspace() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_region(region: str) -> str:
    return region if region in {"中国", "全球"} else "用户"


def _safe_filename(name: str) -> str:
    name = "".join(ch if ch.isalnum() or ch in "._-()[]" else "_" for ch in name)
    return name[:180].strip("._-") or "source"


def _slug(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\-\.]+", "-", text)


def _build_source_key(行业: str, source_name: str, source_uri: str) -> str:
    return hashlib.sha256(f"{行业}|{source_name}|{source_uri}".encode("utf-8")).hexdigest()[:18]


def _is_http_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _download(url: str, target_dir: Path, timeout: int = REQUEST_TIMEOUT) -> Path:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    suffix = Path(url.split("?")[0]).suffix.lower()
    if not suffix:
        if "pdf" in content_type:
            suffix = ".pdf"
        elif "spreadsheet" in content_type:
            suffix = ".xlsx"
        elif "text/csv" in content_type:
            suffix = ".csv"
        elif "html" in content_type:
            suffix = ".html"
        elif "text/plain" in content_type:
            suffix = ".txt"
        else:
            suffix = ".bin"
    filename = _safe_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{_slug(Path(url).name or 'source')}{suffix}")
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / filename
    out.write_bytes(response.content)
    return out


def _resolve_credibility(record: dict) -> int:
    try:
        val = int(record.get("source_credibility", 5))
    except Exception:
        val = 5
    return max(1, min(10, val))


def _run_init(args: argparse.Namespace) -> int:
    root = 初始化资料库(args.资料库, args.行业, args.行业包)
    db_path = Path(root) / "行业索引.sqlite"
    初始化行业索引(db_path)
    print(f"[行业研究] 资料库初始化完成: {root}")
    return 0


def _run_plan(args: argparse.Namespace, skill_root: Path) -> int:
    pack = 读取行业包(skill_root, args.行业)
    matrix = 生成搜索查询矩阵(
        行业=args.行业,
        include_global=args.全球,
        行业包路径=skill_root,
    )
    print(json.dumps(matrix, ensure_ascii=False, indent=2))
    return 0


def _iter_inputs(
    run_args: argparse.Namespace,
    skill_root: Path,
) -> list[dict]:
    items: list[dict] = []

    for raw in run_args.输入:
        if _is_http_url(raw):
            items.append(
                {
                    "source_uri": raw,
                    "title": raw,
                    "source_type": "网络来源",
                    "region": _safe_region(run_args.region),
                    "language": "zh",
                    "source_credibility": 5,
                    "source_name": run_args.行业,
                }
            )
        else:
            path = Path(raw).resolve()
            if path.exists():
                items.append(
                    {
                        "source_uri": str(path),
                        "title": path.name,
                        "source_type": "用户上传",
                        "region": "用户",
                        "language": "zh",
                        "source_credibility": 7,
                        "source_name": run_args.行业,
                        "local_path": str(path),
                    }
                )

    if run_args.来源清单:
        items.extend(
            [
                {
                    "source_uri": candidate.source_uri,
                    "title": candidate.title,
                    "source_type": candidate.source_type,
                    "region": candidate.region,
                    "language": candidate.language,
                    "source_credibility": candidate.source_credibility,
                    "source_name": candidate.source_name or run_args.行业,
                }
                for candidate in 读取候选清单(Path(run_args.来源清单))
            ]
        )

    if run_args.自动检索:
        authoritative_file = skill_root / "industry-packs" / run_args.行业 / "authoritative_sources.jsonl"
        if authoritative_file.is_file():
            authoritative = 读取候选清单(authoritative_file)
            items.extend(
                {
                    "source_uri": candidate.source_uri,
                    "title": candidate.title,
                    "source_type": candidate.source_type,
                    "region": candidate.region,
                    "language": candidate.language,
                    "source_credibility": candidate.source_credibility,
                    "source_name": candidate.source_name or run_args.行业,
                    "published_at": candidate.published_at,
                    "summary": candidate.summary,
                    "discovery_channels": ["行业包权威种子"],
                }
                for candidate in authoritative
            )
            print(f"[行业研究] 行业包权威原始来源: {authoritative_file}（{len(authoritative)}项）")
        matrix = 生成搜索查询矩阵(run_args.行业, run_args.全球, skill_root)
        queries: list[str] = []
        for region_queries in matrix.get("区域", {}).values():
            for query in region_queries:
                if query not in queries:
                    queries.append(query)
        query_limit = max(1, run_args.max_queries_per_region * (2 if run_args.全球 else 1))

        adapters = []
        if not run_args.仅公开源:
            root_value = run_args.neostar_root or os.environ.get("NEOSTAR_ROOT")
            if root_value:
                neostar_root = Path(root_value).expanduser().resolve()
            else:
                candidate_root = skill_root.parents[1]
                neostar_root = candidate_root if (candidate_root / "一级市场机会").is_dir() else None
            if not run_args.禁用_yixin:
                adapters.append(Yixin适配器(查询上限=query_limit))
            env_file = neostar_root / "_root_config" / ".env" if neostar_root else None
            adapters.append(
                创建TDX适配器(
                    neostar_root,
                    enabled=run_args.启用_tdx,
                    每次上限=min(6, query_limit * 2),
                    env_file=env_file,
                )
            )
            if neostar_root and neostar_root.is_dir():
                adapters.append(NeoStar本地适配器(neostar_root))
        adapters.append(公开网页适配器(行业包路径=skill_root))

        route_result = 数据源路由器(adapters).检索(
            run_args.行业,
            最大结果数=run_args.max_candidates,
            查询词=queries[:query_limit],
            时间范围=run_args.时间范围,
            包含全球=run_args.全球,
            每区查询上限=run_args.max_queries_per_region,
        )
        paths = 保存路由结果(route_result, Path(run_args.资料库) / "来源目录")
        print(f"[行业研究] 多源候选清单: {paths['候选清单']}")
        print(f"[行业研究] 数据源运行回执: {paths['运行回执']}")
        items.extend(item.转候选字典() for item in route_result.候选)

    deduped: list[dict] = []
    seen_uri: set[str] = set()
    for item in items:
        uri = str(item.get("source_uri", "")).strip()
        if not uri or uri in seen_uri:
            continue
        seen_uri.add(uri)
        deduped.append(item)
    return deduped


def _collect_files(item: dict, default_download_dir: Path) -> list[tuple[Path, dict]]:
    source_uri = item["source_uri"]
    if "local_path" in item:
        path = Path(item["local_path"])
        return [(path, item)] if path.exists() else []

    if not _is_http_url(source_uri):
        return []

    下载目录 = Path(item.get("download_dir", default_download_dir))
    docs: list[tuple[Path, dict]] = []

    try:
        docs.append((_download(source_uri, 下载目录), item))
    except Exception:
        pass

    try:
        attachments = 探测附件(source_uri)
    except Exception:
        attachments = []

    for attachment in attachments:
        try:
            docs.append((_download(attachment, 下载目录), item))
        except Exception:
            continue

    return docs


def _extract_text(archived: Path, parse_fail_dir: Path, ignore_parse_fail: bool) -> tuple[str, str, str]:
    try:
        parsed = 解析文件(archived)
        return str(parsed["text"]), "success", str(parsed["doc_type"])
    except Exception as exc:
        parse_fail_dir.mkdir(parents=True, exist_ok=True)
        (parse_fail_dir / archived.name).write_text(str(exc), encoding="utf-8")
        if ignore_parse_fail:
            return "", "failed", "text"
        raise


def _write_text_dump(root: Path, doc_id: int, archived: Path, text: str) -> Path:
    out_dir = root / "解析文本" / "正文"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{doc_id}_{archived.stem}.txt"
    out.write_text(text, encoding="utf-8")
    return out


def _build_run_report(root: Path, db_path: Path, report: dict, industry: str) -> tuple[Path, Path]:
    report_dir = root / "研究报告"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"run_{timestamp}.json"
    md_path = report_dir / f"report_{timestamp}.md"
    db_path = Path(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row

        facts = connection.execute(
            """
            SELECT
                f.fact_key,
                f.fact_value,
                f.unit,
                f.time_range,
                f.created_at,
                s.source_name,
                s.source_uri,
                s.source_type,
                s.region,
                s.credibility,
                s.id AS source_id,
                f.id AS fact_id
            FROM 事实 f
            JOIN 来源 s ON s.id = f.source_id
            ORDER BY f.fact_key, f.created_at DESC
            """
        ).fetchall()

        docs = connection.execute(
            """
            SELECT d.source_id, d.doc_type, d.filename, d.raw_path, d.parse_status, d.created_at
            FROM 文档 d
            ORDER BY d.created_at DESC
            """
        ).fetchall()
        docs_by_source = defaultdict(list)
        for doc in docs:
            docs_by_source[int(doc["source_id"])].append(doc)

        sources = connection.execute(
            """
            SELECT id, source_name, source_type, source_uri, region, language, credibility, title, created_at
            FROM 来源
            ORDER BY id
            """
        ).fetchall()

        source_counts = connection.execute(
            "SELECT source_type, COUNT(1) AS c FROM 来源 GROUP BY source_type ORDER BY c DESC"
        ).fetchall()

        validations_raw = connection.execute(
            "SELECT fact_key, status, summary, sources_json FROM 验证 ORDER BY id DESC"
        ).fetchall()

        maps = connection.execute(
            "SELECT industry_pack, node, COUNT(1) AS cnt FROM 映射 GROUP BY industry_pack, node ORDER BY cnt DESC"
        ).fetchall()
        evidence_rows = connection.execute(
            """
            SELECT e.fact_id, e.page_or_span, e.quote, d.filename, d.raw_path
            FROM 证据 e
            JOIN 文档 d ON d.id = e.doc_id
            ORDER BY e.id
            """
        ).fetchall()

    validation_latest: dict[str, dict[str, object]] = {}
    for row in validations_raw:
        key = row["fact_key"]
        if key in validation_latest:
            continue
        validation_latest[key] = {
            "status": row["status"],
            "summary": row["summary"],
            "sources_json": row["sources_json"],
        }

    fact_buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in facts:
        fact_buckets[item["fact_key"]].append(
            {
                "fact_value": item["fact_value"],
                "unit": item["unit"] or "未知",
                "time_range": item["time_range"] or "未知",
                "source_name": item["source_name"],
                "source_uri": item["source_uri"],
                "source_type": item["source_type"],
                "region": item["region"],
                "credibility": item["credibility"],
            }
        )

    map_rows = [{"industry_pack": r["industry_pack"], "node": r["node"], "count": r["cnt"]} for r in maps]
    report["facts_by_key"] = {
        k: {
            "hits": len(v),
            "samples": v[:8],
            "validation": validation_latest.get(k, {"status": "待补充", "summary": "未触发交叉验证", "sources_json": "[]"}),
        }
        for k, v in fact_buckets.items()
    }
    report["source_catalog"] = [
        {
            "source_name": source["source_name"],
            "source_type": source["source_type"],
            "source_uri": source["source_uri"],
            "region": source["region"],
            "language": source["language"],
            "credibility": source["credibility"],
            "title": source["title"],
            "source_id": source["id"],
            "documents": [
                {
                    "filename": str(doc["filename"]),
                    "raw_path": str(doc["raw_path"]),
                    "doc_type": doc["doc_type"],
                    "parse_status": doc["parse_status"],
                    "created_at": doc["created_at"],
                }
                for doc in docs_by_source[int(source["id"])]
            ],
        }
        for source in sources
    ]

    report["map_summary"] = map_rows
    report["source_type_distribution"] = {r["source_type"]: r["c"] for r in source_counts}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# 行业研究深度报告（{industry}）",
        "",
        f"- 行业：{industry}",
        f"- 资料库：{root}",
        f"- 处理时间：{report.get('处理时间', '')}",
        "",
        "## 0. 执行摘要（Top-line）",
        f"- 输入项：{report.get('输入项数', 0)}",
        f"- 成功入库文档：{report.get('documents', 0)}",
        f"- 成功提取事实：{report.get('facts', 0)}",
        f"- 已建立行业映射：{report.get('maps', 0)}",
        f"- 交叉验证（通过/待补充/冲突）："
        f"{report.get('validation', {}).get('passed', 0)}/"
        f"{report.get('validation', {}).get('pending', 0)}/"
        f"{report.get('validation', {}).get('conflicted', 0)}",
        "",
        "## 1. 全链路阶段说明",
        "1. 资料检索与候选发现（候选来源/自动检索/用户输入）",
        "2. 下载与附件抓取（含 PDF / 网页正文 / 表格）",
        "3. 原始归档（按行业/区域双轨归档）",
        "4. 解析与结构化（文本、PDF、表格）",
        "5. 事实抽取与行业节点命中",
        "6. 指纹去重与来源/文件去重",
        "7. 多来源交叉验证（同一 fact_key 的数值一致性）",
        "8. 输出报告与审计（含来源溯源与风险项）",
        "",
        "## 2. 阶段指标与质量控制",
        f"- 风险项：{report.get('风险项', 0)}",
        f"- 解析失败项：{report.get('parse_fail', 0)}",
        f"- 重复跳过：{report.get('重复跳过', 0)}",
        "",
        "### 2.1 数据源结构分布",
        "",
    ]

    if report["source_type_distribution"]:
        md_lines.extend(["|来源类型|数量|", "|---|---:|"])
        for k, v in report["source_type_distribution"].items():
            md_lines.append(f"|{k}|{v}|")
    else:
        md_lines.append("- 尚无来源记录")

    md_lines.extend([
        "",
        "## 3. 交叉验证结果（按事实主键）",
        "|事实键|状态|证据条目数|摘要|",
        "|---|---|---:|---|",
    ])
    for fact_key in sorted(fact_buckets.keys()):
        validation = validation_latest.get(fact_key, {"status": "待补充", "summary": "未触发交叉验证", "sources_json": "[]"})
        evidence_count = len(fact_buckets[fact_key])
        md_lines.append(f"|{fact_key}|{validation['status']}|{evidence_count}|{validation['summary']}|")

    md_lines.extend([
        "",
        "## 4. 关键事实详情（含来源与口径）",
        "|事实键|数值|单位|时间|来源|区域|可信度|交叉验证|",
        "|---|---|---|---|---|---|---:|---|",
    ])
    for fact_key, samples in sorted(fact_buckets.items()):
        validation = validation_latest.get(fact_key, {"status": "待补充"})
        for sample in samples[:6]:
            md_lines.append(
                "|{fkey}|{value}|{unit}|{time}|{uri}|{region}|{credibility}|{status}|".format(
                    fkey=fact_key,
                    value=sample["fact_value"],
                    unit=sample["unit"],
                    time=sample["time_range"],
                    uri=sample["source_uri"],
                    region=sample["region"],
                    credibility=sample["credibility"],
                    status=validation["status"],
                )
            )
        if len(samples) > 6:
            md_lines.append(f"- `{fact_key}` 其余 {len(samples) - 6} 条证据已省略。")

    md_lines.extend([
        "",
        "## 5. 行业映射图谱（Taxonomy 命中）",
        "|行业实例|节点|命中计数|",
        "|---|---|---:|",
    ])
    if map_rows:
        for row in map_rows:
            md_lines.append(f"|{row['industry_pack']}|{row['node']}|{row['count']}|")
    else:
        md_lines.append("|-|-|-|")

    md_lines.extend([
        "",
        "## 6. 风险与缺口",
        f"- 无法归档/下载来源数：{report.get('风险项', 0)}",
        f"- 解析失败数：{report.get('parse_fail', 0)}",
        "",
        "## 7. 数据来源与原始素材（报告最后）",
        "|来源|类型|地区|可信度|文件|解析状态|原始链接|",
        "|---|---|---|---:|---|---|---|",
    ])

    for src in report["source_catalog"]:
        if src["documents"]:
            for idx, doc in enumerate(src["documents"]):
                if idx == 0:
                    md_lines.append(
                        f"|{src['source_name']}|{src['source_type']}|{src['region']}|{src['credibility']}|{doc['filename']}|{doc['parse_status']}|{src['source_uri']}|"
                    )
                else:
                    md_lines.append(f"| | | | |{doc['filename']}|{doc['parse_status']}|{src['source_uri']}|")
        else:
            md_lines.append(f"|{src['source_name']}|{src['source_type']}|{src['region']}|{src['credibility']}|无文件|未抓取|{src['source_uri']}|")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    evidence_by_fact: dict[int, sqlite3.Row] = {}
    for evidence in evidence_rows:
        evidence_by_fact.setdefault(int(evidence["fact_id"]), evidence)

    status_map = {"通过": "已验证", "待补充": "单一来源", "冲突": "存在冲突"}
    research_facts: list[dict[str, object]] = []
    for fact in facts:
        key = str(fact["fact_key"])
        lower = key.lower()
        if any(token in key for token in ("市场规模", "CAGR", "增速")):
            module = "市场规模"
        elif any(token in key for token in ("GAA", "DRAM", "NAND", "需求", "用量")):
            module = "需求驱动"
        elif any(token in key for token in ("国产", "中国份额", "替代")):
            module = "中国国产化"
        elif any(token in key for token in ("竞争", "份额", "集中度")):
            module = "竞争格局"
        elif any(token in key for token in ("估值", "收入", "利润", "融资", "并购")):
            module = "可比公司与资本化"
        elif any(token.lower() in lower for token in ("ald", "cvd", "pvd", "high-k", "low-k", "前驱体", "靶材")):
            module = "技术与工艺"
        else:
            module = "定义与边界"
        validation = validation_latest.get(key, {"status": "待补充"})
        evidence = evidence_by_fact.get(int(fact["fact_id"]))
        locator = ""
        if evidence:
            locator = str(evidence["page_or_span"] or evidence["filename"] or "")
        unit = str(fact["unit"] or "")
        research_facts.append(
            {
                "module": module,
                "claim": f"{key}：{fact['fact_value']}{unit}",
                "verification_status": status_map.get(str(validation.get("status")), "证据不足"),
                "source_uri": str(fact["source_uri"] or ""),
                "locator": locator,
            }
        )

    research_sources: list[dict[str, object]] = []
    for source in report["source_catalog"]:
        documents = source.get("documents", [])
        raw_path = documents[0].get("raw_path", "") if documents else ""
        credibility = int(source.get("credibility", 5) or 5)
        research_sources.append(
            {
                "source_id": f"S-{int(source.get('source_id', 0)):04d}",
                "source_name": source.get("source_name", ""),
                "source_type": source.get("source_type", ""),
                "region": source.get("region", ""),
                "rating": "A" if credibility >= 8 else "B" if credibility >= 6 else "C",
                "credibility": credibility,
                "raw_path": raw_path,
                "parse_status": documents[0].get("parse_status", "未抓取") if documents else "未抓取",
                "source_uri": source.get("source_uri", ""),
            }
        )

    curated_path = 技能目录 / "industry-packs" / industry / "curated_facts.json"
    if curated_path.is_file():
        research_facts = 装载策展事实(curated_path, report["source_catalog"], 资料库=root)
    mapping_output: dict[str, list[dict[str, object]]] = {"正式关系": [], "待验证关系": list(map_rows)}
    curated_mapping_path = 技能目录 / "industry-packs" / industry / "curated_mapping.json"
    if curated_mapping_path.is_file():
        pack = 读取行业包(技能目录, industry)
        relation_config = pack.get("relations", {})
        allowed_relations = set(relation_config.get("关系类型", [])) if isinstance(relation_config, dict) else set()
        curated_mapping = 装载策展Mapping(curated_mapping_path, report["source_catalog"], allowed_relations)
        mapping_output = {
            "正式关系": curated_mapping["正式关系"],
            "待验证关系": curated_mapping["待验证关系"] + list(map_rows),
        }
    research_content: dict[str, object] | None = None
    research_content_path = 技能目录 / "industry-packs" / industry / "research_analysis.json"
    if research_content_path.is_file():
        loaded_content = json.loads(research_content_path.read_text(encoding="utf-8"))
        if isinstance(loaded_content, dict):
            research_content = loaded_content
    if research_content:
        try:
            校验研究内容(research_content, facts=research_facts, sources=research_sources, 资料库=root)
        except ValueError:
            # 当前资料库尚未满足正文证据门控时，只输出带状态的证据报告，
            # 禁止静态行业结论脱离本次事实与归档来源进入成品。
            research_content = None
    生成深度研究报告(
        md_path,
        行业=industry,
        资料库=root,
        事实=research_facts,
        来源清单=research_sources,
        映射=mapping_output,
        研究内容=research_content,
    )
    return json_path, md_path


def _run_pipeline(args: argparse.Namespace, skill_root: Path) -> int:
    root = Path(args.资料库).resolve()
    db_path = root / "行业索引.sqlite"
    if not root.exists():
        raise SystemExit(f"[行业研究] 资料库目录不存在: {root}")
    if not db_path.exists():
        raise SystemExit("[行业研究] 索引库不存在，请先运行: python scripts/行业研究.py 初始化")

    行业包 = 读取行业包(skill_root, args.行业)
    entries = _iter_inputs(args, skill_root)
    if not entries:
        raise SystemExit("[行业研究] 未提供可处理输入（请提供 --输入、--来源清单 或 --自动检索）")

    已解析 = 0
    已入库 = 0
    已跳过 = 0
    风险计数 = 0
    失败计数 = 0
    parsed_sources: list[str] = []
    parse_fail_dir = root / "解析文本" / "解析失败"
    seen_sha: set[str] = set()

    for entry in entries:
        entry_meta = dict(entry)
        entry_meta.setdefault("download_dir", str(root / "原始资料" / "用户导入"))
        files = _collect_files(entry_meta, Path(entry_meta["download_dir"]))
        if not files:
            风险计数 += 1
            continue

        for raw_file, source_meta in files:
            if not raw_file.exists():
                风险计数 += 1
                continue

            region = _safe_region(source_meta.get("region", args.region))
            try:
                archived = 归档原始文件(
                    root,
                    raw_file,
                    args.行业,
                    region,
                    str(source_meta.get("source_name") or args.行业),
                    str(source_meta.get("source_uri")),
                )
            except Exception:
                风险计数 += 1
                continue

            file_sha = 文件sha256(archived.read_bytes())
            if file_sha in seen_sha or 查找同文件指纹(db_path, file_sha):
                已跳过 += 1
                continue
            seen_sha.add(file_sha)

            try:
                text, status, doc_type = _extract_text(archived, parse_fail_dir, args.ignore_parse_fail)
            except Exception:
                失败计数 += 1
                status = "failed"
                doc_type = "text"
                text = ""

            source_id = 写入来源(
                库路径=db_path,
                source_key=_build_source_key(args.行业, str(source_meta.get("source_name") or args.行业), str(source_meta.get("source_uri"))),
                source_name=str(source_meta.get("source_name") or args.行业),
                source_type=str(source_meta.get("source_type") or "未知"),
                source_uri=str(source_meta.get("source_uri")),
                region=region,
                source_country="CN" if region == "中国" else ("GLOBAL" if region == "全球" else None),
                language=str(source_meta.get("language") or "zh"),
                credibility=_resolve_credibility(source_meta),
                title=str(source_meta.get("title") or raw_file.name),
            )

            指纹 = 生成指纹(text) if text else None
            文档_id = 写入文档(
                库路径=db_path,
                source_id=source_id,
                doc_type=doc_type,
                raw_path=archived,
                filename=archived.name,
                file_sha256=file_sha,
                simhash_64=指纹.语义sha if 指纹 else "",
                parse_status=status,
                content_sha256=指纹.原文sha if 指纹 else None,
                extra={"source_name": source_meta.get("source_name"), "source_uri": source_meta.get("source_uri"), "source_type": source_meta.get("source_type")},
            )

            if status != "success":
                continue

            已解析 += 1
            _write_text_dump(root, 文档_id, archived, text)
            已入库 += 1
            parsed_sources.append(f"{source_meta.get('source_name')} | {source_meta.get('source_uri')}")

            facts = 提取事实候选(text, args.行业, 行业包)
            for fact in facts:
                fact_id = 写入事实(
                    db_path,
                    source_id=source_id,
                    fact_key=fact["fact_key"],
                    fact_type=fact.get("fact_type", "extracted_numeric"),
                    fact_value=fact.get("fact_value", ""),
                    unit=fact.get("unit"),
                    time_range=fact.get("time_range"),
                )
                写入证据(db_path, fact_id=fact_id, doc_id=文档_id, quote=fact.get("quote", ""), confidence=_resolve_credibility(source_meta))

            命中节点 = set(提取行业命中节点(text, 行业包))
            for node in 命中节点:
                fact_id = 写入事实(
                    db_path,
                    source_id=source_id,
                    fact_key=f"industry:{args.行业}:{node}",
                    fact_type="keyword_match",
                    fact_value="命中",
                )
                写入映射(
                    db_path,
                    fact_id=fact_id,
                    industry_pack=args.行业,
                    node=node,
                    relation="contains_keyword",
                    confidence=_resolve_credibility(source_meta),
                )

    validation = 执行全量交叉验证(db_path) if not args.skip_validation else {"total": 0, "passed": 0, "pending": 0, "conflicted": 0}
    counts = 统计来源数(db_path)
    validation_status = 统计验证结果(db_path)
    # 统计映射关系（可复用到行业图谱）
    try:
        import sqlite3

        with sqlite3.connect(db_path) as _connection:
            map_count = _connection.execute("SELECT COUNT(1) FROM 映射").fetchone()[0]
    except Exception:
        map_count = 0

    report = {
        "行业": args.行业,
        "资料库": str(root),
        "处理时间": datetime.now().isoformat(timespec="seconds"),
        "输入项数": len(entries),
        "documents": 已入库,
        "facts": counts.get("facts", 0),
        "maps": map_count,
        "重复跳过": 已跳过,
        "风险项": 风险计数,
        "parse_fail": 失败计数,
        "validation": validation_status,
        "sources": sorted(set(parsed_sources)),
        "count": counts,
    }
    json_report, md_report = _build_run_report(root, db_path, report, args.行业)

    写入运行记录(
        db_path,
        "run",
        "行业研究.py 运行",
        "ok",
        f"输入={len(entries)} 已解析={已解析} 入库={已入库} 跳过={已跳过} 风险={风险计数}",
    )
    print(f"[行业研究] 运行报告: {json_report}")
    print(f"[行业研究] 研究快报: {md_report}")
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    root = Path(args.资料库).resolve()
    db_path = root / "行业索引.sqlite"
    if not root.exists():
        raise SystemExit(f"[行业研究] 资料库不存在: {root}")
    if not db_path.exists():
        raise SystemExit(f"[行业研究] 索引库缺失: {db_path}")

    counts = 统计来源数(db_path)
    required_dirs = [
        "配置",
        "原始资料/中国",
        "原始资料/全球",
        "原始资料/用户导入",
        "原始资料/受限来源元数据",
        "解析文本/正文",
        "解析文本/表格",
        "解析文本/解析失败",
        "来源目录",
        "结构化事实",
        "验证与冲突",
        "行业图谱",
        "研究报告",
        "运行记录",
    ]
    missing = [d for d in required_dirs if not (root / d).exists()]
    print(json.dumps({"资料库": str(root), "缺失目录": missing, "计数": counts}, ensure_ascii=False, indent=2))
    return 0


def _run_report(args: argparse.Namespace) -> int:
    root = Path(args.资料库).resolve()
    db_path = root / "行业索引.sqlite"
    if not root.exists():
        raise SystemExit(f"[行业研究] 资料库不存在: {root}")
    if not db_path.exists():
        raise SystemExit(f"[行业研究] 索引库缺失: {db_path}")

    report_files = sorted((root / "研究报告").glob("run_*.json"))
    if not report_files:
        raise SystemExit("[行业研究] 未找到可读报告")
    latest = report_files[-1]
    report = json.loads(latest.read_text(encoding="utf-8"))
    industry = str(report.get("行业") or "")
    if not industry:
        config_path = root / "配置" / "行业配置.json"
        industry = str(json.loads(config_path.read_text(encoding="utf-8")).get("行业") or "未知行业")
    json_report, md_report = _build_run_report(root, db_path, report, industry)
    print(f"[行业研究] 重建报告: {md_report}")
    print(f"[行业研究] 重建数据: {json_report}")
    if args.出版PDF:
        output_dir = Path(args.输出目录).resolve() if args.输出目录 else root / "研究报告"
        command = [
            sys.executable,
            str(技能目录 / "scripts" / "生成出版报告.py"),
            "--资料库",
            str(root),
            "--行业",
            industry,
            "--输出目录",
            str(output_dir),
            "--生成PDF",
        ]
        subprocess.run(command, check=True)
    return 0


# 成品报告格式 -> 文件后缀/模式
def _抓取_网页源(
    主题: str,
    来源: str,
    max_results: int = 10,
    时间范围: str = "past 12 months",
) -> list[dict]:
    """多数据源对外检索现成研报/报告。

    数据源：bing（可靠 HTML 搜索）、duckduckgo（回退）、yixin OpenAPI（需密钥，report/announcement）。
    任一源失败不阻塞整体；返回统一结构的候选清单。
    """

    候选: list[dict] = []
    seen: set[str] = set()
    来源列表 = [item.strip() for item in 来源.split(",") if item.strip()]
    if "all" in 来源列表:
        来源列表 = ["bing", "duckduckgo", "yixin"]

    def _add(title: str, link: str, source_name: str, source_type: str, region: str, published: str | None) -> None:
        key = link or title
        if key in seen:
            return
        seen.add(key)
        候选.append(
            {
                "标题": title,
                "链接": link,
                "来源": source_name,
                "类型": source_type,
                "地区": region,
                "发布日期": published,
            }
        )

    # 1) Bing 网页源（国内可达，可靠）
    if "bing" in 来源列表:
        try:
            for href, title, snippet in 搜索Bing源(主题, max_results=max_results):
                source_name = "Bing搜索"
                region = "中国" if any("\u4e00" <= ch <= "\u9fff" for ch in title) else "全球"
                _add(title, href, source_name, "网页", region, None)
        except Exception as exc:
            print(f"[行业研究] Bing 源失败（跳过）: {exc}")

    # 2) DuckDuckGo 网页源（回退，可能被反爬）
    if "duckduckgo" in 来源列表:
        try:
            for href, title, snippet in 搜索网页源(主题, max_results=max_results):
                source_name = "DuckDuckGo搜索"
                region = "中国" if any("\u4e00" <= ch <= "\u9fff" for ch in title) else "全球"
                _add(title, href, source_name, "网页", region, None)
        except Exception as exc:
            print(f"[行业研究] DuckDuckGo 源失败（跳过）: {exc}")

    # 3) yixin OpenAPI（需密钥，报告/公告/学术）
    if "yixin" in 来源列表:
        try:
            adapter = Yixin适配器(查询上限=3, 每类结果数=max_results, timeout=15)
            for item in adapter.检索({"行业": 主题, "查询词": [主题], "时间范围": 时间范围}):
                region = item.地区 or ("中国" if any("\u4e00" <= ch <= "\u9fff" for ch in item.标题) else "全球")
                _add(item.标题, item.原始链接, item.来源名称, item.来源类型, region, item.发布日期)
        except Exception as exc:
            print(f"[行业研究] yixin 源失败（跳过）: {exc}")

    return 候选[:max_results]


def _run_fetch(args: argparse.Namespace) -> int:
    主题 = args.主题.strip()
    if not 主题:
        raise SystemExit("[行业研究] --主题 不能为空")

    hits = _抓取_网页源(主题, args.来源, max_results=args.数量, 时间范围=args.时间范围)

    if not hits:
        raise SystemExit(f"[行业研究] 主题「{主题}」未检索到现成报告；请确认网络/密钥，或换一个主题词")

    output_dir = Path(args.输出目录).resolve() if str(args.输出目录) not in (".", "") else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 下载附件（PDF/HTML 等），除非 --仅列表；yixin:// 元数据链接无直接附件，跳过
    if not args.仅列表:
        for item in hits:
            link = item["链接"]
            if not link or not link.lower().startswith(("http://", "https://")):
                continue
            if not (link.lower().endswith(".pdf") or link.lower().endswith(".html") or link.lower().endswith(".htm")):
                continue
            try:
                item["附件"] = str(_download(link, output_dir))
            except Exception as exc:
                item["附件错误"] = str(exc)

    if args.json:
        print(json.dumps({"主题": 主题, "来源": args.来源, "结果": hits}, ensure_ascii=False, indent=2))
    else:
        print(f"[行业研究] 主题「{主题}」现成报告清单（{len(hits)} 条）:")
        for index, item in enumerate(hits, start=1):
            marker = "📄" if item.get("附件") else ("  " if item["链接"] else "🔒")
            date = f" [{item['发布日期']}]" if item.get("发布日期") else ""
            print(f"  {index}. {marker} [{item['类型']}] {item['标题'][:70]}{date}")
            print(f"     来源: {item['来源']} | {item['链接'][:80]}")
            if item.get("附件"):
                print(f"     已下载: {item['附件']}")
        if not args.仅列表:
            print(f"[行业研究] 附件已下载到: {output_dir}")
        else:
            print("[行业研究] --仅列表 模式，未下载附件")
    return 0


def _run_status() -> int:
    from yy_industry_research.配置 import 版本

    print("技能名: yy-Industry-R-Skill")
    print(f"版本: {版本}")
    print(f"根目录: {_resolve_workspace()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    skill_root = _resolve_workspace()

    if args.command == "初始化":
        return _run_init(args)
    if args.command == "计划":
        return _run_plan(args, skill_root)
    if args.command == "运行":
        return _run_pipeline(args, skill_root)
    if args.command == "验收":
        return _run_verify(args)
    if args.command == "报告":
        return _run_report(args)
    if args.command == "抓取":
        return _run_fetch(args)
    if args.command == "状态":
        return _run_status()
    raise SystemExit("[行业研究] 未知命令")


if __name__ == "__main__":
    raise SystemExit(main())
