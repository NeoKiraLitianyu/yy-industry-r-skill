from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skill入口把独立模式与NeoStar增强模式分开路由():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "独立模式" in skill
    assert "NeoStar 增强模式" in skill
    assert "references/数据源路由与NeoStar适配.md" in skill
    assert "references/世界级报告结构与质量门.md" in skill
    assert "不创建自动化" in skill


def test_关键引用文件真实存在且能独立分发():
    required = [
        "references/数据源路由与NeoStar适配.md",
        "references/世界级报告结构与质量门.md",
        "industry-packs/半导体膜材/来源矩阵.json",
        "industry-packs/半导体膜材/关系词表.json",
        "references/出版与紫色视觉规范.md",
        "references/朋友分发与明文凭据风险.md",
        "scripts/生成出版报告.py",
    ]

    assert all((ROOT / path).is_file() for path in required)


def test_正式封装版本不再是原型号():
    from yy_industry_research.配置 import 版本

    assert tuple(int(part) for part in 版本.split(".")) >= (2, 0, 0)


def test_skill契约包含出版PDF与双分发说明():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "生成出版报告.py" in skill
    assert "紫色" in skill and "PDF" in skill
    assert "安全包" in readme and "朋友明文凭据包" in readme
    assert "YIXIN_API_KEY" in readme and "TDX_MCP_URL" in readme
