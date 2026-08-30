from __future__ import annotations

import json
from pathlib import Path

import yy_industry_research.数据适配器 as 数据适配器
import yy_industry_research.凭据 as 凭据模块
from yy_industry_research.凭据 import 允许凭据键, 发现可分发凭据, 读取凭据配置


def _创建技能根目录(tmp_path: Path) -> Path:
    skill_root = tmp_path / "repo" / "skills" / "yy-industry-r-skill"
    (skill_root / "config").mkdir(parents=True)
    return skill_root


def _写入旧Yixin密钥(home_dir: Path, value: str, relative_path: str = ".workbuddy/secrets/yixin-api/api-key.json") -> None:
    key_path = home_dir / relative_path
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps({"api_key": value}), encoding="utf-8")


def test_skill_credentials_are_defaults_and_environment_overrides(tmp_path):
    skill_root = _创建技能根目录(tmp_path)
    (skill_root / "config" / "credentials.env").write_text(
        "YIXIN_API_KEY=friend\nTDX_MCP_ENABLED=1\n",
        encoding="utf-8",
    )

    actual = 读取凭据配置(skill_root, {"YIXIN_API_KEY": "runtime"})

    assert actual["YIXIN_API_KEY"] == "runtime"
    assert actual["TDX_MCP_ENABLED"] == "1"


def test_loader_ignores_unapproved_secrets(tmp_path):
    skill_root = _创建技能根目录(tmp_path)
    (skill_root / "config" / "credentials.env").write_text(
        "AWS_SECRET_ACCESS_KEY=nope\nYIXIN_API_KEY=ok\n",
        encoding="utf-8",
    )

    assert 读取凭据配置(skill_root, {}) == {"YIXIN_API_KEY": "ok"}


def test_loader_backfills_missing_values_from_neostar_root_config(tmp_path):
    skill_root = _创建技能根目录(tmp_path)
    (skill_root / "config" / "credentials.env").write_text(
        "TDX_MCP_ENABLED=0\n",
        encoding="utf-8",
    )
    legacy_env = skill_root.parents[1] / "_root_config" / ".env"
    legacy_env.parent.mkdir(parents=True)
    legacy_env.write_text(
        "TDX_MCP_API_KEY=legacy-key\nTDX_MCP_ENABLED=1\nOTHER_SECRET=never\n",
        encoding="utf-8",
    )

    actual = 读取凭据配置(skill_root, {})

    assert actual["TDX_MCP_API_KEY"] == "legacy-key"
    assert actual["TDX_MCP_ENABLED"] == "0"
    assert "OTHER_SECRET" not in actual


def test_discover_shippable_credentials_returns_values_and_missing_keys(tmp_path):
    skill_root = _创建技能根目录(tmp_path)
    (skill_root / "config" / "credentials.env").write_text(
        "YIXIN_API_KEY=friend\n",
        encoding="utf-8",
    )
    legacy_env = skill_root.parents[1] / "_root_config" / ".env"
    legacy_env.parent.mkdir(parents=True)
    legacy_env.write_text(
        "TDX_MCP_API_KEY=legacy-key\n",
        encoding="utf-8",
    )

    actual, missing = 发现可分发凭据(
        skill_root,
        {
            "TDX_MCP_ENABLED": "1",
            "TDX_MCP_URL": "https://tdx.example/mcp",
        },
    )

    assert tuple(actual) == (
        "YIXIN_API_KEY",
        "TDX_MCP_URL",
        "TDX_MCP_API_KEY",
        "TDX_MCP_ENABLED",
    )
    assert missing == ["TDX_MCP_DAILY_BUDGET"]
    assert set(actual).issubset(set(允许凭据键))


def test_loader_backfills_missing_yixin_key_from_legacy_json(tmp_path, monkeypatch):
    skill_root = _创建技能根目录(tmp_path)
    home_dir = tmp_path / "home"
    _写入旧Yixin密钥(home_dir, "legacy-json-key")
    monkeypatch.delenv("YIXIN_API_KEY", raising=False)
    monkeypatch.setattr(凭据模块.Path, "home", lambda: home_dir)

    actual = 读取凭据配置(skill_root, {})

    assert actual["YIXIN_API_KEY"] == "legacy-json-key"


def test_yixin_reader_reads_legacy_json_without_monkeypatching_loader(tmp_path, monkeypatch):
    skill_root = Path(数据适配器.__file__).resolve().parents[1]
    credentials_file = skill_root / "config" / "credentials.env"
    original_contents = credentials_file.read_text(encoding="utf-8") if credentials_file.exists() else None
    home_dir = tmp_path / "home"
    _写入旧Yixin密钥(home_dir, "legacy-json-key")
    monkeypatch.delenv("YIXIN_API_KEY", raising=False)
    monkeypatch.setattr(凭据模块.Path, "home", lambda: home_dir)
    credentials_file.parent.mkdir(parents=True, exist_ok=True)
    credentials_file.write_text("", encoding="utf-8")
    try:
        assert 数据适配器._读取Yixin密钥() == "legacy-json-key"
    finally:
        if original_contents is None:
            credentials_file.unlink(missing_ok=True)
        else:
            credentials_file.write_text(original_contents, encoding="utf-8")


def test_tdx_client_reads_loaded_credentials(monkeypatch):
    monkeypatch.setattr(
        数据适配器,
        "读取凭据配置",
        lambda skill_root=None, environ=None: {
            "TDX_MCP_URL": "https://tdx.example/mcp",
            "TDX_MCP_API_KEY": "skill-token",
        },
    )

    client = 数据适配器._TDXMcpClient()

    assert client.url == "https://tdx.example/mcp"
    assert client.key == "skill-token"


def test_tdx_adapter_enabled_defaults_from_loaded_credentials(monkeypatch):
    monkeypatch.setattr(
        数据适配器,
        "读取凭据配置",
        lambda skill_root=None, environ=None: {"TDX_MCP_ENABLED": "1"},
    )

    adapter = 数据适配器.TDX适配器(client=object())

    assert adapter.enabled is True
