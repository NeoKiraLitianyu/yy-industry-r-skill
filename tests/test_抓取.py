# -*- coding: utf-8 -*-
"""测试「抓取」子命令：对外抓取现成行业报告/研报（不创作新报告）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.行业研究 import _抓取_网页源, _run_fetch


def _args(**overrides):
    base = {
        "主题": "光模块",
        "来源": "bing",
        "数量": 5,
        "时间范围": "past 12 months",
        "输出目录": ".",
        "仅列表": True,
        "json": False,
    }
    base.update(overrides)
    return type("Args", (), base)()


def test_抓取网页源_bing结果并入清单(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import 行业研究

    def fake_搜索Bing源(query: str, max_results: int):
        return [
            ("https://example.com/report1.pdf", "光模块行业深度报告 2026", "光模块市场"),
            ("https://example.com/report2.html", "Global Optical Module Report 2026", "market"),
        ]

    monkeypatch.setattr(行业研究, "搜索Bing源", fake_搜索Bing源)

    hits = _抓取_网页源("光模块", "bing", max_results=5)

    assert len(hits) == 2
    assert hits[0]["标题"] == "光模块行业深度报告 2026"
    assert hits[0]["链接"] == "https://example.com/report1.pdf"
    assert hits[0]["类型"] == "网页"
    assert hits[0]["地区"] == "中国"


def test_抓取网页源_单源失败不阻塞(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import 行业研究

    def fake_搜索Bing源(query: str, max_results: int):
        raise RuntimeError("network down")

    monkeypatch.setattr(行业研究, "搜索Bing源", fake_搜索Bing源)

    hits = _抓取_网页源("光模块", "bing", max_results=5)
    assert hits == []  # 失败返回空，不抛异常


def test_抓取网页源_多源合并去重(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import 行业研究

    def fake_搜索Bing源(query: str, max_results: int):
        return [("https://example.com/same.pdf", "同一报告", "")]

    class FakeYixinAdapter:
        def __init__(self, *args, **kwargs):
            pass

        def 检索(self, 请求):
            class Item:
                标题 = "同一报告"
                原始链接 = "https://example.com/same.pdf"
                来源名称 = "某券商"
                来源类型 = "report"
                地区 = "中国"
                发布日期 = "2026-06-01"

            return [Item()]

    monkeypatch.setattr(行业研究, "搜索Bing源", fake_搜索Bing源)
    monkeypatch.setattr(行业研究, "Yixin适配器", FakeYixinAdapter)

    hits = _抓取_网页源("光模块", "bing,yixin", max_results=5)

    # 同一链接只保留一条
    assert len(hits) == 1


def test_抓取_仅列表不下载附件(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import 行业研究

    def fake_抓取_网页源(主题, 来源, max_results, 时间范围):
        return [
            {
                "标题": "光模块行业报告",
                "链接": "https://example.com/report.pdf",
                "来源": "某券商",
                "类型": "report",
                "地区": "中国",
                "发布日期": None,
            }
        ]

    monkeypatch.setattr(行业研究, "_抓取_网页源", fake_抓取_网页源)
    calls = {"download": 0}

    def fake_download(link, d):
        calls["download"] += 1
        return Path(d) / "report.pdf"

    monkeypatch.setattr(行业研究, "_download", fake_download)

    result = _run_fetch(_args(输出目录=str(tmp_path), 仅列表=True))
    assert result == 0
    assert calls["download"] == 0  # 仅列表模式不下载


def test_抓取_下载附件(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import 行业研究

    def fake_抓取_网页源(主题, 来源, max_results, 时间范围):
        return [
            {
                "标题": "光模块行业报告",
                "链接": "https://example.com/report.pdf",
                "来源": "某券商",
                "类型": "report",
                "地区": "中国",
                "发布日期": None,
            }
        ]

    monkeypatch.setattr(行业研究, "_抓取_网页源", fake_抓取_网页源)
    monkeypatch.setattr(行业研究, "_download", lambda link, d: Path(d) / "report.pdf")

    result = _run_fetch(_args(输出目录=str(tmp_path), 仅列表=False, json=True))
    assert result == 0


def test_抓取_yixin链接不尝试下载(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import 行业研究

    def fake_抓取_网页源(主题, 来源, max_results, 时间范围):
        return [
            {
                "标题": "某券商研报",
                "链接": "yixin://report/abc123",
                "来源": "某券商",
                "类型": "report",
                "地区": "中国",
                "发布日期": "2026-06-01",
            }
        ]

    monkeypatch.setattr(行业研究, "_抓取_网页源", fake_抓取_网页源)
    calls = {"download": 0}

    def fake_download(link, d):
        calls["download"] += 1
        return Path(d) / "x.pdf"

    monkeypatch.setattr(行业研究, "_download", fake_download)

    result = _run_fetch(_args(输出目录=str(tmp_path), 仅列表=False))
    assert result == 0
    assert calls["download"] == 0  # yixin:// 元数据链接跳过下载


def test_抓取_json输出结构(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from scripts import 行业研究

    def fake_抓取_网页源(主题, 来源, max_results, 时间范围):
        return [
            {
                "标题": "报告A",
                "链接": "",
                "来源": "某券商",
                "类型": "report",
                "地区": "中国",
                "发布日期": "2026-06-01",
            }
        ]

    monkeypatch.setattr(行业研究, "_抓取_网页源", fake_抓取_网页源)

    result = _run_fetch(_args(输出目录=str(tmp_path), json=True))
    assert result == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["主题"] == "光模块"
    assert data["结果"][0]["标题"] == "报告A"
