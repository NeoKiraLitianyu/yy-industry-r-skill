#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


技能目录 = Path(__file__).resolve().parents[1]
if str(技能目录) not in sys.path:
    sys.path.insert(0, str(技能目录))

from yy_industry_research.HTML import 生成出版HTML
from yy_industry_research.PDF import 生成PDF, 验收PDF
from yy_industry_research.出版 import 构建出版模型
from yy_industry_research.图表 import 渲染图表_svg
from yy_industry_research.报告 import 生成深度研究报告
from yy_industry_research.策展事实 import 装载策展Mapping, 装载策展事实
from yy_industry_research.行业包 import 读取行业包


def _读取最新运行资料(资料库: Path) -> dict[str, Any]:
    candidates = sorted((资料库 / "研究报告").glob("run_*.json"))
    if not candidates:
        raise FileNotFoundError("资料库中没有 run_*.json；请先执行行业研究管道")
    data = json.loads(candidates[-1].read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("最新运行资料不是 JSON 对象")
    data["_run_file"] = str(candidates[-1])
    return data


def _规范来源(source_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, source in enumerate(source_catalog, start=1):
        documents = [item for item in source.get("documents", []) if isinstance(item, dict)]
        document = next((item for item in documents if str(item.get("raw_path") or "") and Path(str(item["raw_path"])).is_file()), documents[0] if documents else {})
        credibility = int(source.get("credibility") or 5)
        result.append(
            {
                "source_id": str(source.get("source_id") or f"S-{index:04d}"),
                "source_name": str(source.get("source_name") or "未知来源"),
                "source_type": str(source.get("source_type") or "未知类型"),
                "region": str(source.get("region") or "未知地区"),
                "language": str(source.get("language") or "未知"),
                "credibility": credibility,
                "rating": "A" if credibility >= 8 else "B" if credibility >= 6 else "C",
                "raw_path": str(document.get("raw_path") or ""),
                "parse_status": str(document.get("parse_status") or "未解析"),
                "source_uri": str(source.get("source_uri") or ""),
            }
        )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def 生成完整出版物(
    *,
    资料库: str | Path,
    行业: str,
    输出目录: str | Path,
    生成_pdf: bool = False,
    浏览器: str | Path | None = None,
) -> dict[str, Any]:
    library = Path(资料库).resolve()
    output = Path(输出目录).resolve()
    if not library.is_dir():
        raise FileNotFoundError(f"资料库不存在：{library}")
    output.mkdir(parents=True, exist_ok=True)
    pack_dir = 技能目录 / "industry-packs" / 行业
    required = ["curated_facts.json", "curated_mapping.json", "research_analysis.json", "charts.json"]
    missing = [name for name in required if not (pack_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("行业包缺少出版文件：" + "、".join(missing))

    run = _读取最新运行资料(library)
    catalog = list(run.get("source_catalog") or [])
    if not catalog:
        raise ValueError("最新运行资料缺少 source_catalog")
    sources = _规范来源(catalog)
    facts = 装载策展事实(pack_dir / "curated_facts.json", catalog, 资料库=library)
    content = json.loads((pack_dir / "research_analysis.json").read_text(encoding="utf-8"))
    chart_specs = json.loads((pack_dir / "charts.json").read_text(encoding="utf-8"))["charts"]
    industry_pack = 读取行业包(技能目录, 行业)
    relation_config = industry_pack.get("relations") or {}
    allowed = set(relation_config.get("关系类型") or []) if isinstance(relation_config, dict) else set()
    mappings = 装载策展Mapping(pack_dir / "curated_mapping.json", catalog, allowed)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{行业}_行业深度研究_{timestamp}"
    md_path = output / f"{base}.md"
    html_path = output / f"{base}.html"
    pdf_path = output / f"{base}.pdf"
    charts_path = output / f"{base}.charts.json"
    evidence_path = output / f"{base}.evidence.json"
    receipt_path = output / f"{base}.receipt.json"
    chart_dir = output / f"{base}_charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    生成深度研究报告(
        md_path,
        行业=行业,
        资料库=library,
        事实=facts,
        来源清单=sources,
        映射=mappings,
        研究内容=content,
    )
    publication = 构建出版模型(
        markdown=md_path.read_text(encoding="utf-8"),
        content=content,
        facts=facts,
        sources=sources,
        mappings=mappings,
        chart_specs=chart_specs,
        资料库=library,
    )
    生成出版HTML(html_path, publication)

    rendered_charts = []
    for spec in publication["charts"]:
        svg_path = chart_dir / f"{spec['id']}.svg"
        svg_path.write_text(渲染图表_svg(spec, publication["fact_index"]), encoding="utf-8")
        rendered_charts.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "type": spec["type"],
                "fact_ids": spec.get("fact_ids", []),
                "fact_scope": spec.get("fact_scope"),
                "svg": str(svg_path),
                "sha256": _sha256(svg_path),
            }
        )
    charts_path.write_text(json.dumps({"charts": rendered_charts}, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence_path.write_text(
        json.dumps(
            {
                "industry": 行业,
                "as_of": content.get("as_of"),
                "facts": facts,
                "mappings": publication["mappings"],
                "sources": sources,
                "source_run": run.get("_run_file"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if 生成_pdf:
        生成PDF(html_path, pdf_path, browser=浏览器)
        pdf_receipt = 验收PDF(
            pdf_path,
            ["半导体膜材", "行业 Mapping 与投资机会地图", "数据来源、原始素材与引用清单"],
            min_pages=20,
        )
        if not pdf_receipt["valid"]:
            raise RuntimeError("PDF 验收未通过：" + json.dumps(pdf_receipt, ensure_ascii=False))
    else:
        pdf_receipt = {"valid": False, "generated": False, "pages": 0, "size": 0, "missing_text": []}

    artifacts = [md_path, html_path, charts_path, evidence_path]
    if 生成_pdf:
        artifacts.append(pdf_path)
    receipt = {
        "industry": 行业,
        "as_of": content.get("as_of"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "library": str(library),
        "source_run": run.get("_run_file"),
        "facts": len(facts),
        "verified_facts": sum(1 for item in facts if item.get("verification_status") == "已验证"),
        "single_source_facts": sum(1 for item in facts if item.get("verification_status") == "单一来源"),
        "sources": len(sources),
        "charts": len(rendered_charts),
        "formal_mappings": len(publication["mappings"]["正式关系"]),
        "pending_mappings": len(publication["mappings"]["待验证关系"]),
        "pdf": pdf_receipt,
        "artifacts": {str(path): {"size": path.stat().st_size, "sha256": _sha256(path)} for path in artifacts},
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成全中文紫色行业研究 HTML/PDF 出版物")
    parser.add_argument("--资料库", required=True)
    parser.add_argument("--行业", required=True)
    parser.add_argument("--输出目录", required=True)
    parser.add_argument("--生成PDF", action="store_true")
    parser.add_argument("--浏览器", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = 生成完整出版物(
        资料库=args.资料库,
        行业=args.行业,
        输出目录=args.输出目录,
        生成_pdf=args.生成PDF,
        浏览器=args.浏览器,
    )
    print(json.dumps({"receipt": receipt["receipt_path"], "pdf": receipt["pdf"], "charts": receipt["charts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
