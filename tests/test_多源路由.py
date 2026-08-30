from __future__ import annotations

from pathlib import Path

from yy_industry_research.数据路由 import (
    标准候选,
    数据源路由器,
    保存路由结果,
    规范化Yixin结果,
)
from yy_industry_research.数据适配器 import NeoStar本地适配器, TDX适配器, Yixin适配器, 公开网页适配器, 创建TDX适配器, 读取NeoStar连接配置
from yy_industry_research.相关性 import 评估膜材相关性


class 假适配器:
    def __init__(self, 名称: str, 优先级: int, 结果=None, 错误: str | None = None):
        self.名称 = 名称
        self.优先级 = 优先级
        self.结果 = list(结果 or [])
        self.错误 = 错误
        self.调用次数 = 0

    def 检索(self, 请求):
        self.调用次数 += 1
        if self.错误:
            raise RuntimeError(self.错误)
        return self.结果


def test_路由按原生数据优先并记录诚实降级():
    yixin = 假适配器("yixin", 10, 错误="连接超时")
    tdx = 假适配器(
        "tdx",
        20,
        [标准候选("https://example.cn/report.pdf", "TDX研报", "TDX", "中国")],
    )
    web = 假适配器(
        "公开网页",
        90,
        [标准候选("https://example.cn/report.pdf", "镜像", "公开网页", "中国")],
    )

    结果 = 数据源路由器([web, tdx, yixin]).检索("半导体膜材", 最大结果数=10)

    assert [回执.适配器 for 回执 in 结果.回执] == ["yixin", "tdx", "公开网页"]
    assert 结果.回执[0].状态 == "降级"
    assert 结果.回执[0].错误 == "连接超时"
    assert len(结果.候选) == 1
    assert 结果.候选[0].发现通道 == ["TDX", "公开网页"]


def test_规范化Yixin嵌套结果保留来源日期与原始链接():
    原始 = [
        {
            "query": "半导体前驱体",
            "content": [
                {
                    "title": "中国半导体前驱体行业报告",
                    "snippet": "覆盖ALD与CVD前驱体。",
                    "link": "https://broker.example/report/1.pdf",
                    "date": "2026-08-01",
                }
            ],
        }
    ]

    候选 = 规范化Yixin结果(原始, source_type="report")

    assert len(候选) == 1
    assert 候选[0].来源类型 == "券商咨询"
    assert 候选[0].发布日期 == "2026-08-01"
    assert 候选[0].原始链接.endswith("1.pdf")
    assert 候选[0].发现通道 == ["Yixin/report"]


def test_Yixin无原始链接时保留为可归档MCP元数据而不是静默丢弃():
    candidates = 规范化Yixin结果(
        [
            {
                "query": "ALD前驱体",
                "content": [
                    {
                        "title": "半导体前驱体深度报告",
                        "link": "",
                        "snippet": "资料来源：国信证券研究所",
                        "date": "2026-05-27",
                        "extra": {"institution": "国信证券"},
                    }
                ],
            }
        ],
        source_type="report",
    )

    assert len(candidates) == 1
    assert candidates[0].原始链接.startswith("yixin://report/")
    assert candidates[0].来源名称 == "国信证券"
    assert candidates[0].元数据["metadata_only"] is True


def test_Yixin公告用披露公司作为来源族而不是笼统Yixin():
    candidates = 规范化Yixin结果(
        [{"query": "靶材", "content": [{"title": "南大光电:2025年年度报告", "link": "", "snippet": ""}]}],
        source_type="announcement",
    )

    assert candidates[0].来源名称 == "南大光电"


def test_Yixin适配器覆盖研报学术公告三类并保留查询回执():
    calls = []

    def transport(path, payload):
        calls.append((path, payload))
        return {
            "result": [
                {
                    "query": payload["query"],
                    "content": [
                        {
                            "title": f"ALD前驱体{payload['source']}资料",
                            "link": f"https://source.example/{payload['source']}.pdf",
                            "date": "2026-08-20",
                        }
                    ],
                }
            ]
        }

    adapter = Yixin适配器(transport=transport, 查询上限=1)
    results = list(adapter.检索({"行业": "半导体膜材", "查询词": ["ALD前驱体"]}))

    assert {call[1]["source"] for call in calls} == {"report", "academic", "announcement"}
    assert len(results) == 3
    assert all(item.元数据["query"] == "ALD前驱体" for item in results)


