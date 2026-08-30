from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_问题模板 = {
    "定义与边界": ["行业定义是什么", "统计边界如何设定", "产品与工艺如何分类", "哪些相邻材料不纳入"],
    "技术与工艺": ["核心沉积路线是什么", "关键材料性能指标是什么", "工艺窗口与失效模式是什么", "技术迭代路径是什么"],
    "需求驱动": ["先进逻辑如何驱动需求", "存储器如何驱动需求", "先进封装如何驱动需求", "单位晶圆材料强度如何变化"],
    "市场规模": ["全球市场规模是多少", "中国市场规模是多少", "自上而下测算如何", "自下而上测算如何", "两种测算差异为何"],
    "供应链与利润池": ["产业链环节有哪些", "利润池集中在哪里", "上游关键原料是什么", "设备与材料如何耦合", "认证周期有多长"],
    "竞争格局": ["全球龙头是谁", "中国主要厂商是谁", "份额与集中度如何", "进入壁垒是什么", "并购与合作趋势如何"],
    "中国国产化": ["国产化率如何定义", "分产品国产化率是多少", "卡点与断点在哪里", "政策与扩产如何影响", "潜在替代者是谁"],
    "可比公司与资本化": ["上市可比公司有哪些", "收入利润与估值如何", "一级融资与并购案例有哪些", "估值口径如何统一"],
    "一级市场投资判断": ["最佳切入点是什么", "控制点在哪里", "团队与产线需验证什么", "投资节奏与里程碑是什么", "退出路径有哪些"],
    "风险与反证": ["技术替代风险是什么", "周期与价格风险是什么", "客户认证风险是什么", "合规安全与地缘风险是什么", "哪些证据会推翻结论"],
    "数据来源与原始素材": ["每项关键数据来自哪里", "是否保存原始文件", "能否定位页码段落", "冲突数据如何保留"],
}


@dataclass(frozen=True, slots=True)
class 研究框架:
    行业: str
    模块: tuple[str, ...]
    研究问题: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class 覆盖检查结果:
    未达标模块: tuple[str, ...]
    未交叉验证事实: int
    缺少定位事实: int
    缺少原始素材: int
    模块事实数: dict[str, int]


def 生成研究框架(行业: str) -> 研究框架:
    questions = tuple(f"{行业}：{q}" for items in _问题模板.values() for q in items)
    return 研究框架(行业.strip(), tuple(_问题模板), questions)


def 检查研究覆盖(框架: 研究框架, 事实: Iterable[dict], 来源清单: Iterable[dict]) -> 覆盖检查结果:
    counts = {module: 0 for module in 框架.模块}
    unverified = 0
    unlocated = 0
    for fact in 事实:
        module = str(fact.get("module", ""))
        if module in counts:
            counts[module] += 1
        if fact.get("verification_status") != "已验证":
            unverified += 1
        if not str(fact.get("locator", "")).strip():
            unlocated += 1
    missing_raw = 0
    for source in 来源清单:
        raw_path = str(source.get("raw_path", "")).strip()
        if not raw_path or not Path(raw_path).exists():
            missing_raw += 1
    failed = tuple(module for module, count in counts.items() if count == 0 or module == "市场规模" and unverified > 0)
    return 覆盖检查结果(failed, unverified, unlocated, missing_raw, counts)
