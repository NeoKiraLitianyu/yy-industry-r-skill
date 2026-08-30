from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "打包技能.py"
MANIFEST_PATH = "yy-industry-r-skill/package-manifest.json"
LEGACY_MANIFEST_PATH = "yy-industry-r-skill/PACKAGE_MANIFEST.json"
CREDENTIALS_PATH = "yy-industry-r-skill/config/credentials.env"
MARKER = "secret-marker-for-task-2"


def _load_module():
    spec = importlib.util.spec_from_file_location("task2_packaging", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载打包脚本: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _allowlisted_values() -> dict[str, str]:
    return {
        "YIXIN_API_KEY": f"{MARKER}-1",
        "TDX_MCP_URL": "https://example.invalid/mcp",
        "TDX_MCP_API_KEY": f"{MARKER}-2",
        "TDX_MCP_ENABLED": f"{MARKER}-3",
        "TDX_MCP_DAILY_BUDGET": f"{MARKER}-4",
    }


def test_default_package_excludes_credentials(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setenv("YIXIN_API_KEY", MARKER)

    result = module.构建技能包(SKILL_ROOT, tmp_path / "safe.zip")

    with ZipFile(result["path"]) as archive:
        names = archive.namelist()
        assert CREDENTIALS_PATH not in names
        assert MANIFEST_PATH in names
        assert LEGACY_MANIFEST_PATH in names
        manifest = archive.read(MANIFEST_PATH).decode("utf-8")
        legacy_manifest = archive.read(LEGACY_MANIFEST_PATH).decode("utf-8")

    assert MARKER not in manifest
    assert MARKER not in legacy_manifest
    assert manifest == legacy_manifest
    assert result["contains_credentials"] is False


def test_plaintext_package_requires_double_confirmation(tmp_path):
    module = _load_module()

    with pytest.raises(PermissionError):
        module.构建技能包(
            SKILL_ROOT,
            tmp_path / "friend.zip",
            include_plaintext_credentials=True,
        )


def test_plaintext_package_rejects_confirm_without_include(tmp_path):
    module = _load_module()

    with pytest.raises(PermissionError, match="确认明文分发"):
        module.构建技能包(
            SKILL_ROOT,
            tmp_path / "friend.zip",
            confirm_plaintext_distribution=True,
        )


def test_plaintext_package_rejects_missing_allowlisted_keys_without_partial_archive(tmp_path, monkeypatch):
    module = _load_module()
    partial = _allowlisted_values()
    missing_key = "TDX_MCP_DAILY_BUDGET"
    present_value = partial.pop("YIXIN_API_KEY")
    monkeypatch.setattr(
        module,
        "发现可分发凭据",
        lambda skill_root=None, environ=None: (partial, [missing_key]),
    )

    with pytest.raises(ValueError, match=missing_key) as exc_info:
        module.构建技能包(
            SKILL_ROOT,
            tmp_path / "friend.zip",
            include_plaintext_credentials=True,
            confirm_plaintext_distribution=True,
        )

    assert present_value not in str(exc_info.value)
    assert not (tmp_path / "friend.zip").exists()


def test_plaintext_package_rejects_control_characters_without_echoing_values(tmp_path, monkeypatch):
    module = _load_module()
    invalid_key = "TDX_MCP_API_KEY"
    invalid_value = f"{MARKER}-line1\n{MARKER}-line2"
    monkeypatch.setattr(
        module,
        "发现可分发凭据",
        lambda skill_root=None, environ=None: (
            {**_allowlisted_values(), invalid_key: invalid_value},
            [],
        ),
    )

    with pytest.raises(ValueError, match=invalid_key) as exc_info:
        module.构建技能包(
            SKILL_ROOT,
            tmp_path / "friend.zip",
            include_plaintext_credentials=True,
            confirm_plaintext_distribution=True,
        )

    assert MARKER not in str(exc_info.value)
    assert not (tmp_path / "friend.zip").exists()


def test_plaintext_package_contains_allowlisted_values_without_manifest_leak(tmp_path, monkeypatch):
    module = _load_module()
    allowlisted = _allowlisted_values()
    for key, value in allowlisted.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-copy")

    result = module.构建技能包(
        SKILL_ROOT,
        tmp_path / "friend.zip",
        include_plaintext_credentials=True,
        confirm_plaintext_distribution=True,
    )

    with ZipFile(result["path"]) as archive:
        names = archive.namelist()
        assert CREDENTIALS_PATH in names
        credentials = archive.read(CREDENTIALS_PATH).decode("utf-8")
        manifest = archive.read(MANIFEST_PATH).decode("utf-8")
        legacy_manifest = archive.read(LEGACY_MANIFEST_PATH).decode("utf-8")

    lines = [line for line in credentials.splitlines() if line.strip()]
    assert len(lines) == 5
    for key, value in allowlisted.items():
        assert f"{key}={value}" in credentials
        assert value not in manifest
        assert value not in legacy_manifest
    assert "AWS_SECRET_ACCESS_KEY" not in credentials
    assert "must-not-copy" not in credentials
    assert manifest == legacy_manifest
    assert result["contains_credentials"] is True


def test_打包脚本可从Skill目录直接执行(tmp_path: Path) -> None:
    output = tmp_path / "safe.zip"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--输出", str(output)],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert output.is_file()


def test_safe_package_uses_strict_product_allowlist(tmp_path: Path) -> None:
    module = _load_module()
    skill = tmp_path / "skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "yy_industry_research").mkdir()
    (skill / "SKILL.md").write_text("skill", encoding="utf-8")
    (skill / "README.md").write_text("readme", encoding="utf-8")
    (skill / "scripts" / "行业研究.py").write_text("print('ok')", encoding="utf-8")
    (skill / "yy_industry_research" / "核心.py").write_text("VALUE = 1", encoding="utf-8")
    (skill / "secret.log").write_text(MARKER, encoding="utf-8")
    (skill / "unknown.pem").write_text(MARKER, encoding="utf-8")

    result = module.构建技能包(skill, tmp_path / "safe.zip")

    with ZipFile(result["path"]) as archive:
        names = archive.namelist()
        payload = b"\n".join(archive.read(name) for name in names)
    assert "yy-industry-r-skill/yy_industry_research/核心.py" in names
    assert "yy-industry-r-skill/secret.log" not in names
    assert "yy-industry-r-skill/unknown.pem" not in names
    assert MARKER.encode() not in payload


def test_safe_package_rejects_symlink_entries(tmp_path: Path) -> None:
    module = _load_module()
    skill = tmp_path / "skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "assets").mkdir()
    (skill / "SKILL.md").write_text("skill", encoding="utf-8")
    (skill / "README.md").write_text("readme", encoding="utf-8")
    (skill / "scripts" / "行业研究.py").write_text("print('ok')", encoding="utf-8")
    target = tmp_path / "outside.txt"
    target.write_text(MARKER, encoding="utf-8")
    link = skill / "assets" / "linked.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("当前 Windows 权限不允许创建符号链接")

    result = module.构建技能包(skill, tmp_path / "safe.zip")

    with ZipFile(result["path"]) as archive:
        names = archive.namelist()
    assert "yy-industry-r-skill/assets/linked.txt" not in names
