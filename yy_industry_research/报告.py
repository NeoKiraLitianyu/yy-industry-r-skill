from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .深度研究 import 生成研究框架, 检查研究覆盖
from .策展事实 import 门控Mapping


_章节 = (
    ("定义与边界", "行业定义、口径与研究边界"),
    ("技术与工艺", "技术路线、材料体系与工艺窗口"),
    ("需求驱动", "下游需求、制程演进与单位用量"),
    ("市场规模", "全球与中国市场规模、增速及双法测算"),
    ("供应链与利润池", "产业链、供应安全、认证壁垒与利润池"),
    ("竞争格局", "全球竞争格局、厂商定位与份额演变"),
    ("中国国产化", "中国供需、国产化率、卡点与替代路径"),
    ("可比公司与资本化", "可比公司、财务质量、估值与资本事件"),
    ("一级市场投资判断", "投资地图、控制点、里程碑与退出路径"),
)
_必需正文模块 = tuple(module for module, _ in _章节)
_事实引用模式 = re.compile(r"\[(F-\d+)\]")


def _escape(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def _事实行(fact: dict[str, Any]) -> str:
    status = _escape(fact.get("verification_status") or "证据不足")
    claim = _escape(fact.get("claim") or fact.get("事实") or "")
    locator = _escape(fact.get("locator") or "未定位")
    uris = fact.get("source_uris") or [fact.get("source_uri") or "未提供"]
    uri = "；".join(_escape(item) for item in uris)
    note = _escape(fact.get("verification_note") or "")
    suffix = f"；验证说明：{note}" if note else ""
    return f"- [{status}] {claim}（定位：{locator}；来源：{uri}{suffix}）"


def _表格行(values: Iterable[Any]) -> str:
    return "|" + "|".join(_escape(value) for value in values) + "|"


def _遍历文本(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _遍历文本(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _遍历文本(item)


def _显式事实编号(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        fact_ids = value.get("fact_ids") or value.get("事实编号") or []
        if isinstance(fact_ids, list):
            ids.update(str(item) for item in fact_ids if str(item).strip())
        for item in value.values():
            ids.update(_显式事实编号(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            ids.update(_显式事实编号(item))
    return ids


def _校验出版章节(content: dict[str, Any]) -> set[str]:
    publication_sections = content.get("出版章节") or []
    if not publication_sections:
        return set()
    if not isinstance(publication_sections, list):
        raise ValueError("出版章节必须为列表")
    if len(publication_sections) != 22:
        raise ValueError("出版层必须恰好提供22个章节")

    allowed_modules = set(_必需正文模块) | {"情景分析", "风险与反证", "数据来源与原始素材"}
    explicit_refs: set[str] = set()
    seen_ids: set[str] = set()
    for index, section in enumerate(publication_sections, start=1):
        if not isinstance(section, dict):
            raise ValueError("出版章节必须是对象")
        expected_id = f"P-{index:02d}"
        section_id = str(section.get("id") or "").strip()
        if section_id != expected_id:
            raise ValueError(f"出版章节ID必须连续编号：期望{expected_id}，得到{section_id or '空'}")
        if section_id in seen_ids:
            raise ValueError(f"出版章节ID重复：{section_id}")
        seen_ids.add(section_id)

        missing_fields = [
            field
            for field in (
                "id",
                "title",
                "module",
                "thesis",
                "paragraphs",
                "fact_ids",
                "tables",
                "investment_implications",
                "uncertainties",
            )
            if field not in section
        ]
        if missing_fields:
            raise ValueError(f"出版章节缺少字段：{section_id} {'、'.join(missing_fields)}")

        module = str(section.get("module") or "")
        if module not in allowed_modules:
            raise ValueError(f"出版章节模块不属于九模块或允许的附录模块：{section_id} {module}")

        paragraphs = section.get("paragraphs") or []
        if (
            not isinstance(paragraphs, list)
            or len(paragraphs) < 2
            or not all(isinstance(item, str) and item.strip() for item in paragraphs)
        ):
            raise ValueError(f"出版章节每章至少需要两段正文：{section_id}")

        fact_ids = section.get("fact_ids") or []
        if not isinstance(fact_ids, list):
            raise ValueError(f"出版章节fact_ids必须为列表：{section_id}")
        fact_id_set = {str(item) for item in fact_ids if str(item).strip()}
        if section_id != "P-22" and not fact_id_set:
            raise ValueError(f"非来源附录出版章节必须绑定事实编号：{section_id}")

        text_refs = {
            match
            for text in _遍历文本(
                {
                    "thesis": section.get("thesis"),
                    "paragraphs": section.get("paragraphs"),
                    "tables": section.get("tables"),
                    "investment_implications": section.get("investment_implications"),
                    "uncertainties": section.get("uncertainties"),
                }
            )
            for match in _事实引用模式.findall(text)
        }
        undeclared = sorted(text_refs - fact_id_set)
        if undeclared:
            raise ValueError(f"出版章节正文引用了未在fact_ids声明的事实：{section_id} {'、'.join(undeclared)}")
        if section_id != "P-22" and not text_refs:
            raise ValueError(f"非来源附录出版章节正文必须就近引用事实：{section_id}")

        tables = section.get("tables") or []
        if not isinstance(tables, list):
            raise ValueError(f"出版章节tables必须为列表：{section_id}")
        for table in tables:
            if not isinstance(table, dict):
                raise ValueError(f"出版章节表格必须是对象：{section_id}")
            columns = table.get("columns") or table.get("列") or []
            rows = table.get("rows") or table.get("行") or []
            if not isinstance(columns, list) or not isinstance(rows, list):
                raise ValueError(f"出版章节表格列与行必须为列表：{section_id}")
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) != len(columns):
                    raise ValueError(f"出版章节表格行列数不一致：{section_id}")

        explicit_refs.update(fact_id_set)
    return explicit_refs


def 校验研究内容(
    content: dict[str, Any],
    *,
    facts: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    资料库: str | Path,
) -> None:
    version = str(content.get("version") or "")
    if not re.fullmatch(r"1\.\d+\.\d+", version):
        raise ValueError("研究内容包版本缺失或与1.x渲染器不兼容")
    if not str(content.get("as_of") or "").strip():
        raise ValueError("研究内容包缺少数据时点as_of")

    sections = content.get("章节") or content.get("sections") or []
    if not isinstance(sections, list):
        raise ValueError("研究内容包章节必须为列表")
    modules = [str(section.get("module") or "") for section in sections if isinstance(section, dict)]
    if tuple(modules) != _必需正文模块:
        raise ValueError("研究内容包必须按固定顺序完整提供九个必需模块，且不得重复")

    executive = content.get("执行摘要") or content.get("executive_summary") or {}
    executive_basis = str(executive.get("依据") or executive.get("evidence") or "").strip()
    if not executive_basis or not _事实引用模式.search(executive_basis):
        raise ValueError("执行摘要必须引用至少一条已归档事实，不能只使用内部模型标记")

    for section in sections:
        paragraphs = section.get("正文") or section.get("paragraphs") or []
        if (
            not isinstance(paragraphs, list)
            or not paragraphs
            or not all(isinstance(item, str) and item.strip() for item in paragraphs)
        ):
            raise ValueError(f"研究章节正文必须是非空字符串列表：{section.get('module')}")
        section_basis = str(section.get("依据") or section.get("evidence") or "").strip()
        if not section_basis or not _事实引用模式.search(section_basis):
            raise ValueError(f"研究章节必须引用至少一条已归档事实，不能只使用内部模型标记：{section.get('module')}")
        for table in section.get("表格") or section.get("tables") or []:
            if not isinstance(table, dict):
                raise ValueError("研究章节表格必须是对象")
            columns = table.get("列") or table.get("columns") or []
            rows = table.get("行") or table.get("rows") or []
            if not isinstance(columns, list) or not columns:
                raise ValueError("研究章节表格缺少列定义")
            if not isinstance(rows, list):
                raise ValueError("研究章节表格行必须是列表")
            table_basis = str(table.get("依据") or table.get("evidence") or "").strip()
            if not table_basis or not (_事实引用模式.search(table_basis) or "内部模型假设" in table_basis):
                raise ValueError(f"研究表格缺少事实引用或内部模型标记：{table.get('标题') or table.get('title') or '未命名表格'}")
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) != len(columns):
                    raise ValueError(f"表格行列数不一致：{table.get('标题') or table.get('title') or '未命名表格'}")

    explicit_refs = _校验出版章节(content)
    referenced = {
        match
        for text in _遍历文本(content)
        for match in _事实引用模式.findall(text)
    } | explicit_refs
    fact_by_id = {str(fact.get("fact_id") or ""): fact for fact in facts if fact.get("fact_id")}
    missing = sorted(referenced - set(fact_by_id))
    if missing:
        raise ValueError(f"研究内容包包含不存在的事实引用：{'、'.join(missing)}")

    invalid = sorted(
        fact_id
        for fact_id in referenced
        if str(fact_by_id[fact_id].get("verification_status") or "")
        not in {"已验证", "单一来源"}
    )
    if invalid:
        raise ValueError(f"研究内容包引用了证据不足或冲突事实：{'、'.join(invalid)}")

    source_by_uri: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in sources:
        uri = str(source.get("source_uri") or "")
        if not uri:
            continue
        source_by_uri[uri].append(source)
        for document in source.get("documents", []) or []:
            if isinstance(document, dict):
                expanded = dict(source)
                expanded.update(document)
                source_by_uri[uri].append(expanded)
    library_root = Path(资料库).resolve()
    no_archive: list[str] = []
    outside_archive: list[str] = []
    for fact_id in sorted(referenced):
        fact = fact_by_id[fact_id]
        uris = fact.get("source_uris") or [fact.get("source_uri")]
        missing_uris: list[str] = []
        for uri in uris:
            records = source_by_uri.get(str(uri or ""), [])
            archived = False
            for source in records:
                raw_path = str(source.get("raw_path") or "")
                if not raw_path or not Path(raw_path).is_file():
                    continue
                resolved_raw = Path(raw_path).resolve()
                if resolved_raw.is_relative_to(library_root):
                    archived = True
                    break
                outside_archive.append(f"{fact_id}:{uri}")
            if not archived:
                missing_uris.append(str(uri or ""))
        if missing_uris:
            no_archive.append(fact_id)
    if outside_archive:
        raise ValueError(f"研究内容包引用原文不属于本次资料库归档目录：{'、'.join(sorted(set(outside_archive)))}")
    if no_archive:
        raise ValueError(f"研究内容包引用事实没有可访问的归档原文：{'、'.join(no_archive)}")


def _渲染研究章节(
    lines: list[str],
    *,
    index: int,
    section: dict[str, Any],
) -> None:
    title = _escape(section.get("title") or section.get("标题") or section.get("module") or "未命名章节")
    lines.extend(["", f"## {index}. {title}", ""])

    thesis = _escape(section.get("核心判断") or section.get("thesis") or "")
    if thesis:
        lines.extend([f"> **本章判断：** {thesis}", ""])
    basis = _escape(section.get("依据") or section.get("evidence") or "")
    if not basis and isinstance(section.get("fact_ids"), list):
        basis = _escape("".join(f"[{fact_id}]" for fact_id in section.get("fact_ids") or []))
    if basis:
        lines.extend([f"> **本章证据依据：** {basis}", ""])

    paragraphs = section.get("正文") or section.get("paragraphs") or []
    for paragraph in paragraphs:
        value = str(paragraph).strip()
        if value:
            lines.extend([value, ""])

    for table in section.get("表格") or section.get("tables") or []:
        table_title = _escape(table.get("标题") or table.get("title") or "分析表")
        columns = list(table.get("列") or table.get("columns") or [])
        rows = list(table.get("行") or table.get("rows") or [])
        lines.extend([f"### {table_title}", ""])
        if columns:
            lines.append(_表格行(columns))
            lines.append(_表格行(["---"] * len(columns)))
            for row in rows:
                lines.append(_表格行(row))
        else:
            lines.append("- 本表尚无有效列定义。")
        table_basis = _escape(table.get("依据") or table.get("evidence") or "")
        if table_basis:
            lines.extend(["", f"> 表格依据：{table_basis}"])
        lines.append("")

    implications = section.get("投资含义") or section.get("investment_implications") or []
    if implications:
        lines.extend(["### 一级市场投资含义", ""])
        lines.extend(f"- {_escape(item)}" for item in implications)
        lines.append("")

    uncertainties = section.get("不确定性") or section.get("uncertainties") or []
    if uncertainties:
        lines.extend(["### 证据边界与待验证项", ""])
        lines.extend(f"- {_escape(item)}" for item in uncertainties)
        lines.append("")


def 生成深度研究报告(
    输出路径: str | Path,
    *,
    行业: str,
    资料库: str | Path,
    事实: Iterable[dict[str, Any]],
    来源清单: Iterable[dict[str, Any]],
    映射: dict[str, list[dict[str, Any]]],
    研究内容: dict[str, Any] | None = None,
) -> Path:
    facts = list(事实)
    sources = list(来源清单)
    content = 研究内容 or {}
    if content:
        校验研究内容(content, facts=facts, sources=sources, 资料库=资料库)
    framework = 生成研究框架(行业)
    coverage = 检查研究覆盖(framework, facts, sources)
    by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        by_module[str(fact.get("module") or "未分类")].append(fact)

    verified = sum(1 for item in facts if item.get("verification_status") == "已验证")
    conflicted = sum(1 for item in facts if item.get("verification_status") in {"存在冲突", "冲突"})
    single = sum(1 for item in facts if item.get("verification_status") == "单一来源")
    investment_facts = [item for item in facts if item.get("module") == "一级市场投资判断"]
    risk_facts = [item for item in facts if item.get("module") == "风险与反证"]
    executive = content.get("执行摘要") or content.get("executive_summary") or {}
    lines = [
        f"# {行业}行业深度研究与一级市场投资报告",
        "",
        f"> 生成时间：{datetime.now().isoformat(timespec='seconds')}  ",
        f"> 资料库：{Path(资料库).resolve()}  ",
        "> 规则：硬数据必须可定位；单一来源与冲突数据不写成确定性结论。",
        "",
        "## 执行摘要与投资结论" if content else "## 投资结论仪表盘",
        "",
        f"- 证据事实：{len(facts)} 项；已验证 {verified} 项；单一来源 {single} 项；冲突 {conflicted} 项。",
        f"- 研究覆盖：{len(framework.模块) - len(coverage.未达标模块)}/{len(framework.模块)} 个模块达到最低证据覆盖。",
        f"- 未达标模块：{'、'.join(coverage.未达标模块) if coverage.未达标模块 else '无'}。",
        "- 投资动作：由已验证事实支持时给出；当前证据不足的模块保留为尽调条件，不以叙事补齐。",
    ]
    if content:
        lines[5:5] = [
            f"> 内容包版本：{_escape(content.get('version'))}  ",
            f"> 数据时点：{_escape(content.get('as_of'))}  ",
        ]
    rating = _escape(executive.get("投资评级") or executive.get("rating") or "")
    conclusion = _escape(executive.get("核心结论") or executive.get("conclusion") or "")
    if rating:
        lines.append(f"- 投资评级：{rating}")
    if conclusion:
        lines.extend(["", f"**核心结论：** {conclusion}"])
    executive_basis = _escape(executive.get("依据") or executive.get("evidence") or "")
    if executive_basis:
        lines.extend(["", f"> **执行摘要证据依据：** {executive_basis}"])
    judgments = executive.get("关键判断") or executive.get("key_judgments") or []
    if judgments:
        lines.extend(["", "### 关键判断", ""])
        lines.extend(f"- {_escape(item)}" for item in judgments)
    else:
        for item in investment_facts[:3]:
            lines.append(f"- 核心投资判断：{_escape(item.get('claim'))}")
    conditions = executive.get("投资条件") or executive.get("investment_conditions") or []
    if conditions:
        lines.extend(["", "### 投资成立条件", ""])
        lines.extend(f"- {_escape(item)}" for item in conditions)
    disconfirmations = executive.get("否证条件") or executive.get("disconfirmations") or []
    if disconfirmations:
        lines.extend(["", "### 核心否证条件", ""])
        lines.extend(f"- {_escape(item)}" for item in disconfirmations)
    else:
        for item in risk_facts[:2]:
            lines.append(f"- 核心否证条件：{_escape(item.get('claim'))}")
    lines.extend([
        "",
        "## 研究范围、方法与口径",
        "",
        "- 研究链路：多源检索 → 原始归档 → 指纹去重 → 解析 → 事实结构化 → 来源评级 → 独立来源验证 → 行业 Mapping → 投资研究。",
        "- 数据优先级：政府/监管/标准/公司原文 → 协会/学术 → 券商/咨询 → 行业媒体；MCP 是发现与问数通道，不替代原始证据。",
        "- 市场规模：必须同时保留自上而下与自下而上口径，差异超过 30% 时列入冲突与敏感性分析。",
        "- 时间窗口：关键数据优先最近 12 个月，主检索覆盖最近 24 个月，历史文献仅作技术基础与周期对照。",
    ])

    research_sections = list(content.get("出版章节") or content.get("章节") or content.get("sections") or [])
    if research_sections:
        for idx, section in enumerate(research_sections, start=1):
            _渲染研究章节(lines, index=idx, section=section)
        next_index = len(research_sections) + 1
    else:
        for idx, (module, title) in enumerate(_章节, start=1):
            lines.extend(["", f"## {idx}. {title}", ""])
            if by_module.get(module):
                lines.extend(_事实行(item) for item in by_module[module])
            else:
                lines.append("- [证据不足] 当前资料库尚无达到定位要求的正式事实，本节进入研究缺口清单。")
            module_questions = [f"{行业}：{q}" for q in __import__("yy_industry_research.深度研究", fromlist=["_问题模板"])._问题模板[module]]
            lines.extend(["", "本节待回答问题："])
            lines.extend(f"- {question}" for question in module_questions)
        next_index = len(_章节) + 1

    lines.extend(["", f"## {next_index}. 行业 Mapping 与投资机会地图", ""])
    gated_mapping = 门控Mapping(
        映射,
        sources,
        资料库=资料库,
        允许事实编号={
            str(item.get("fact_id"))
            for item in facts
            if item.get("fact_id") and item.get("verification_status") == "已验证"
        },
        事实目录=facts,
    )
    formal = gated_mapping["正式关系"]
    pending = gated_mapping["待验证关系"]
    if formal:
        lines.extend(["|起点|关系|终点|验证状态|证据|来源|", "|---|---|---|---|---|---|"])
        for item in formal:
            source = _escape(item.get("source_id"))
            source_uris = item.get("source_uris") or []
            if source_uris:
                source = source + "；" + _escape("；".join(str(uri) for uri in source_uris))
            lines.append(
                "|{subject}|{predicate}|{object}|{status}|{evidence}|{source}|".format(
                    subject=_escape(item.get("subject")), predicate=_escape(item.get("predicate")),
                    object=_escape(item.get("object")), status=_escape(item.get("verification_status")),
                    evidence=_escape(item.get("evidence_id") or "、".join(str(fact_id) for fact_id in item.get("fact_ids") or [])), source=source,
                )
            )
    else:
        lines.append("- 尚无通过证据门控的正式关系。")
    lines.append(f"- 待验证关系：{len(pending)} 条；不得进入确定性产业图谱。")

    has_publication_chapters = bool(content.get("出版章节"))
    if not has_publication_chapters:
        lines.extend(["", f"## {next_index + 1}. 情景分析、敏感性与催化剂", ""])
        lines.extend(_事实行(item) for item in by_module.get("情景分析", []))
        if not by_module.get("情景分析"):
            lines.append("- [证据不足] 基准/乐观/悲观情景的价格、产能、良率、客户认证和制程渗透参数尚未形成可复核模型。")

        lines.extend(["", f"## {next_index + 2}. 风险、反证与待验证事项", ""])
        lines.extend(_事实行(item) for item in by_module.get("风险与反证", []))
        if not by_module.get("风险与反证"):
            lines.append("- 需补齐技术替代、价格下行、客户集中、认证失败、产能爬坡、地缘合规与安全环保七类反证。")
        lines.extend(
            [
                f"- 未交叉验证事实：{coverage.未交叉验证事实} 项。",
                f"- 缺少页码/段落定位事实：{coverage.缺少定位事实} 项。",
                f"- 缺少可访问原始素材：{coverage.缺少原始素材} 项。",
            ]
        )

    evidence_index = next_index + 1 if has_publication_chapters else next_index + 3

    if content:
        lines.extend(["", f"## {evidence_index}. 关键事实—证据—验证矩阵", "", "|编号|模块|关键事实|状态|定位|来源|", "|---|---|---|---|---|---|"])
    else:
        lines.extend(["", f"## {evidence_index}. 关键事实—证据—验证矩阵", "", "|模块|关键事实|状态|定位|来源|", "|---|---|---|---|---|"])
    for item in facts:
        uris = item.get("source_uris") or [item.get("source_uri")]
        if content:
            lines.append(
                f"|{_escape(item.get('fact_id'))}|{_escape(item.get('module'))}|{_escape(item.get('claim'))}|{_escape(item.get('verification_status'))}|{_escape(item.get('locator'))}|{_escape('；'.join(str(uri) for uri in uris if uri))}|"
            )
        else:
            lines.append(
                f"|{_escape(item.get('module'))}|{_escape(item.get('claim'))}|{_escape(item.get('verification_status'))}|{_escape(item.get('locator'))}|{_escape('；'.join(str(uri) for uri in uris if uri))}|"
            )
    if not facts:
        lines.append("|-|-|尚无结构化事实|证据不足|-|-|" if content else "|-|尚无结构化事实|证据不足|-|-|")

    # 用户要求来源放报告最后，因此本节后不再追加任何正文。
    lines.extend(["", "## 数据来源、原始素材与引用清单", "", "|来源|类型|地区|可信度|文件|解析状态|原始链接|", "|---|---|---|---:|---|---|---|"])
    for source in sources:
        lines.append(
            f"|{_escape(source.get('source_name'))}|{_escape(source.get('source_type'))}|{_escape(source.get('region'))}|{_escape(source.get('credibility') or source.get('rating'))}|{_escape(source.get('raw_path'))}|{_escape(source.get('parse_status'))}|{_escape(source.get('source_uri'))} |"
        )
    if not sources:
        lines.append("|-|-|-|-|尚无来源|-|- |")

    output = Path(输出路径).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".临时")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temp, output)
    return output
