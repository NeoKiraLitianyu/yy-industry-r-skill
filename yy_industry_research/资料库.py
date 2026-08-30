from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .配置 import 当前时间
from .模型 import 研究配置


中文目录 = (
    "配置",
    "原始资料/中国",
    "原始资料/全球",
    "原始资料/用户导入",
    "原始资料/受限来源元数据",
    "解析文本/正文",
    "解析文本/表格",
    "解析文本/解析失败",
    "来源目录",
    "结构化事实",
    "验证与冲突",
    "行业图谱",
    "研究报告",
    "运行记录",
)


@dataclass(frozen=True, slots=True)
class 行业资料库:
    根目录: Path

    @property
    def 配置文件(self) -> Path:
        return self.根目录 / "配置" / "行业配置.json"

    @property
    def 索引文件(self) -> Path:
        return self.根目录 / "行业索引.sqlite"


def _原子写入_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".临时")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _初始化索引(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS 元数据 (
                键 TEXT PRIMARY KEY,
                值 TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO 元数据(键, 值) VALUES('数据库版本', '1')"
        )


def 初始化资料库(
    root: str | Path,
    industry: str,
    pack_dir: str | Path | None,
) -> Path:
    industry = industry.strip()
    if not industry:
        raise ValueError("行业名称不能为空")

    root_path = Path(root).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    for relative in 中文目录:
        (root_path / relative).mkdir(parents=True, exist_ok=True)

    library = 行业资料库(root_path)
    if not library.配置文件.exists():
        config = 研究配置(
            行业=industry,
            创建时间=当前时间(),
            行业包路径=str(Path(pack_dir).resolve()) if pack_dir else "",
        )
        _原子写入_json(library.配置文件, config.转字典())

    _初始化索引(library.索引文件)
    return root_path
