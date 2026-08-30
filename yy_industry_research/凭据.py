from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path


允许凭据键: tuple[str, ...] = (
    "YIXIN_API_KEY",
    "TDX_MCP_URL",
    "TDX_MCP_API_KEY",
    "TDX_MCP_ENABLED",
    "TDX_MCP_DAILY_BUDGET",
)


def _技能根目录(skill_root: Path | None) -> Path:
    return Path(skill_root).resolve() if skill_root else Path(__file__).resolve().parents[1]


def _过滤凭据(items: Mapping[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in 允许凭据键:
        if key not in items:
            continue
        value = str(items[key]).strip().strip("\"'")
        if value:
            values[key] = value
    return values


def _读取_env(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    raw: dict[str, object] = {}
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        raw[key.strip()] = value
    return _过滤凭据(raw)


def 读取NeoStar连接配置(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}
    return _读取_env(Path(path))


def _发现NeoStar旧配置(skill_root: Path) -> tuple[Path, ...]:
    if skill_root.parent.name != "skills":
        return ()
    candidate = (skill_root.parent.parent / "_root_config" / ".env").resolve()
    return (candidate,) if candidate.is_file() else ()


def _读取旧Yixin密钥() -> str:
    candidates = (
        Path.home() / ".workbuddy" / "secrets" / "yixin-api" / "api-key.json",
        Path.home() / ".config" / "yixin-api" / "api-key.json",
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        value = str(data.get("api_key", "")).strip()
        if value:
            return value
    return ""


def 读取凭据配置(skill_root: Path | None = None, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    root = _技能根目录(skill_root)
    values = _读取_env(root / "config" / "credentials.env")
    runtime = _过滤凭据(dict(environ) if environ is not None else os.environ)
    values.update(runtime)
    if not values.get("YIXIN_API_KEY"):
        legacy_yixin_key = _读取旧Yixin密钥()
        if legacy_yixin_key:
            values["YIXIN_API_KEY"] = legacy_yixin_key
    for path in _发现NeoStar旧配置(root):
        for key, value in 读取NeoStar连接配置(path).items():
            values.setdefault(key, value)
    return {key: values[key] for key in 允许凭据键 if values.get(key)}


def 发现可分发凭据(skill_root: Path | None = None, environ: Mapping[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    values = 读取凭据配置(skill_root=skill_root, environ=environ)
    missing = [key for key in 允许凭据键 if key not in values]
    return values, missing
