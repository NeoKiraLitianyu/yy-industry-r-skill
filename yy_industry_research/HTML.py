from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Iterable, Mapping

from .图表 import 渲染图表_svg


_ROOT = Path(__file__).resolve().parents[1]
_CSS = _ROOT / "assets" / "report-purple.css"
_TEMPLATE = _ROOT / "templates" / "report.html"


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else "").strip(), quote=True)


def _list(items: Iterable[Any], *, class_name: str = "") -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return ""
    class_attr = f' class="{_h(class_name)}"' if class_name else ""
    return f"<ul{class_attr}>" + "".join(f"<li>{_h(item)}</li>" for item in values) + "</ul>"


def _table(table: Mapping[str, Any], *, class_name: str = "") -> str:
    columns = list(table.get("columns") or table.get("列") or [])
    rows = list(table.get("rows") or table.get("行") or [])
    if not columns:
        return ""
    title = str(table.get("title") or table.get("标题") or "").strip()
    cls = f" {class_name}" if class_name else ""
    pieces = ['<div class="table-wrap">']
    if title:
        pieces.append(f"<h3>{_h(title)}</h3>")
    pieces.append(f'<table class="data-table{_h(cls)}"><thead><tr>')
    pieces.extend(f"<th>{_h(column)}</th>" for column in columns)
    pieces.append("</tr></thead><tbody>")
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != len(columns):
            continue
        pieces.append("<tr>" + "".join(f"<td>{_h(cell)}</td>" for cell in row) + "</tr>")
    pieces.append("</tbody></table>")
    basis = str(table.get("basis") or table.get("依据") or "").strip()
    if basis:
        pieces.append(f'<p class="chart-caption">表格依据：{_h(basis)}</p>')
    pieces.append("</div>")
    return "".join(pieces)


def _chart(spec: Mapping[str, Any], facts_by_id: Mapping[str, dict[str, Any]]) -> str:
    svg = 渲染图表_svg(spec, facts_by_id)
    trace = str(spec.get("trace") or "").strip()
    caption = f'<p class="chart-caption">{_h(trace)}</p>' if trace else ""
    return f'<figure class="chart">{svg}{caption}</figure>'


def _status_class(status: str) -> str:
    if status == "已验证":
        return "status-verified"
    if status == "单一来源":
        return "status-single"
    return "status-gap"


def _cover(publication: Mapping[str, Any]) -> str:
    content = publication.get("content") or {}
    facts = list(publication.get("facts") or [])
    sources = list(publication.get("sources") or [])
    charts = list(publication.get("charts") or [])
    verified = sum(1 for item in facts if item.get("verification_status") == "已验证")
    single = sum(1 for item in facts if item.get("verification_status") == "单一来源")
    return f"""
<section class="cover">
  <div class="cover-kicker">NEO STAR · PRIMARY MARKET RESEARCH</div>
  <div class="cover-rule"></div>
  <h1>半导体膜材行业深度研究与一级市场投资报告</h1>
  <p class="cover-subtitle">从材料 taxonomy、沉积工艺与薄膜结构，到先进制程需求、全球竞争、中国替代、证据交叉验证与投资决策。</p>
  <div class="cover-meta">
    <div class="meta-grid">
      <div class="meta-item"><span>数据时点</span><strong>{_h(publication.get('as_of') or content.get('as_of'))}</strong></div>
      <div class="meta-item"><span>结构化事实</span><strong>{len(facts)}</strong></div>
      <div class="meta-item"><span>原始来源</span><strong>{len(sources)}</strong></div>
      <div class="meta-item"><span>可追溯图表</span><strong>{len(charts)}</strong></div>
    </div>
    <p class="chart-caption">证据状态：已验证 {verified} 项 · 单一来源 {single} 项。单一来源不得写成确定性结论。</p>
  </div>
</section>"""


def _toc(chapters: list[dict[str, Any]]) -> str:
    items = []
    for index, chapter in enumerate(chapters, start=1):
        title = chapter.get("title") or chapter.get("module") or f"第{index}章"
        items.append(f'<li><a href="#chapter-{index:02d}"><span class="toc-index">{index:02d}</span>{_h(title)}</a></li>')
    items.extend(
        [
            '<li><a href="#mapping"><span class="toc-index">M</span>行业 Mapping 与投资机会地图</a></li>',
            '<li><a href="#evidence"><span class="toc-index">E</span>关键事实—证据—验证矩阵</a></li>',
            '<li><a href="#sources"><span class="toc-index">S</span>数据来源、原始素材与引用清单</a></li>',
        ]
    )
    return '<section class="toc"><div class="eyebrow">CONTENTS</div><h2>目录</h2><ol class="toc-list">' + "".join(items) + "</ol></section>"


