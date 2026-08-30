from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence


def 发现浏览器(explicit: str | Path | None = None) -> Path:
    """发现支持无头打印的 Edge/Chrome 浏览器。"""

    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if not root:
            continue
        base = Path(root)
        candidates.extend(
            [
                base / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                base / "Google" / "Chrome" / "Application" / "chrome.exe",
                base / "Chromium" / "Application" / "chromium.exe",
            ]
        )
    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ]
    )
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    if explicit is not None:
        raise FileNotFoundError(f"指定浏览器不存在：{Path(explicit)}")
    raise FileNotFoundError("未找到 Microsoft Edge、Google Chrome 或 Chromium")


def 构建浏览器命令(
    browser_path: str | Path,
    profile: str | Path,
    pdf_path: str | Path,
    html_path: str | Path,
) -> list[str]:
    """构造保留浏览器沙箱的本地无头打印命令。"""

    return [
        str(Path(browser_path)),
        "--headless",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--no-first-run",
        "--no-default-browser-check",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=3000",
        f"--user-data-dir={Path(profile)}",
        f"--print-to-pdf={Path(pdf_path)}",
        "--no-pdf-header-footer",
        Path(html_path).resolve().as_uri(),
    ]


def _运行浏览器(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        timeout=timeout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def 生成PDF(
    html: str | Path,
    pdf: str | Path,
    browser: str | Path | None = None,
    timeout: int = 120,
) -> Path:
    """使用 Chromium 系浏览器将本地自包含 HTML 打印为 PDF。"""

    html_path = Path(html).resolve()
    pdf_path = Path(pdf).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML 文件不存在：{html_path}")
    if timeout <= 0:
        raise ValueError("timeout 必须为正整数")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()
    browser_path = 发现浏览器(browser)

    with tempfile.TemporaryDirectory(prefix=".edge-profile-", dir=pdf_path.parent, ignore_cleanup_errors=True) as profile:
        command = 构建浏览器命令(browser_path, profile, pdf_path, html_path)
        completed = _运行浏览器(command, timeout)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "浏览器未返回错误详情").strip()
        raise RuntimeError(f"浏览器生成 PDF 失败（退出码 {completed.returncode}）：{message[:500]}")
    if not pdf_path.is_file() or not pdf_path.read_bytes()[:5] == b"%PDF-":
        raise RuntimeError("浏览器返回成功，但未生成有效 PDF 文件头")
    return pdf_path


def _抽取PDF文本(pdf_path: Path) -> list[tuple[int, str, str]]:
    errors: list[str] = []
    candidates: list[tuple[int, str, str]] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        candidates.append((len(reader.pages), text, "pypdf"))
    except Exception as exc:  # pragma: no cover - optional parser depends on environment
        errors.append(f"pypdf:{type(exc).__name__}")
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(str(pdf_path))
        try:
            pages_text: list[str] = []
            for page in document:
                text_page = page.get_textpage()
                try:
                    pages_text.append(text_page.get_text_range())
                finally:
                    text_page.close()
                    page.close()
            candidates.append((len(document), "\n".join(pages_text), "pypdfium2"))
        finally:
            document.close()
    except Exception as exc:  # pragma: no cover - optional parser depends on environment
        errors.append(f"pypdfium2:{type(exc).__name__}")
    try:
        import fitz

        document = fitz.open(str(pdf_path))
        try:
            text = "\n".join(page.get_text("text") for page in document)
            candidates.append((document.page_count, text, "fitz"))
        finally:
            document.close()
    except Exception as exc:  # pragma: no cover - fallback depends on environment
        errors.append(f"fitz:{type(exc).__name__}")
    if not candidates:
        raise RuntimeError("无法抽取 PDF 文本；" + "；".join(errors))
    return candidates


def _规范文本(value: str) -> str:
    return "".join(str(value).replace("\u200b", "").replace("\ufeff", "").split())


def 验收PDF(
    pdf: str | Path,
    required_text: Sequence[str],
    min_pages: int = 20,
) -> dict[str, Any]:
    """检查 PDF 文件头、页数、体积和可抽取的必需文本。"""

    pdf_path = Path(pdf).resolve()
    if min_pages < 1:
        raise ValueError("min_pages 必须至少为1")
    result: dict[str, Any] = {
        "valid": False,
        "pages": 0,
        "size": pdf_path.stat().st_size if pdf_path.is_file() else 0,
        "missing_text": list(required_text),
        "parser": "",
        "path": str(pdf_path),
    }
    if not pdf_path.is_file() or pdf_path.read_bytes()[:5] != b"%PDF-":
        result["error"] = "PDF 文件不存在或文件头无效"
        return result
    try:
        candidates = _抽取PDF文本(pdf_path)
    except RuntimeError as exc:
        result["error"] = str(exc)
        return result
    ranked: list[tuple[int, int, str, list[str]]] = []
    for pages, text, parser in candidates:
        normalized = _规范文本(text)
        missing = [item for item in required_text if _规范文本(item) not in normalized]
        ranked.append((len(missing), -len(normalized), parser, missing))
    missing_count, _negative_text_length, parser, missing = min(ranked)
    pages = max(item[0] for item in candidates)
    result.update(
        {
            "pages": pages,
            "missing_text": missing,
            "parser": parser,
            "valid": pages >= min_pages and result["size"] > 1000 and missing_count == 0,
        }
    )
    if pages < min_pages:
        result["error"] = f"页数不足：{pages} < {min_pages}"
    elif missing:
        result["error"] = "缺少必需文本"
    return result
