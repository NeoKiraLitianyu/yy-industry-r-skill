from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _当前时间() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class 库索引:
    path: Path

    @property
    def 连接(self) -> sqlite3.Connection:
        连接对象 = sqlite3.connect(self.path)
        连接对象.row_factory = sqlite3.Row
        return 连接对象


def _创建来源表(游标: sqlite3.Cursor) -> None:
    游标.execute(
        """
        CREATE TABLE IF NOT EXISTS 来源 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT NOT NULL UNIQUE,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_uri TEXT NOT NULL,
            region TEXT NOT NULL,
            country TEXT,
            currency TEXT,
            language TEXT,
            credibility INTEGER,
            publish_at TEXT,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            notes TEXT
        )
        """
    )


def _创建文档表(游标: sqlite3.Cursor) -> None:
    游标.execute(
        """
        CREATE TABLE IF NOT EXISTS 文档 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            doc_type TEXT NOT NULL,
            raw_path TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_sha256 TEXT NOT NULL,
            simhash_64 TEXT NOT NULL,
            content_sha256 TEXT,
            created_at TEXT NOT NULL,
            parser_version TEXT,
            parse_status TEXT NOT NULL,
            extra JSON,
            UNIQUE(file_sha256),
            FOREIGN KEY(source_id) REFERENCES 来源(id)
        )
        """
    )


def _创建事实表(游标: sqlite3.Cursor) -> None:
    游标.execute(
        """
        CREATE TABLE IF NOT EXISTS 事实 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            fact_key TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            fact_value TEXT NOT NULL,
            unit TEXT,
            time_range TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES 来源(id)
        )
        """
    )


def _创建证据表(游标: sqlite3.Cursor) -> None:
    游标.execute(
        """
        CREATE TABLE IF NOT EXISTS 证据 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id INTEGER NOT NULL,
            doc_id INTEGER NOT NULL,
            quote TEXT NOT NULL,
            page_or_span TEXT,
            confidence INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(fact_id) REFERENCES 事实(id),
            FOREIGN KEY(doc_id) REFERENCES 文档(id)
        )
        """
    )


def _创建验证表(游标: sqlite3.Cursor) -> None:
    游标.execute(
        """
        CREATE TABLE IF NOT EXISTS 验证 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_key TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sources_json TEXT,
            details_json TEXT
        )
        """
    )


def _创建映射表(游标: sqlite3.Cursor) -> None:
    游标.execute(
        """
        CREATE TABLE IF NOT EXISTS 映射 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id INTEGER NOT NULL,
            industry_pack TEXT NOT NULL,
            node TEXT NOT NULL,
            relation TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(fact_id) REFERENCES 事实(id),
            UNIQUE(fact_id, industry_pack, node, relation)
        )
        """
    )


def _创建运行表(游标: sqlite3.Cursor) -> None:
    游标.execute(
        """
        CREATE TABLE IF NOT EXISTS 运行记录 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage TEXT NOT NULL,
            command TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_ms INTEGER
        )
        """
        )


def _创建索引(游标: sqlite3.Cursor) -> None:
    游标.execute("CREATE INDEX IF NOT EXISTS idx_文档_file_sha256 ON 文档(file_sha256)")
    游标.execute("CREATE INDEX IF NOT EXISTS idx_文档_source_id ON 文档(source_id)")
    游标.execute("CREATE INDEX IF NOT EXISTS idx_事实_fact_key ON 事实(fact_key)")
    游标.execute("CREATE INDEX IF NOT EXISTS idx_验证_fact_key ON 验证(fact_key)")


def 初始化行业索引(sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sqlite_path) as connection:
        cursor = connection.cursor()
        _创建来源表(cursor)
        _创建文档表(cursor)
        _创建事实表(cursor)
        _创建证据表(cursor)
        _创建验证表(cursor)
        _创建映射表(cursor)
        _创建运行表(cursor)
        _创建索引(cursor)
        connection.commit()


def 查找同指纹(路径: Path, 文件指纹: str, 语义指纹: str) -> list[sqlite3.Row]:
    库 = 库索引(路径)
    with 库.连接 as connection:
        行 = connection.execute(
            """
            SELECT id, filename, raw_path, simhash_64, file_sha256
            FROM 文档
            WHERE file_sha256 = ? OR simhash_64 = ?
            """,
            (文件指纹, 语义指纹),
        ).fetchall()
    return list(行)


def 查找同文件指纹(路径: Path, 文件指纹: str) -> bool:
    库 = 库索引(路径)
    with 库.连接 as connection:
        row = connection.execute("SELECT COUNT(1) FROM 文档 WHERE file_sha256 = ?", (文件指纹,)).fetchone()
    return bool(row and row[0] > 0)


def 取来源名(库路径: Path, 来源ID: int) -> str:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        row = cursor.execute("SELECT source_name FROM 来源 WHERE id = ?", (来源ID,)).fetchone()
        return row[0] if row else ""


