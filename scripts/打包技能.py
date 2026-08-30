#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


根目录 = Path(__file__).resolve().parents[1]
if str(根目录) not in sys.path:
    sys.path.insert(0, str(根目录))

from yy_industry_research.凭据 import 发现可分发凭据, 允许凭据键
from yy_industry_research.配置 import 版本


允许顶层文件 = {"SKILL.md", "README.md", "LICENSE", "requirements.txt"}
允许产品目录 = {
    "agents",
    "assets",
    "yy_industry_research",
    "industry-packs",
    "references",
    "scripts",
    "templates",
}
允许产品后缀 = {".py", ".md", ".json", ".yaml", ".yml", ".css", ".html", ".txt", ".csv"}
MANIFEST_PATH = "yy-industry-r-skill/package-manifest.json"
LEGACY_MANIFEST_PATH = "yy-industry-r-skill/PACKAGE_MANIFEST.json"
ZIP_ROOT = "yy-industry-r-skill"


def _zip_info(relative: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def _可分发文件(skill_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in skill_root.rglob("*"):
        relative = path.relative_to(skill_root)
        if path.is_symlink() or not path.is_file():
            continue
        if len(relative.parts) == 1:
            if relative.name not in 允许顶层文件:
                continue
            files.append(path)
            continue
        elif relative.parts[0] not in 允许产品目录:
            continue
        if path.suffix.lower() not in 允许产品后缀:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(skill_root).as_posix())


def _序列化允许凭据(credentials: dict[str, str]) -> bytes:
    lines = [f"{key}={credentials[key]}" for key in 允许凭据键 if credentials.get(key)]
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def _包含控制字符(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _准备明文凭据(skill_root: Path) -> bytes:
    credentials, missing = 发现可分发凭据(skill_root=skill_root)
    if missing:
        raise ValueError("明文分发缺少必需凭据键: " + "、".join(missing))
    invalid_keys = [key for key in 允许凭据键 if _包含控制字符(credentials[key])]
    if invalid_keys:
        raise ValueError("明文分发凭据包含非法控制字符: " + "、".join(invalid_keys))
    return _序列化允许凭据(credentials)


def 构建技能包(
    skill_root: Path,
    output: str | Path,
    *,
    include_plaintext_credentials: bool = False,
    confirm_plaintext_distribution: bool = False,
) -> dict[str, object]:
    root = Path(skill_root).resolve()
    required = [root / "SKILL.md", root / "README.md", root / "scripts" / "行业研究.py"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("缺少必需文件: " + "、".join(missing))
    if include_plaintext_credentials and not confirm_plaintext_distribution:
        raise PermissionError("明文凭据分发必须双确认")
    if confirm_plaintext_distribution and not include_plaintext_credentials:
        raise PermissionError("确认明文分发只能与包含明文凭据一起使用")

    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    files = _可分发文件(root)
    manifest_files = []
    for path in files:
        data = path.read_bytes()
        manifest_files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    credential_bytes = b""
    if include_plaintext_credentials:
        credential_bytes = _准备明文凭据(root)
    manifest = {
        "name": ZIP_ROOT,
        "version": 版本,
        "language": "zh-CN",
        "contains_user_data": False,
        "contains_credentials": bool(credential_bytes),
        "credential_file_sha256": hashlib.sha256(credential_bytes).hexdigest() if credential_bytes else None,
        "credential_file_size": len(credential_bytes) if credential_bytes else None,
        "files": manifest_files,
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            info = _zip_info(f"{ZIP_ROOT}/{relative}")
            archive.writestr(info, path.read_bytes())
        if credential_bytes:
            archive.writestr(_zip_info(f"{ZIP_ROOT}/config/credentials.env"), credential_bytes)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        for manifest_path in (MANIFEST_PATH, LEGACY_MANIFEST_PATH):
            archive.writestr(_zip_info(manifest_path), manifest_bytes)
    return {
        "path": output_path,
        "contains_credentials": manifest["contains_credentials"],
        "credential_file_sha256": manifest["credential_file_sha256"],
        "credential_file_size": manifest["credential_file_size"],
    }


def 打包(output: str | Path) -> Path:
    result = 构建技能包(根目录, output)
    return Path(result["path"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成不含密钥、缓存和用户资料的独立 Skill 包")
    parser.add_argument("--输出", required=True)
    parser.add_argument("--包含明文凭据", action="store_true")
    parser.add_argument("--确认明文分发", action="store_true")
    args = parser.parse_args(argv)
    result = 构建技能包(
        根目录,
        args.输出,
        include_plaintext_credentials=args.包含明文凭据,
        confirm_plaintext_distribution=args.确认明文分发,
    )
    print(result["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
