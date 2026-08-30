---
status: active
name: yy-Industry R Skill
title: yy-Industry R Skill
description: 把 Agent 变成一名可复查的证据工程行业研究员。当用户需要研究中国或全球行业、搜集行业研报、建立行业资料库或 Mapping，尤其是要求原始素材、来源追溯、多来源验证和全中文研究输出时启用。触发词：行业研究、行业研报、行业资料库、industry research、行业图谱、Mapping、赛道扫描、产业研究、行业深研。
description_zh: 中国与全球行业研究专家，把行业研究做成可复查的证据工程：原始资料不可变、关键事实可定位、冲突不覆盖、结论与证据分层。
description_en: China & global industry research specialist that turns industry studies into auditable evidence engineering with original material, source tracing, multi-source verification, and full-Chinese output.
triggers:
  - 行业研究
  - 行业研报
  - 行业资料库
  - 行业图谱
  - 产业研究
  - 赛道扫描
  - 行业深研
  - industry research
  - industry report
  - industry mapping
  - market mapping
license: MIT
compatibility:
  - claude-skills
  - workbuddy
  - openclaw
  - hermes
  - skillhub
spec: agentskills.io/v1
agent_created: true
domain: 投研
metadata:
  author: yy
  version: 2.0.0
  category: primary-market-research
  target-platforms:
    - claude-skills
    - workbuddy
    - openclaw
    - hermes
    - skillhub
  tags:
    - industry-research
    - source-traceability
    - evidence-engineering
    - china-and-global
    - report-generation
---

# yy-Industry R Skill

## 核心原则

把行业研究做成可复查的证据工程：原始资料不可变，关键事实可定位，冲突不覆盖，结论与证据分层。

## 适用场景

- “研究半导体膜材”或其他行业。
- 搜集中国与全球最新、权威行业资料。
- 建立可持续更新的行业资料库、事实库与 Mapping。
- 审计一份行业报告的来源、口径和证据缺口。

轻量网页问答、单篇摘要或公司 IC Memo 不使用本 Skill。

## 工作契约

1. 读取相关行业包；没有行业包时先生成独立行业配置，不改通用核心。
2. 生成中国与全球查询矩阵，主窗口为最近 24 个月，关键数据优先最近 12 个月，基础资料单列。
3. 先选择运行模式，再把所有发现结果规范化为同一候选来源与证据模型：
   - **独立模式**：公开网页、用户文件与可选 Yixin OpenAPI；没有 NeoStar 也能完成全流程。
   - **NeoStar 增强模式**：按 yixin → TDX（显式启用的计费源）→ 星图/一级知识库 → 全球公开源的顺序路由；每个通道独立记录成功、降级和错误回执。
4. 只获取公开合法资料和用户提供文件。登录、验证码或付费墙只登记元数据，不绕过权限。
5. 运行 `scripts/行业研究.py` 完成归档、解析、指纹、事实验证、Mapping 和 Deep Research；正式成品统一通过 `scripts/生成出版报告.py` 输出 Markdown、紫色 HTML、PDF、SVG 图表、证据包与验收回执。单个来源失败不得静默丢失。
6. 所有关键数字引用来源编号、机构、日期、原始文件和页码或段落。搜索摘要不能直接成为已验证事实。
7. 输出全部使用中文；外文原始文件保持原貌，并生成中文标题、摘要和证据说明。
8. 本 Skill 不创建自动化、定时任务或监控；需要重复运行时由调用方显式触发。

## 按需读取

- 研究来源或抓取边界时，读取 [references/来源与合规规范.md](references/来源与合规规范.md)。
- 提取事实或裁决冲突时，读取 [references/事实与验证规范.md](references/事实与验证规范.md)。
- 需要 yixin、TDX、星图、一级知识库或降级策略时，读取 [references/数据源路由与NeoStar适配.md](references/数据源路由与NeoStar适配.md)。
- 生成正式行业报告或执行质量门时，读取 [references/世界级报告结构与质量门.md](references/世界级报告结构与质量门.md)。
- 生成 HTML/PDF 或调整视觉时，读取 [references/出版与紫色视觉规范.md](references/出版与紫色视觉规范.md)。
- 构建安全包或朋友明文凭据包时，读取 [references/朋友分发与明文凭据风险.md](references/朋友分发与明文凭据风险.md)。
- 使用半导体膜材行业包时，读取 `industry-packs/半导体膜材/研究问题.md` 和对应 JSON 配置。

## 快速命令

```powershell
python scripts/行业研究.py 初始化 --行业 半导体膜材 --资料库 半导体膜材行业库
python scripts/行业研究.py 计划 --行业 半导体膜材
python scripts/行业研究.py 运行 --行业 半导体膜材 --资料库 半导体膜材行业库 --自动检索 --全球
python scripts/行业研究.py 验收 --资料库 半导体膜材行业库
python scripts/生成出版报告.py --资料库 半导体膜材行业库 --行业 半导体膜材 --输出目录 半导体膜材行业库\研究报告 --生成PDF

# 直接抓取现成的行业报告/研报（不创作新报告，默认 yixin OpenAPI + Bing 多源路由）
python scripts/行业研究.py 抓取 --主题 "光模块 行业研报"
python scripts/行业研究.py 抓取 --主题 "光模块" --来源 bing,yixin --数量 10
python scripts/行业研究.py 抓取 --主题 "半导体设备" --仅列表 --json   # 只列清单，机器可读
python scripts/行业研究.py 抓取 --主题 "光模块" --输出目录 .\runs       # 下载 PDF 附件到当前目录下 runs\
```

## 正式出版硬门

- 正式报告固定 22 章，并在正文之后依次输出行业 Mapping、关键事实—证据—验证矩阵，最后一节必须是“数据来源、原始素材与引用清单”。
- 至少 12 张可追溯图表；半导体膜材行业包默认 14 张。外部事实图绑定事实编号，内部测算必须显示“内部模型假设”。
- PDF 必须由自包含 HTML 生成并通过文件头、页数、体积和中文关键标题抽取验收；文件生成不等于验收通过。
- 视觉采用克制紫色、A4、高信息密度和清爽留白；禁止远程字体、脚本、装饰性照片、厚重阴影和高饱和渐变。
- Mapping 正式关系引用的全部事实都必须为“已验证”，关系来源必须来自其事实来源并位于指定资料库；单一公司口径只能进入待验证关系。

## 常见错误

| 错误 | 正确处理 |
|---|---|
| 把转载数量当独立来源数 | 追溯到原始来源族后再计数 |
| 用搜索摘要支撑关键数字 | 获取原文并记录页码或段落 |
| 新数据覆盖旧冲突 | 建立时间线并保留双方证据 |
| 无证据关系进入 Mapping | 放入待验证关系，不进入正式图谱 |
| PDF 无正文仍继续分析 | 标记需要 OCR，诚实报缺 |
| 把 MCP 返回直接当事实 | MCP 只负责发现/问数；关键事实仍需原文、定位与独立验证 |
| TDX 未授权仍尝试调用 | 默认关闭；仅 `--启用-tdx` 时调用并受每次上限约束 |