def 写入来源(
    库路径: Path,
    source_key: str,
    source_name: str,
    source_type: str,
    source_uri: str,
    region: str,
    source_country: Optional[str] = None,
    language: Optional[str] = None,
    credibility: int = 5,
    title: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    with sqlite3.connect(库路径) as connection:
        now = _当前时间()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO 来源 (
                source_key, source_name, source_type, source_uri, region, country, language, credibility,
                publish_at, title, created_at, updated_at, notes, currency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(source_key) DO UPDATE SET
                updated_at=excluded.updated_at,
                source_name=excluded.source_name,
                source_uri=excluded.source_uri,
                region=excluded.region,
                title=excluded.title,
                notes=excluded.notes
            """,
            (
                source_key,
                source_name,
                source_type,
                source_uri,
                region,
                source_country,
                language,
                credibility,
                None,
                title,
                now,
                now,
                notes,
            ),
        )
        return cursor.execute("SELECT id FROM 来源 WHERE source_key = ?", (source_key,)).fetchone()[0]


def 写入文档(
    库路径: Path,
    source_id: int,
    doc_type: str,
    raw_path: Path,
    filename: str,
    file_sha256: str,
    simhash_64: str,
    parse_status: str,
    content_sha256: Optional[str] = None,
    extra: Optional[dict[str, object]] = None,
    parser_version: str = "0.1.0",
) -> int:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        now = _当前时间()
        cursor.execute(
            """
            INSERT OR IGNORE INTO 文档 (
                source_id, doc_type, raw_path, filename, file_sha256, simhash_64,
                content_sha256, created_at, parser_version, parse_status, extra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                doc_type,
                str(raw_path),
                filename,
                file_sha256,
                simhash_64,
                content_sha256,
                now,
                parser_version,
                parse_status,
                None if extra is None else json.dumps(extra, ensure_ascii=False),
            ),
        )
        row_id = cursor.lastrowid
        if row_id is None:
            row_id = cursor.execute(
                "SELECT id FROM 文档 WHERE file_sha256 = ?", (file_sha256,)
            ).fetchone()[0]
        return row_id


def 写入证据(
    库路径: Path,
    fact_id: int,
    doc_id: int,
    quote: str,
    confidence: int = 5,
    page_or_span: str | None = None,
) -> int:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        now = _当前时间()
        cursor.execute(
            """
            INSERT INTO 证据 (fact_id, doc_id, quote, page_or_span, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (fact_id, doc_id, quote, page_or_span, confidence, now),
        )
        return cursor.lastrowid


def 写入事实(
    库路径: Path,
    source_id: int,
    fact_key: str,
    fact_type: str,
    fact_value: str,
    unit: Optional[str] = None,
    time_range: Optional[str] = None,
) -> int:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        now = _当前时间()
        cursor.execute(
            """
            INSERT INTO 事实 (source_id, fact_key, fact_type, fact_value, unit, time_range, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                fact_key,
                fact_type,
                fact_value,
                unit,
                time_range,
                now,
            ),
        )
        return cursor.lastrowid


def 写入映射(
    库路径: Path,
    fact_id: int,
    industry_pack: str,
    node: str,
    relation: str,
    confidence: int = 5,
) -> None:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        now = _当前时间()
        cursor.execute(
            """
            INSERT OR IGNORE INTO 映射 (fact_id, industry_pack, node, relation, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (fact_id, industry_pack, node, relation, confidence, now),
        )


def 写入来源统计(库路径: Path, command: str, status: str, detail: str) -> None:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        now = _当前时间()
        cursor.execute(
            """
            INSERT INTO 运行记录 (stage, command, status, detail, started_at, finished_at, duration_ms)
            VALUES ('metadata', ?, ?, ?, ?, ?, ?)
            """,
            (command, status, detail, now, now, 0),
        )


def 写入运行记录(库路径: Path, stage: str, command: str, status: str, detail: str) -> None:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        now = _当前时间()
        cursor.execute(
            """
            INSERT INTO 运行记录 (stage, command, status, detail, started_at, finished_at, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (stage, command, status, detail, now, now, 0),
        )


def 统计来源数(库路径: Path) -> dict[str, int]:
    with sqlite3.connect(库路径) as connection:
        cursor = connection.cursor()
        source_count = cursor.execute("SELECT COUNT(1) FROM 来源").fetchone()[0]
        doc_count = cursor.execute("SELECT COUNT(1) FROM 文档").fetchone()[0]
        fact_count = cursor.execute("SELECT COUNT(1) FROM 事实").fetchone()[0]
        validate_count = cursor.execute("SELECT COUNT(1) FROM 验证").fetchone()[0]
        source_type_rows = cursor.execute("SELECT source_type, COUNT(1) AS c FROM 来源 GROUP BY source_type").fetchall()
        type_count = {str(r[0]): int(r[1]) for r in source_type_rows}
        return {
            "sources": int(source_count),
            "documents": int(doc_count),
            "facts": int(fact_count),
            "validations": int(validate_count),
            **{f"source_type_{k}": v for k, v in type_count.items()},
        }