def test_膜材相关性要求候选正文真实命中而不是只因检索词命中():
    无关 = 标准候选(
        "yixin://report/generic",
        "半导体行业周报",
        "Yixin/report",
        "中国",
        摘要="本周晶圆代工板块上涨。",
        元数据={"query": "ALD前驱体"},
    )
    相关 = 标准候选(
        "yixin://report/ald",
        "先进制程薄膜沉积材料深度报告",
        "Yixin/report",
        "中国",
        摘要="覆盖ALD/CVD前驱体、高纯溅射靶材和High-k介质。",
    )

    assert 评估膜材相关性(无关)["是否相关"] is False
    assert 评估膜材相关性(相关)["是否相关"] is True
    assert "ALD" in 评估膜材相关性(相关)["命中词"]


def test_Yixin适配器过滤泛半导体噪声并记录相关性证据():
    def transport(path, payload):
        return {
            "result": [
                {
                    "query": payload["query"],
                    "content": [
                        {"title": "半导体行业周报", "snippet": "晶圆代工行情复盘", "link": "https://x/generic"},
                        {"title": "ALD前驱体行业深度", "snippet": "GAA带动High-k薄膜需求", "link": "https://x/ald"},
                    ],
                }
            ]
        }

    results = list(Yixin适配器(transport=transport, 查询上限=1).检索({"行业": "半导体膜材", "查询词": ["ALD前驱体"]}))

    assert len(results) == 3
    assert all(item.标题 == "ALD前驱体行业深度" for item in results)
    assert all(item.元数据["相关性"]["是否相关"] for item in results)


def test_TDX计费源默认关闭且显式启用后只调用研报公告():
    class Client:
        def __init__(self):
            self.calls = []

        def reports(self, query, top_k=10):
            self.calls.append(("reports", query, top_k))
            return {"data": [{"标题": "券商研报", "原文链接": "https://tdx.example/report.pdf"}]}

        def notices(self, query, top_k=10):
            self.calls.append(("notices", query, top_k))
            return {"data": [{"标题": "公司公告", "原文链接": "https://tdx.example/notice.pdf"}]}

    client = Client()
    disabled = TDX适配器(client=client, enabled=False)
    try:
        list(disabled.检索({"行业": "半导体膜材"}))
    except PermissionError as exc:
        assert "未启用" in str(exc)
    else:
        raise AssertionError("TDX 计费源默认关闭时不应静默调用")
    assert client.calls == []

    enabled = TDX适配器(client=client, enabled=True, 每次上限=2)
    results = list(enabled.检索({"行业": "半导体膜材", "查询词": ["高纯溅射靶材"]}))
    assert [call[0] for call in client.calls] == ["reports", "notices"]
    assert {item.来源类型 for item in results} == {"券商咨询", "公司一手"}


def test_TDX原生客户端握手失败返回None时必须诚实降级而非伪成功():
    class Client:
        def reports(self, query, top_k=10):
            return None

        def notices(self, query, top_k=10):
            return None

    adapter = TDX适配器(client=Client(), enabled=True, 每次上限=2)

    try:
        list(adapter.检索({"行业": "半导体膜材", "查询词": ["ALD前驱体"]}))
    except RuntimeError as exc:
        assert "未取得有效响应" in str(exc)
    else:
        raise AssertionError("TDX握手失败不应记录为成功")


def test_NeoStar增强模式优先桥接原生TDX预算客户端(tmp_path):
    module = tmp_path / "二级市场交易" / "KiraQuant" / "data" / "tdx_mcp_adapter.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "class TdxMcpClient:\n"
        "    def __init__(self, enabled=None): self.enabled = enabled\n"
        "    def reports(self, query, top_k=10): return {'data': []}\n"
        "    def notices(self, query, top_k=10): return {'data': []}\n",
        encoding="utf-8",
    )

    adapter = 创建TDX适配器(tmp_path, enabled=True, 每次上限=2)

    assert adapter.名称 == "tdx/NeoStar原生"
    assert adapter.client.__class__.__name__ == "TdxMcpClient"
    assert adapter.client.enabled is True


