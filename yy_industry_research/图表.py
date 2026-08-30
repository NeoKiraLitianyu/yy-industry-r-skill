from __future__ import annotations

import html
from math import cos, isfinite, pi, sin
from typing import Any, Callable, Mapping

from .出版 import 支持图表类型, 视觉令牌


_宽度 = 960
_高度 = 540
_支持类型 = 支持图表类型()
_色阶 = {
    "high": "#4B2E83",
    "medium": "#7456A8",
    "low": "#C7B6E4",
    "neutral": "#DED6E8",
    "accent": "#8C6BC4",
    "risk": "#C66B6B",
    "positive": "#6A9D78",
}


def 支持图表类型() -> set[str]:
    return set(_支持类型)


def _安全文本(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    lowered = text.lower()
    if any(token in lowered for token in ("http://", "https://", "<script", "<foreignobject", "xlink:href")):
        raise ValueError("SVG 文本包含不允许的远程或脚本内容")
    return html.escape(text, quote=True)


def _非空文本(value: Any, *, field: str, chart_id: str) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(f"图表缺少必要文本字段：{chart_id} -> {field}")
    return text


def _色值(name: str) -> str:
    return _色阶.get(str(name or "").strip(), _色阶["neutral"])


def _数值(value: Any, *, field: str, chart_id: str, minimum: float = 0.0, maximum: float = 1_000_000.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"图表数值非法：{chart_id} -> {field}") from exc
    if not isfinite(number):
        raise ValueError(f"图表数值必须有限：{chart_id} -> {field}")
    if number < minimum:
        raise ValueError(f"图表数值不得为负：{chart_id} -> {field}")
    if number > maximum:
        raise ValueError(f"图表数值超出合理范围：{chart_id} -> {field}")
    return number


def _整型(value: Any, *, field: str, chart_id: str, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"图表整数非法：{chart_id} -> {field}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"图表整数非法：{chart_id} -> {field}") from exc
    if number < minimum:
        raise ValueError(f"图表整数不得小于{minimum}：{chart_id} -> {field}")
    return number


def _追踪文本(spec: Mapping[str, Any]) -> str:
    fact_ids = [str(item).strip() for item in spec.get("fact_ids", []) if str(item).strip()]
    anchors = f"事实锚点：{'、'.join(fact_ids)}" if fact_ids else ""
    model_label = str(spec.get("model_label") or "").strip()
    if model_label and anchors:
        return f"{model_label}；{anchors}"
    if str(spec.get("fact_scope") or "").strip() == "all":
        anchors = "事实锚点：全部已装载事实"
    return anchors or model_label or "无"


def _证据事实(spec: Mapping[str, Any], facts_by_id: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if str(spec.get("fact_scope") or "").strip() == "all":
        facts = [dict(item) for item in facts_by_id.values()]
    else:
        fact_ids = [str(item).strip() for item in spec.get("fact_ids", []) if str(item).strip()]
        facts = [dict(facts_by_id[fact_id]) for fact_id in fact_ids]
    if not facts:
        raise ValueError(f"evidence 图表缺少可聚合事实：{spec.get('id') or '未命名'}")
    return facts


def _校验依据(spec: Mapping[str, Any], facts_by_id: Mapping[str, dict[str, Any]]) -> None:
    chart_id = str(spec.get("id") or "").strip() or "未命名"
    chart_type = str(spec.get("type") or "").strip()
    if chart_type not in _支持类型:
        raise ValueError(f"图表类型不支持：{chart_type or '空'}")
    for key in ("title", "as_of", "basis"):
        _非空文本(spec.get(key), field=key, chart_id=chart_id)

    model_label = str(spec.get("model_label") or "").strip()
    if model_label and model_label != "内部模型假设":
        raise ValueError(f"图表只允许 model_label=内部模型假设：{chart_id}")

    fact_ids = [str(item).strip() for item in spec.get("fact_ids", []) if str(item).strip()]
    fact_scope = str(spec.get("fact_scope") or "").strip()
    if fact_scope and fact_scope != "all":
        raise ValueError(f"图表 fact_scope 只允许 all：{chart_id}")
    if fact_scope == "all" and chart_type != "evidence":
        raise ValueError(f"只有 evidence 图表允许 fact_scope=all：{chart_id}")
    missing = sorted({fact_id for fact_id in fact_ids if fact_id not in facts_by_id})
    if missing:
        raise ValueError(f"不存在的事实引用：{'、'.join(missing)}")
    if not fact_ids and fact_scope != "all" and model_label != "内部模型假设":
        raise ValueError(f"图表缺少事实引用或内部模型标签：{chart_id}")


def _页眉(spec: Mapping[str, Any], tokens: Mapping[str, str]) -> str:
    title = _安全文本(spec.get("title"))
    as_of = _安全文本(spec.get("as_of"))
    basis = _安全文本(spec.get("basis"))
    trace = _安全文本(spec.get("trace") or _追踪文本(spec))
    return (
        f"<rect x='0' y='0' width='{_宽度}' height='{_高度}' fill='{tokens['paper']}'/>"
        f"<rect x='32' y='28' width='{_宽度 - 64}' height='{_高度 - 56}' rx='18' "
        f"fill='{tokens['paper']}' stroke='{tokens['rule']}' stroke-width='2'/>"
        f"<text x='56' y='74' font-size='28' font-weight='700' fill='{tokens['primary_purple']}'>"
        f"{title}</text>"
        f"<text x='56' y='104' font-size='14' fill='{tokens['muted_text']}'>"
        f"as_of: {as_of}</text>"
        f"<text x='56' y='126' font-size='14' fill='{tokens['muted_text']}'>"
        f"basis: {basis}</text>"
        f"<text x='56' y='{_高度 - 34}' font-size='13' fill='{tokens['muted_text']}'>"
        f"trace: {trace}</text>"
    )


def _基础线(tokens: Mapping[str, str]) -> str:
    return (
        f"<line x1='80' y1='430' x2='860' y2='430' stroke='{tokens['rule']}' stroke-width='2'/>"
        f"<line x1='80' y1='430' x2='80' y2='150' stroke='{tokens['rule']}' stroke-width='2'/>"
    )


def _校验_bar(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    chart_id = str(spec.get("id") or "").strip() or "未命名"
    bars = list(spec.get("bars", []))
    if not bars:
        raise ValueError(f"bar 图表数据不能为空：{chart_id}")
    for index, bar in enumerate(bars, start=1):
        if not isinstance(bar, Mapping):
            raise ValueError(f"bar 图表条目必须是对象：{chart_id} -> {index}")
        _非空文本(bar.get("label"), field=f"bars[{index}].label", chart_id=chart_id)
        _数值(bar.get("value"), field=f"bars[{index}].value", chart_id=chart_id)
    return [dict(item) for item in bars]


def _校验网格(spec: Mapping[str, Any], *, chart_type: str) -> tuple[list[str], list[dict[str, Any]]]:
    chart_id = str(spec.get("id") or "").strip() or "未命名"
    columns = [str(item).strip() for item in spec.get("columns", []) if str(item).strip()]
    rows = list(spec.get("rows", []))
    if not columns or not rows:
        raise ValueError(f"{chart_type} 图表数据不能为空：{chart_id}")
    normalized_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"{chart_type} 行必须是对象：{chart_id} -> {row_index}")
        _非空文本(row.get("label"), field=f"rows[{row_index}].label", chart_id=chart_id)
        cells = list(row.get("cells", []))
        if len(cells) != len(columns):
            raise ValueError(f"{chart_type} 行列维度不一致：{chart_id} -> {row_index}")
        normalized_cells: list[dict[str, Any]] = []
        for cell_index, cell in enumerate(cells, start=1):
            if not isinstance(cell, Mapping):
                raise ValueError(f"{chart_type} 单元格必须是对象：{chart_id} -> {row_index}/{cell_index}")
            _非空文本(cell.get("label"), field=f"rows[{row_index}].cells[{cell_index}].label", chart_id=chart_id)
            normalized_cells.append(dict(cell))
        normalized_row = dict(row)
        normalized_row["cells"] = normalized_cells
        normalized_rows.append(normalized_row)
    return columns, normalized_rows


def _校验_flow(spec: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chart_id = str(spec.get("id") or "").strip() or "未命名"
    nodes = list(spec.get("nodes", []))
    links = list(spec.get("links", []))
    if not nodes or not links:
        raise ValueError(f"flow 图表节点和边不能为空：{chart_id}")
    seen: set[str] = set()
    positions: dict[str, tuple[int, int]] = {}
    normalized_nodes: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, Mapping):
            raise ValueError(f"flow 节点必须是对象：{chart_id} -> {index}")
        node_id = _非空文本(node.get("id"), field=f"nodes[{index}].id", chart_id=chart_id)
        if node_id in seen:
            raise ValueError(f"flow 节点重复：{chart_id} -> {node_id}")
        seen.add(node_id)
        column = _整型(node.get("column"), field=f"nodes[{index}].column", chart_id=chart_id)
        row = _整型(node.get("row"), field=f"nodes[{index}].row", chart_id=chart_id)
        positions[node_id] = (column, row)
        _非空文本(node.get("label"), field=f"nodes[{index}].label", chart_id=chart_id)
        normalized_nodes.append(dict(node))
    normalized_links: list[dict[str, Any]] = []
    for index, link in enumerate(links, start=1):
        if not isinstance(link, Mapping):
            raise ValueError(f"flow 边必须是对象：{chart_id} -> {index}")
        start = _非空文本(link.get("from"), field=f"links[{index}].from", chart_id=chart_id)
        end = _非空文本(link.get("to"), field=f"links[{index}].to", chart_id=chart_id)
        if start not in positions or end not in positions:
            raise ValueError(f"flow 边引用了不存在节点：{chart_id} -> {start}->{end}")
        if start == end:
            raise ValueError(f"flow 边不能自环：{chart_id} -> {start}")
        normalized_links.append(dict(link))
    return normalized_nodes, normalized_links


def _校验_ladder(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    chart_id = str(spec.get("id") or "").strip() or "未命名"
    steps = list(spec.get("steps", []))
    if not steps:
        raise ValueError(f"ladder 图表步骤不能为空：{chart_id}")
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, Mapping):
            raise ValueError(f"ladder 步骤必须是对象：{chart_id} -> {index}")
        _非空文本(step.get("label"), field=f"steps[{index}].label", chart_id=chart_id)
    return [dict(item) for item in steps]


def _标准化_radar轴(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    chart_id = str(spec.get("id") or "").strip() or "未命名"
    axes = list(spec.get("axes", []))
    if not axes:
        raise ValueError(f"radar 图表 axes 不能为空：{chart_id}")
    if all(isinstance(axis, Mapping) for axis in axes):
        normalized: list[dict[str, Any]] = []
        for index, axis in enumerate(axes, start=1):
            label = _非空文本(axis.get("label"), field=f"axes[{index}].label", chart_id=chart_id)
            value = _数值(axis.get("value"), field=f"axes[{index}].value", chart_id=chart_id)
            max_value = _数值(axis.get("max", 100), field=f"axes[{index}].max", chart_id=chart_id, minimum=1.0)
            normalized.append({"label": label, "value": value, "max": max_value})
        return normalized

    values = list(spec.get("values", []))
    if len(values) != len(axes):
        raise ValueError(f"radar 图表 axes/values 长度不一致：{chart_id}")
    max_values = spec.get("max_values")
    if isinstance(max_values, list):
        if len(max_values) != len(axes):
            raise ValueError(f"radar 图表 max_values 长度不一致：{chart_id}")
        max_list = list(max_values)
    else:
        scalar_max = spec.get("max_value", spec.get("max", 100))
        max_list = [scalar_max] * len(axes)

    normalized = []
    for index, axis in enumerate(axes, start=1):
        label = _非空文本(axis, field=f"axes[{index}]", chart_id=chart_id)
        value = _数值(values[index - 1], field=f"values[{index}]", chart_id=chart_id)
        max_value = _数值(max_list[index - 1], field=f"max[{index}]", chart_id=chart_id, minimum=1.0)
        normalized.append({"label": label, "value": value, "max": max_value})
    return normalized


def _证据段(spec: Mapping[str, Any], facts_by_id: Mapping[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    chart_id = str(spec.get("id") or "").strip() or "未命名"
    if "segments" in spec:
        segments = list(spec.get("segments", []))
        if not segments:
            raise ValueError(f"evidence 图表 segments 不能为空：{chart_id}")
        if str(spec.get("model_label") or "").strip() != "内部模型假设":
            raise ValueError(f"evidence 静态 segments 只能用于内部模型假设：{chart_id}")
        normalized = []
        for index, segment in enumerate(segments, start=1):
            if not isinstance(segment, Mapping):
                raise ValueError(f"evidence segment 必须是对象：{chart_id} -> {index}")
            label = _非空文本(segment.get("label"), field=f"segments[{index}].label", chart_id=chart_id)
            value = _数值(segment.get("value"), field=f"segments[{index}].value", chart_id=chart_id)
            normalized.append({"label": label, "value": value, "tone": str(segment.get("tone") or "neutral")})
        return normalized, "内部模型指数"

    facts = _证据事实(spec, facts_by_id)
    verified = sum(1 for fact in facts if str(fact.get("verification_status") or "") == "已验证")
    single = sum(1 for fact in facts if str(fact.get("verification_status") or "") == "单一来源")
    gap = len(facts) - verified - single
    multi_source = 0
    one_source = 0
    for fact in facts:
        uris = {str(item).strip() for item in fact.get("source_uris", []) if str(item).strip()}
        if not uris and str(fact.get("source_uri") or "").strip():
            uris = {str(fact["source_uri"]).strip()}
        if len(uris) >= 2:
            multi_source += 1
        elif len(uris) == 1:
            one_source += 1
    segments = [
        {"label": "已验证", "value": float(verified), "tone": "high"},
        {"label": "单一来源", "value": float(single), "tone": "medium"},
        {"label": "研究缺口/模型", "value": float(gap), "tone": "neutral"},
    ]
    summary = f"来源结构：多来源 {multi_source} / 单一来源 {one_source}"
    return segments, summary


def _渲染_bar(spec: Mapping[str, Any], tokens: Mapping[str, str]) -> str:
    bars = _校验_bar(spec)
    max_value = max(_数值(item.get("value"), field="bars.value", chart_id=str(spec.get("id") or "")) for item in bars) or 1.0
    gap = 28
    bar_width = max(36, int((720 - gap * max(len(bars) - 1, 0)) / max(len(bars), 1)))
    body = [_基础线(tokens)]
    for index, item in enumerate(bars):
        x = 112 + index * (bar_width + gap)
        value = _数值(item.get("value"), field=f"bars[{index + 1}].value", chart_id=str(spec.get("id") or ""))
        height = int(240 * value / max_value)
        y = 430 - height
        fill = _色值(str(item.get("tone") or "high"))
        label = _安全文本(item.get("label"))
        metric = _安全文本(item.get("display") or f"{value:g}{item.get('unit') or ''}")
        body.append(
            f"<rect x='{x}' y='{y}' width='{bar_width}' height='{height}' rx='8' fill='{fill}'/>"
            f"<text x='{x + bar_width / 2:.1f}' y='{y - 10}' text-anchor='middle' font-size='14' fill='{tokens['ink']}'>"
            f"{metric}</text>"
            f"<text x='{x + bar_width / 2:.1f}' y='458' text-anchor='middle' font-size='13' fill='{tokens['ink']}'>"
            f"{label}</text>"
        )
    return "".join(body)


def _渲染_heatmap(spec: Mapping[str, Any], tokens: Mapping[str, str]) -> str:
    columns, rows = _校验网格(spec, chart_type="heatmap")
    cell_width = 130
    cell_height = 50
    left = 220
    top = 170
    body = []
    for col_index, column in enumerate(columns):
        x = left + col_index * cell_width
        body.append(
            f"<text x='{x + cell_width / 2:.1f}' y='{top - 18}' text-anchor='middle' font-size='14' "
            f"fill='{tokens['ink']}'>{_安全文本(column)}</text>"
        )
    for row_index, row in enumerate(rows):
        y = top + row_index * cell_height
        body.append(
            f"<text x='198' y='{y + 30}' text-anchor='end' font-size='14' fill='{tokens['ink']}'>"
            f"{_安全文本(row.get('label'))}</text>"
        )
        for col_index, cell in enumerate(row.get("cells", [])):
            x = left + col_index * cell_width
            fill = _色值(str(cell.get("tone") or "neutral"))
            body.append(
                f"<rect x='{x}' y='{y}' width='{cell_width - 10}' height='{cell_height - 10}' rx='10' fill='{fill}'/>"
                f"<text x='{x + (cell_width - 10) / 2:.1f}' y='{y + 28}' text-anchor='middle' font-size='13' fill='{tokens['paper']}'>"
                f"{_安全文本(cell.get('label'))}</text>"
            )
        body.append("")
    return "".join(body)


def _渲染_flow(spec: Mapping[str, Any], tokens: Mapping[str, str]) -> str:
    nodes, links = _校验_flow(spec)
    positions: dict[str, tuple[float, float]] = {}
    body: list[str] = []
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        column = _整型(node.get("column"), field=f"{node_id}.column", chart_id=str(spec.get("id") or ""))
        row = _整型(node.get("row"), field=f"{node_id}.row", chart_id=str(spec.get("id") or ""))
        x = 90 + column * 190
        y = 170 + row * 90
        positions[node_id] = (x, y)
    for link in links:
        start = positions[str(link.get("from") or "")]
        end = positions[str(link.get("to") or "")]
        sx, sy = start
        ex, ey = end
        body.append(
            f"<line x1='{sx + 140}' y1='{sy + 24}' x2='{ex}' y2='{ey + 24}' stroke='{tokens['violet']}' stroke-width='4'/>"
        )
        if str(link.get("label") or "").strip():
            body.append(
                f"<text x='{(sx + ex + 140) / 2:.1f}' y='{(sy + ey) / 2 + 12:.1f}' text-anchor='middle' "
                f"font-size='12' fill='{tokens['muted_text']}'>{_安全文本(link.get('label'))}</text>"
            )
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        x, y = positions[node_id]
        fill = _色值(str(node.get("tone") or "medium"))
        body.append(
            f"<rect x='{x}' y='{y}' width='140' height='48' rx='12' fill='{fill}'/>"
            f"<text x='{x + 70}' y='{y + 29}' text-anchor='middle' font-size='13' fill='{tokens['paper']}'>"
            f"{_安全文本(node.get('label'))}</text>"
        )
    return "".join(body)


def _渲染_matrix(spec: Mapping[str, Any], tokens: Mapping[str, str]) -> str:
    columns, rows = _校验网格(spec, chart_type="matrix")
    cell_width = 155
    cell_height = 54
    left = 190
    top = 170
    body: list[str] = []
    for col_index, column in enumerate(columns):
        x = left + col_index * cell_width
        body.append(
            f"<text x='{x + cell_width / 2:.1f}' y='{top - 20}' text-anchor='middle' font-size='14' fill='{tokens['ink']}'>"
            f"{_安全文本(column)}</text>"
        )
    for row_index, row in enumerate(rows):
        y = top + row_index * cell_height
        body.append(
            f"<text x='168' y='{y + 32}' text-anchor='end' font-size='14' fill='{tokens['ink']}'>"
            f"{_安全文本(row.get('label'))}</text>"
        )
        for col_index, cell in enumerate(row.get("cells", [])):
            x = left + col_index * cell_width
            fill = _色值(str(cell.get("tone") or "neutral"))
            text_fill = tokens["paper"] if fill != _色阶["neutral"] else tokens["ink"]
            body.append(
                f"<rect x='{x}' y='{y}' width='{cell_width - 10}' height='{cell_height - 10}' rx='10' fill='{fill}' stroke='{tokens['rule']}'/>"
                f"<text x='{x + (cell_width - 10) / 2:.1f}' y='{y + 30}' text-anchor='middle' font-size='13' fill='{text_fill}'>"
                f"{_安全文本(cell.get('label'))}</text>"
            )
    return "".join(body)


def _渲染_ladder(spec: Mapping[str, Any], tokens: Mapping[str, str]) -> str:
    steps = _校验_ladder(spec)
    body: list[str] = []
    base_y = 390
    for index, step in enumerate(steps):
        width = 520 - index * 80
        x = 220 + index * 40
        y = base_y - index * 56
        fill = _色值(str(step.get("tone") or "medium"))
        body.append(
            f"<rect x='{x}' y='{y}' width='{width}' height='44' rx='10' fill='{fill}'/>"
            f"<text x='{x + 20}' y='{y + 28}' font-size='13' fill='{tokens['paper']}'>{_安全文本(step.get('label'))}</text>"
        )
        if str(step.get("detail") or "").strip():
            body.append(
                f"<text x='{x + width + 16}' y='{y + 28}' font-size='13' fill='{tokens['ink']}'>{_安全文本(step.get('detail'))}</text>"
            )
    return "".join(body)


def _渲染_radar(spec: Mapping[str, Any], tokens: Mapping[str, str]) -> str:
    axes = _标准化_radar轴(spec)
    center_x = 370
    center_y = 300
    radius = 120
    rings = []
    for ring in range(1, 5):
        r = radius * ring / 4
        points = []
        for index in range(len(axes)):
            angle = -pi / 2 + index * 2 * pi / len(axes)
            points.append(f"{center_x + cos(angle) * r:.1f},{center_y + sin(angle) * r:.1f}")
        rings.append(
            f"<polygon points='{' '.join(points)}' fill='none' stroke='{tokens['rule']}' stroke-width='1'/>"
        )
    value_points = []
    labels = []
    for index, axis in enumerate(axes):
        angle = -pi / 2 + index * 2 * pi / len(axes)
        max_value = max(float(axis["max"]), 1.0)
        distance = radius * float(axis["value"]) / max_value
        outer_x = center_x + cos(angle) * (radius + 34)
        outer_y = center_y + sin(angle) * (radius + 34)
        value_points.append(f"{center_x + cos(angle) * distance:.1f},{center_y + sin(angle) * distance:.1f}")
        labels.append(
            f"<line x1='{center_x}' y1='{center_y}' x2='{center_x + cos(angle) * radius:.1f}' y2='{center_y + sin(angle) * radius:.1f}' "
            f"stroke='{tokens['rule']}' stroke-width='1'/>"
            f"<text x='{outer_x:.1f}' y='{outer_y:.1f}' text-anchor='middle' font-size='13' fill='{tokens['ink']}'>"
            f"{_安全文本(axis['label'])}</text>"
        )
    legend = (
        f"<rect x='620' y='214' width='220' height='104' rx='14' fill='{tokens['surface_soft']}' stroke='{tokens['rule']}'/>"
        f"<text x='642' y='246' font-size='15' fill='{tokens['primary_purple']}'>评分指数</text>"
        f"<text x='642' y='274' font-size='13' fill='{tokens['ink']}'>仅用于项目排序，不代表历史胜率</text>"
        f"<text x='642' y='298' font-size='13' fill='{tokens['ink']}'>模型标签：{_安全文本(spec.get('model_label') or '')}</text>"
    )
    return "".join(rings) + "".join(labels) + (
        f"<polygon points='{' '.join(value_points)}' fill='{tokens['violet']}' fill-opacity='0.28' "
        f"stroke='{tokens['primary_purple']}' stroke-width='3'/>"
    ) + legend


def _渲染_evidence(spec: Mapping[str, Any], tokens: Mapping[str, str], facts_by_id: Mapping[str, dict[str, Any]]) -> str:
    segments, summary = _证据段(spec, facts_by_id)
    total = sum(_数值(item.get("value"), field=f"{item.get('label')}.value", chart_id=str(spec.get("id") or "")) for item in segments) or 1.0
    x = 120
    body = [
        f"<rect x='{x}' y='220' width='680' height='46' rx='12' fill='{tokens['surface_soft']}' stroke='{tokens['rule']}'/>",
        f"<text x='120' y='192' font-size='13' fill='{tokens['muted_text']}'>{_安全文本(summary)}</text>",
    ]
    cursor = x
    legend_y = 324
    for index, segment in enumerate(segments):
        value = _数值(segment.get("value"), field=f"segments[{index + 1}].value", chart_id=str(spec.get("id") or ""))
        width = 680 * value / total
        fill = _色值(str(segment.get("tone") or "neutral"))
        body.append(
            f"<rect x='{cursor:.1f}' y='220' width='{width:.1f}' height='46' rx='12' fill='{fill}'/>"
        )
        body.append(
            f"<rect x='120' y='{legend_y + index * 30}' width='16' height='16' rx='4' fill='{fill}'/>"
            f"<text x='146' y='{legend_y + index * 30 + 13}' font-size='13' fill='{tokens['ink']}'>"
            f"{_安全文本(segment.get('label'))} {int(value):d}</text>"
        )
        cursor += width
    return "".join(body)


_渲染器: dict[str, Callable[[Mapping[str, Any], Mapping[str, str], Mapping[str, dict[str, Any]]], str]] = {
    "bar": lambda spec, tokens, _facts: _渲染_bar(spec, tokens),
    "heatmap": lambda spec, tokens, _facts: _渲染_heatmap(spec, tokens),
    "flow": lambda spec, tokens, _facts: _渲染_flow(spec, tokens),
    "matrix": lambda spec, tokens, _facts: _渲染_matrix(spec, tokens),
    "ladder": lambda spec, tokens, _facts: _渲染_ladder(spec, tokens),
    "radar": lambda spec, tokens, _facts: _渲染_radar(spec, tokens),
    "evidence": _渲染_evidence,
}


def 渲染图表_svg(spec: dict[str, Any], facts_by_id: Mapping[str, dict[str, Any]]) -> str:
    _校验依据(spec, facts_by_id)
    tokens = 视觉令牌()
    chart_type = str(spec["type"])
    body = _渲染器[chart_type](spec, tokens, facts_by_id)
    title = _安全文本(spec.get("title"))
    desc = _安全文本(
        f"title={spec.get('title')}; as_of={spec.get('as_of')}; basis={spec.get('basis')}; "
        f"trace={spec.get('trace') or _追踪文本(spec)}"
    )
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{_宽度}' height='{_高度}' "
        f"viewBox='0 0 {_宽度} {_高度}' role='img'>"
        f"<title>{title}</title>"
        f"<desc>{desc}</desc>"
        f"{_页眉(spec, tokens)}"
        f"{body}"
        f"</svg>"
    )
    lowered = svg.lower().replace("http://www.w3.org/2000/svg", "")
    for token in ("http://", "https://", "<script", "<foreignobject", "xlink:href"):
        if token in lowered:
            raise ValueError("SVG 输出包含不允许内容")
    return svg