def _executive(publication: Mapping[str, Any]) -> str:
    content = publication.get("content") or {}
    executive = content.get("执行摘要") or content.get("executive_summary") or {}
    facts = list(publication.get("facts") or [])
    verified = sum(1 for item in facts if item.get("verification_status") == "已验证")
    single = sum(1 for item in facts if item.get("verification_status") == "单一来源")
    gap = len(facts) - verified - single
    return f"""
<section class="front-matter executive">
  <div class="eyebrow">INVESTMENT VIEW</div>
  <h2>执行摘要与证据仪表盘</h2>
  <div class="metric-grid">
    <div class="metric"><span>已验证</span><strong>{verified}</strong></div>
    <div class="metric"><span>单一来源</span><strong>{single}</strong></div>
    <div class="metric"><span>冲突/缺口</span><strong>{gap}</strong></div>
    <div class="metric"><span>出版章节</span><strong>{len(content.get('出版章节') or [])}</strong></div>
  </div>
  <div class="executive-card"><h3>核心结论</h3><p>{_h(executive.get('核心结论') or executive.get('conclusion') or '以证据门控后的事实与行业 Mapping 形成投资判断。')}</p></div>
  <h3>关键判断</h3>{_list(executive.get('关键判断') or executive.get('key_judgments') or [])}
  <h3>投资成立条件</h3>{_list(executive.get('投资条件') or executive.get('investment_conditions') or [])}
  <h3>核心否证条件</h3>{_list(executive.get('否证条件') or executive.get('disconfirmations') or [], class_name='uncertainty')}
</section>"""


def _chapter(index: int, chapter: Mapping[str, Any], chart_html: str = "") -> str:
    title = chapter.get("title") or chapter.get("module") or f"第{index}章"
    paragraphs = chapter.get("paragraphs") or chapter.get("正文") or []
    tables = chapter.get("tables") or chapter.get("表格") or []
    implications = chapter.get("investment_implications") or chapter.get("投资含义") or []
    uncertainties = chapter.get("uncertainties") or chapter.get("不确定性") or []
    fact_ids = chapter.get("fact_ids") or []
    body = "".join(f"<p>{_h(paragraph)}</p>" for paragraph in paragraphs if str(paragraph).strip())
    tags = "".join(f'<span class="fact-tag">{_h(fact_id)}</span>' for fact_id in fact_ids)
    return f"""
<section class="publication-chapter" id="chapter-{index:02d}">
  <header class="chapter-heading"><div class="chapter-number">CHAPTER {index:02d} · {_h(chapter.get('module'))}</div><h2>{_h(title)}</h2></header>
  <div class="thesis">本章判断：{_h(chapter.get('thesis') or chapter.get('核心判断'))}</div>
  <div class="body-copy">{body}</div>
  {chart_html}
  {''.join(_table(table) for table in tables if isinstance(table, Mapping))}
  <h3>一级市场投资含义</h3>{_list(implications)}
  <h3>不确定性与待验证事项</h3>{_list(uncertainties, class_name='uncertainty')}
  <div class="fact-tags"><strong>事实锚点：</strong>{tags or '本章为来源附录结构说明'}</div>
</section>"""


def _mapping(publication: Mapping[str, Any]) -> str:
    mapping = publication.get("mappings") or {}
    if isinstance(mapping, Mapping):
        formal = list(mapping.get("正式关系") or [])
        pending = list(mapping.get("待验证关系") or [])
    else:
        formal = list(mapping)
        pending = []
    rows = []
    for item in formal:
        rows.append(
            [item.get("subject"), item.get("predicate"), item.get("object"), item.get("verification_status"), "、".join(item.get("fact_ids") or [])]
        )
    table = _table({"columns": ["起点", "关系", "终点", "状态", "事实锚点"], "rows": rows}, class_name="mapping-table")
    return f"""
<section class="appendix" id="mapping">
  <div class="eyebrow">INDUSTRY GRAPH</div><h2>行业 Mapping 与投资机会地图</h2>
  <div class="mapping-summary"><div class="mapping-box"><span>正式关系</span><br><strong>{len(formal)}</strong></div><div class="mapping-box"><span>待验证关系</span><br><strong>{len(pending)}</strong></div></div>
  <p class="source-note">只有已归档原文、有效事实编号和至少两个独立来源族共同支持的关系进入正式图谱；公司单方客户与节点口径保留为待验证。</p>
  {table if rows else '<p>尚无通过全部证据门的正式关系。</p>'}
</section>"""


