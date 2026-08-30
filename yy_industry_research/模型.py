from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class 研究配置:
    行业: str
    创建时间: str
    主检索月数: int = 24
    关键数据月数: int = 12
    输出语言: str = "中文"
    行业包路径: str = ""
    规则版本: str = "1.0.0"

    def 转字典(self) -> dict[str, Any]:
        return asdict(self)
