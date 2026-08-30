from __future__ import annotations

import csv
import shutil
from datetime import datetime
from pathlib import Path

from .指纹 import 文件sha256


def _safe_target_dir(root: Path, region: str) -> Path:
    region_map = {
        "中国": root / "原始资料" / "中国",
        "全球": root / "原始资料" / "全球",
    }
    return region_map.get(region, root / "原始资料" / "用户导入")


def _safe_filename(name: str) -> str:
    name = "".join(ch if ch.isalnum() or ch in "._-()[]中文世界国际" else "_" for ch in name)
    return name[:180].strip("._- ")


def 归档原始文件(
    库根目录: Path,
    来源文件: Path,
    行业: str,
    region: str,
    source_name: str,
    source_uri: str,
) -> Path:
    源路径 = Path(来源文件).resolve()
    if not 源路径.is_file():
        raise FileNotFoundError(f"原始文件不存在: {源路径}")

    目标目录 = _safe_target_dir(库根目录, region)
    目标目录.mkdir(parents=True, exist_ok=True)

    时间戳 = datetime.now().strftime("%Y%m%d_%H%M%S")
    文件名 = f"{时间戳}_{行业}_{source_name}_{源路径.name}"
    清洗 = _safe_filename(文件名)
    if not 清洗:
        清洗 = "research_file"
    目标路径 = 目标目录 / 清洗
    if 目标路径.exists():
        i = 1
        while True:
            alt = 目标路径.with_name(f"{目标路径.stem}_{i}{目标路径.suffix}")
            if not alt.exists():
                目标路径 = alt
                break
            i += 1
    shutil.copy2(源路径, 目标路径)

    (库根目录 / "来源目录").mkdir(parents=True, exist_ok=True)
    目录文件 = 库根目录 / "来源目录" / "原始来源.csv"
    if not 目录文件.exists():
        目录文件.write_text("file_name,sha256,source_uri,region,industry,archived_at\n", encoding="utf-8")
    sha = 文件sha256(源路径.read_bytes())
    with 目录文件.open("a", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                目标路径.name,
                sha,
                source_uri,
                region,
                行业,
                datetime.now().isoformat(timespec="seconds"),
            ]
        )
    return 目标路径
