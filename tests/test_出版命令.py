from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "industry-packs" / "半导体膜材"
SCRIPT = ROOT / "scripts" / "生成出版报告.py"


def _构造可出版资料库(tmp_path: Path) -> Path:
    library = tmp_path / "半导体膜材行业库"
    report_dir = library / "研究报告"
    raw_dir = library / "原始资料" / "归档"
    report_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    facts = json.loads((PACK / "curated_facts.json").read_text(encoding="utf-8"))["facts"]
    uris = sorted({str(uri) for fact in facts for uri in fact.get("source_uris", []) if str(uri)})
    catalog = []
    for index, uri in enumerate(uris, start=1):
        raw = raw_dir / f"source-{index:03d}.txt"
        raw.write_text(f"archived source: {uri}", encoding="utf-8")
        host = (urlparse(uri).hostname or f"source-{index}").removeprefix("www.")
        catalog.append(
            {
                "source_id": index,
                "source_name": host,
                "source_type": "监管/协会/公司一手来源",
                "source_uri": uri,
                "region": "中国" if "cninfo.com.cn" in host or host.endswith("gov.cn") else "全球",
                "language": "zh" if "cninfo.com.cn" in host else "en",
                "credibility": 9,
                "title": host,
                "documents": [
                    {
                        "filename": raw.name,
                        "raw_path": str(raw),
                        "doc_type": "text",
                        "parse_status": "success",
                    }
                ],
            }
        )
    run = {"行业": "半导体膜材", "资料库": str(library), "source_catalog": catalog, "map_summary": []}
    (report_dir / "run_20260830_000000.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return library


def test_publication_cli_emits_complete_artifact_set(tmp_path: Path) -> None:
    library = _构造可出版资料库(tmp_path)
    output = tmp_path / "出版物"
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--资料库",
            str(library),
            "--行业",
            "半导体膜材",
            "--输出目录",
            str(output),
            "--生成PDF",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )

    if result.returncode != 0 and os.name == "nt" and "2147483651" in (result.stderr or ""):
        pytest.skip("当前受限 Windows 作业阻止 Edge 沙箱子进程；出版流程其余产物另行覆盖")
    assert result.returncode == 0, result.stderr or result.stdout
    assert len(list(output.glob("*.md"))) == 1
    assert len(list(output.glob("*.html"))) == 1
    assert len(list(output.glob("*.pdf"))) == 1
    assert len(list(output.glob("*.charts.json"))) == 1
    assert len(list(output.glob("*.evidence.json"))) == 1
    receipt = json.loads(next(output.glob("*.receipt.json")).read_text(encoding="utf-8"))
    assert receipt["pdf"]["valid"] is True, receipt["pdf"]
    assert receipt["pdf"]["pages"] >= 20
    assert receipt["charts"] >= 12
    assert receipt["facts"] >= 100
    assert len(list(output.glob("*_charts/*.svg"))) >= 12