def test_NeoStar本地适配器读取星图与一级知识库但不越界(tmp_path):
    (tmp_path / "星图数据库" / "产业图谱研究").mkdir(parents=True)
    (tmp_path / "一级市场机会" / "_知识库" / "半导体").mkdir(parents=True)
    (tmp_path / "星图数据库" / "产业图谱研究" / "膜材.md").write_text(
        "ALD前驱体用于GAA薄膜沉积", encoding="utf-8"
    )
    (tmp_path / "一级市场机会" / "_知识库" / "半导体" / "靶材.md").write_text(
        "高纯溅射靶材供应链", encoding="utf-8"
    )
    (tmp_path / "越界.md").write_text("ALD前驱体", encoding="utf-8")

    results = list(
        NeoStar本地适配器(tmp_path).检索(
            {"行业": "半导体膜材", "查询词": ["ALD前驱体", "高纯溅射靶材"]}
        )
    )

    assert len(results) == 2
    assert all("越界.md" not in item.原始链接 for item in results)
    assert {item.来源类型 for item in results} == {"NeoStar星图", "NeoStar一级知识库"}


def test_本地候选字典可被主流水线直接归档(tmp_path):
    local = tmp_path / "材料.md"
    local.write_text("ALD前驱体", encoding="utf-8")
    item = 标准候选(
        str(local),
        "材料",
        "NeoStar本地",
        "中国",
        元数据={"local_path": str(local)},
    )

    payload = item.转候选字典()

    assert payload["local_path"] == str(local)
    assert payload["discovery_channels"] == ["NeoStar本地"]


def test_路由回执与候选清单一起原子保存(tmp_path):
    adapter = 假适配器(
        "yixin",
        10,
        [标准候选("https://example.com/a.pdf", "A", "Yixin/report", "全球")],
    )
    result = 数据源路由器([adapter]).检索("半导体膜材")

    paths = 保存路由结果(result, tmp_path)

    assert paths["候选清单"].exists()
    assert paths["运行回执"].exists()
    assert "Yixin/report" in paths["候选清单"].read_text(encoding="utf-8")
    assert '"状态": "成功"' in paths["运行回执"].read_text(encoding="utf-8")


def test_保存路由结果会把Yixin无链接内容物化为原始回执(tmp_path):
    candidate = 标准候选(
        "yixin://report/abc123",
        "无链接研报",
        "Yixin/report",
        "中国",
        元数据={"metadata_only": True, "snippet": "原始检索摘要", "query": "ALD"},
    )
    result = 数据源路由器([假适配器("yixin", 10, [candidate])]).检索("半导体膜材")

    paths = 保存路由结果(result, tmp_path)
    payload = __import__("json").loads(paths["候选清单"].read_text(encoding="utf-8").splitlines()[0])

    assert Path(payload["local_path"]).exists()
    assert "原始检索摘要" in Path(payload["local_path"]).read_text(encoding="utf-8")


def test_公开网页适配器复用通用检索并标准化候选():
    calls = []

    def search(industry, **kwargs):
        calls.append((industry, kwargs))
        return [
            type(
                "Candidate",
                (),
                {
                    "source_uri": "https://semi.org/materials",
                    "title": "Global Materials Report",
                    "source_type": "行业协会",
                    "region": "全球",
                    "published_at": "2026-07-01",
                    "summary": "materials",
                    "source_name": "SEMI",
                    "language": "en",
                    "source_credibility": 9,
                },
            )()
        ]

    results = list(公开网页适配器(search=search).检索({"行业": "半导体膜材", "最大结果数": 5}))

    assert calls[0][0] == "半导体膜材"
    assert results[0].发现通道 == ["公开网页"]
    assert results[0].来源名称 == "SEMI"


def test_NeoStar连接配置只读取指定键且不返回其他秘密(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TDX_MCP_API_KEY=tdx-test\nTDX_MCP_ENABLED=1\nOTHER_SECRET=never-return\n",
        encoding="utf-8",
    )

    config = 读取NeoStar连接配置(env_file)

    assert config == {"TDX_MCP_API_KEY": "tdx-test", "TDX_MCP_ENABLED": "1"}
