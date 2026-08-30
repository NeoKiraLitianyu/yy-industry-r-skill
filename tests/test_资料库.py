from __future__ import annotations

import json
from pathlib import Path

from yy_industry_research.资料库 import 初始化资料库
from yy_industry_research.行业包 import 读取行业包, 构建查询矩阵, 提取行业命中节点
from yy_industry_research.索引 import _当前时间


def test_初始化资料库生成全中文目录和配置(tmp_path: Path) -> None:
    root = 初始化资料库(tmp_path / "库", "半导体膜材", None)

    required = [
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
    ]
    assert all((root / part).is_dir() for part in required)
    assert (root / "行业索引.sqlite").is_file()

    config = json.loads((root / "配置" / "行业配置.json").read_text(encoding="utf-8"))
    assert config["行业"] == "半导体膜材"
    assert config["主检索月数"] == 24
    assert config["关键数据月数"] == 12
    assert config["输出语言"] == "中文"


def test_重复初始化不覆盖用户配置(tmp_path: Path) -> None:
    root = 初始化资料库(tmp_path / "库", "半导体膜材", None)
    config_path = root / "配置" / "行业配置.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["用户备注"] = "保留"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    初始化资料库(root, "半导体膜材", None)

    reloaded = json.loads(config_path.read_text(encoding="utf-8"))
    assert reloaded["用户备注"] == "保留"


def test_读取半导体膜材行业包_有基础配置() -> None:
    root = Path(__file__).resolve().parents[1]
    pack = 读取行业包(root, "半导体膜材")
    assert "config" in pack
    assert "taxonomy" in pack
    assert "research_questions" in pack
    assert "source_matrix" in pack
    assert "relations" in pack


def test_查询矩阵_包含行业特化词() -> None:
    root = Path(__file__).resolve().parents[1]
    pack = 读取行业包(root, "半导体膜材")
    matrix = 构建查询矩阵("半导体膜材", include_global=True, 行业包=pack)
    assert any("ALD" in q for q in matrix["中国"])
    assert any("GAA" in q for q in matrix["全球"])


def test_行业节点命中() -> None:
    root = Path(__file__).resolve().parents[1]
    pack = 读取行业包(root, "半导体膜材")
    text = "该报告覆盖 ALD 前驱体、PVD 靶材及高纯硅基材料，涉及 GAA 与 3D NAND 工艺。"
    hit = 提取行业命中节点(text, pack)
    assert "ALD前驱体" in hit
    assert "PVD溅射靶材" in hit
    assert "先进制程需求" in hit


def test_半导体膜材taxonomy覆盖材料工艺结构器件供应链与投资层() -> None:
    root = Path(__file__).resolve().parents[1]
    pack = 读取行业包(root, "半导体膜材")
    nodes = set(pack["taxonomy"]["nodes"])
    required = {
        "ALD前驱体",
        "CVD前驱体",
        "硅基前驱体",
        "金属基前驱体",
        "高k介质",
        "低k介质",
        "PVD高纯溅射靶材",
        "金属栅与功函数层",
        "阻挡层与衬垫层",
        "互连金属",
        "GAA环绕栅极",
        "背面供电",
        "DRAM电容",
        "3D NAND高深宽比结构",
        "先进封装薄膜",
        "纯度与杂质控制",
        "客户认证与供应安全",
        "国产化与投资机会",
    }

    assert required <= nodes
    assert {"材料用于工艺", "工艺形成薄膜", "器件结构驱动需求", "公司供应材料"} <= set(pack["relations"]["关系类型"])


def test_索引时间戳使用时区感知UTC且无弃用告警() -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        value = _当前时间()

    assert value.endswith("Z")


def test_半导体行业包内置中国与全球权威原始来源种子() -> None:
    root = Path(__file__).resolve().parents[1]
    source_file = root / "industry-packs" / "半导体膜材" / "authoritative_sources.jsonl"
    rows = [json.loads(line) for line in source_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(rows) >= 15
    assert {row["region"] for row in rows} == {"中国", "全球"}
    assert all(row["source_uri"].startswith("https://") for row in rows)
    assert all(row["source_name"] and row["source_type"] for row in rows)
