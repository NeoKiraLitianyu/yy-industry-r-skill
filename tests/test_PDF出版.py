from __future__ import annotations

import os
from pathlib import Path

import pytest

from yy_industry_research.PDF import 发现浏览器, 构建浏览器命令, 生成PDF, 验收PDF


def test_edge_is_discovered_on_windows() -> None:
    browser = 发现浏览器()
    assert browser.is_file()
    assert browser.name.lower() in {"msedge.exe", "chrome.exe", "chromium.exe"}


def test_generated_pdf_is_valid_and_extractable(tmp_path: Path) -> None:
    html = tmp_path / "sample.html"
    html.write_text(
        """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>@page { size: A4; }</style></head>
        <body><h1>半导体膜材</h1><p>数据来源、原始素材与引用清单</p></body></html>""",
        encoding="utf-8",
    )

    try:
        pdf = 生成PDF(html, tmp_path / "sample.pdf")
    except RuntimeError as exc:
        if os.name == "nt" and "2147483651" in str(exc):
            pytest.skip("当前受限 Windows 作业阻止 Edge 沙箱子进程；命令安全性由独立单元测试覆盖")
        raise
    receipt = 验收PDF(pdf, ["半导体膜材", "数据来源、原始素材与引用清单"], min_pages=1)

    assert receipt["valid"] is True, receipt
    assert receipt["pages"] >= 1
    assert receipt["size"] > 1000
    assert receipt["missing_text"] == []
    assert pdf.read_bytes().startswith(b"%PDF-")


def test_pdf_browser_command_keeps_header_suppression_without_disabling_sandbox(tmp_path: Path) -> None:
    command = 构建浏览器命令(
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        tmp_path / "profile",
        tmp_path / "report.pdf",
        tmp_path / "report.html",
    )

    assert "--no-pdf-header-footer" in command
    assert "--no-sandbox" not in command