def _evidence(publication: Mapping[str, Any]) -> str:
    rows = []
    for fact in publication.get("facts") or []:
        status = str(fact.get("verification_status") or "证据不足")
        uris = fact.get("source_uris") or [fact.get("source_uri")]
        rows.append(
            "<tr>"
            f"<td>{_h(fact.get('fact_id'))}</td><td>{_h(fact.get('module'))}</td><td>{_h(fact.get('claim'))}</td>"
            f'<td class="{_status_class(status)}">{_h(status)}</td><td>{_h(fact.get("locator"))}</td>'
            f'<td class="url">{_h("；".join(str(uri) for uri in uris if uri))}</td></tr>'
        )
    return """
<section class="appendix" id="evidence">
  <div class="eyebrow">EVIDENCE MATRIX</div><h2>关键事实—证据—验证矩阵</h2>
  <p class="source-note">每条硬事实均保留编号、验证状态、原文定位和来源 URI；“单一来源”是披露边界，不是弱化后的“已验证”。</p>
  <div class="table-wrap"><table class="matrix-table"><thead><tr><th>编号</th><th>模块</th><th>关键事实</th><th>状态</th><th>原文定位</th><th>来源</th></tr></thead><tbody>
""" + "".join(rows) + "</tbody></table></div></section>"


def _sources(publication: Mapping[str, Any]) -> str:
    rows = []
    for source in publication.get("sources") or []:
        rows.append(
            "<tr>"
            f"<td>{_h(source.get('source_name'))}</td><td>{_h(source.get('source_type'))}</td><td>{_h(source.get('region'))}</td>"
            f"<td>{_h(source.get('credibility') or source.get('rating'))}</td><td>{_h(source.get('parse_status'))}</td>"
            f'<td>{_h(source.get("raw_path"))}</td><td class="url">{_h(source.get("source_uri"))}</td></tr>'
        )
    return """
<section class="appendix source-appendix" id="sources">
  <div class="eyebrow">SOURCE LINEAGE</div><h2>数据来源、原始素材与引用清单</h2>
  <p class="source-note">本节为报告最后正文。原始网页、PDF、附件和数据回执均应在行业资料库中留存；以下路径与 URI 用于复核、更新和尽调追问。</p>
  <div class="table-wrap"><table class="source-table"><thead><tr><th>来源</th><th>类型</th><th>地区</th><th>可信度</th><th>解析</th><th>原始文件</th><th>原始链接</th></tr></thead><tbody>
""" + "".join(rows) + '</tbody></table></div><div class="end-mark">END OF REPORT · NEO STAR INDUSTRY RESEARCH</div></section>'


def 生成出版HTML(output: str | Path, publication: dict[str, Any]) -> Path:
    """将通过证据门的出版模型渲染为完全自包含的 A4 HTML。"""

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = publication.get("content") or {}
    chapters = list(content.get("出版章节") or [])
    if len(chapters) != 22:
        raise ValueError("HTML 出版要求恰好22个出版章节")
    facts_by_id = {
        str(item.get("fact_id")): dict(item)
        for item in publication.get("facts") or []
        if str(item.get("fact_id") or "").strip()
    }
    charts = list(publication.get("charts") or [])
    chart_blocks = [_chart(spec, facts_by_id) for spec in charts]

    body = [_cover(publication), _toc(chapters), _executive(publication)]
    for index, chapter in enumerate(chapters, start=1):
        body.append(_chapter(index, chapter, chart_blocks[index - 1] if index <= len(chart_blocks) else ""))
    body.extend([_mapping(publication), _evidence(publication), _sources(publication)])

    template = _TEMPLATE.read_text(encoding="utf-8")
    css = _CSS.read_text(encoding="utf-8")
    title = "半导体膜材行业深度研究与一级市场投资报告"
    document = template.replace("__TITLE__", _h(title)).replace("__STYLE__", css).replace("__BODY__", "\n".join(body))
    lowered = document.lower()
    if any(token in lowered for token in ("<script", "https://fonts", "@import", "<foreignobject")):
        raise ValueError("HTML 出版物包含远程依赖或脚本")
    output_path.write_text(document, encoding="utf-8")
    return output_path
