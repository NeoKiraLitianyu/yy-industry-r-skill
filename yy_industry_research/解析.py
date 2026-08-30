from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import openpyxl  # type: ignore
from bs4 import BeautifulSoup  # type: ignore


def 解析纯文本(路径: Path) -> str:
    return 路径.read_text(encoding="utf-8", errors="ignore")


def _parse_html_to_text(内容: str) -> str:
    return BeautifulSoup(内容, "html.parser").get_text("\\n", strip=True)


def 解析_html(路径: Path) -> str:
    return _parse_html_to_text(路径.read_text(encoding="utf-8", errors="ignore"))


def 解析_pdf(路径: Path) -> str:
    try:
        import pdfplumber  # type: ignore
        文本块: List[str] = []
        with pdfplumber.open(路径) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    文本块.append(text)
        return "\\n\\n".join(文本块)
    except Exception as exc:
        raise RuntimeError(f"PDF 解析失败: {exc}") from exc


def 解析_xlsx(路径: Path) -> str:
    try:
        wb = openpyxl.load_workbook(路径, data_only=True, read_only=True)
        行表: List[str] = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                行: List[str] = [str(x) for x in row if x is not None]
                if 行:
                    行表.append("\t".join(行))
        return "\\n".join(行表)
    except Exception as exc:
        raise RuntimeError(f"XLSX 解析失败: {exc}") from exc


def 导出表格_csv(文本块: str) -> str:
    return "\n".join([line for line in 文本块.splitlines() if line.strip()])


def 解析文件(路径: Path) -> Dict[str, str]:
    后缀 = 路径.suffix.lower()
    if 后缀 == ".pdf":
        return {"doc_type": "pdf", "text": 解析_pdf(路径)}
    if 后缀 in {".xlsx", ".xls"}:
        return {"doc_type": "xlsx", "text": 解析_xlsx(路径)}
    if 后缀 in {".html", ".htm"}:
        return {"doc_type": "html", "text": 解析_html(路径)}
    if 后缀 == ".csv":
        return {"doc_type": "csv", "text": 导出表格_csv(路径.read_text(encoding="utf-8", errors="ignore"))}
    if 后缀 in {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".log"}:
        return {"doc_type": "text", "text": 解析纯文本(路径)}
    return {"doc_type": "text", "text": 解析纯文本(路径)}
