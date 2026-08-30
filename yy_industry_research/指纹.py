from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass


def 标准化文本(文本: str) -> str:
    """将文本标准化用于指纹对比。"""
    文本 = unicodedata.normalize("NFKC", 文本)
    文本 = 文本.lower()
    文本 = 文本.replace("\u200b", "")
    文本 = re.sub(r"\s+", " ", 文本)
    return 文本.strip()


def sha256十六进制(文本: str) -> str:
    return hashlib.sha256(标准化文本(文本).encode("utf-8")).hexdigest()


def 文件sha256(二进制: bytes) -> str:
    return hashlib.sha256(二进制).hexdigest()


def _词重(文本: str) -> int:
    压缩 = re.sub(r"\W+", "", 文本)
    return int.from_bytes(hashlib.md5(压缩.encode("utf-8")).digest()[:8], "big", signed=False)


def simhash64(文本: str) -> str:
    """兼容式 SimHash 64 位十六进制字符串。"""
    标准 = 标准化文本(文本)
    tokens = [w for w in re.split(r"\W+", 标准) if w]
    if not tokens:
        return "0" * 16

    维度 = [0] * 64
    for token in tokens:
        h = _词重(token)
        for i in range(64):
            if (h >> i) & 1:
                维度[i] += 1
            else:
                维度[i] -= 1

    位 = 0
    for i in range(64):
        if 维度[i] >= 0:
            位 |= 1 << i
    return f"{位:016x}"


def 汉明距离(左: str, 右: str) -> int:
    return (int(左, 16) ^ int(右, 16)).bit_count()


@dataclass(frozen=True, slots=True)
class 文本指纹:
    原文sha: str
    语义sha: str


def 生成指纹(文本: str) -> 文本指纹:
    """返回原文摘要与局部语义签名。"""
    return 文本指纹(sha256十六进制(文本), simhash64(文本))
