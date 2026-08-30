# yy-Industry R Skill

可独立复制、封装和交付的中国与全球行业研究 Skill（原名 china-industry-research）。通用核心负责"找、抓、存、去重、解析、验证、建库、研究"，行业包负责术语、来源、研究问题、策展事实、分析正文和 Mapping；当前内置首个正式行业包"半导体膜材"。

## 能力

- 中国/全球多语检索，券商、协会、政府、公司、科研机构与咨询机构专项发现。
- Yixin 研报/学术/公告检索；NeoStar 内可桥接原生 TDX 预算客户端、星图与一级市场知识库。
- PDF、网页与附件抓取，原始文件双轨归档，SHA-256/内容指纹去重。
- PDF、DOCX、XLSX、HTML、文本解析，来源多维评级，结构化事实和独立来源族验证。
- 证据门控的行业 Mapping、策展关键事实、Deep Research 问题框架和中文一级市场投资报告。
- 22 章顶级颗粒度出版结构、14 张可追溯 SVG 图表、克制紫色自包含 HTML 与可抽取中文的 A4 PDF。
- 每路数据源保留成功、降级、错误和候选回执；单一来源、冲突与缺口不伪装成确定结论。

本 Skill 不包含定时任务、监控或自动化调度。

## 两种运行模式

- 独立模式：行业包权威种子、公开网页、用户文件及可选 Yixin OpenAPI；不依赖 NeoStar。
- NeoStar 增强模式：Yixin → TDX（显式启用且受原生每日预算熔断）→ 星图/一级市场知识库 → 权威原文与公开源。

MCP 只负责发现和问数。关键事实必须回到原始网页/PDF并记录机构、日期、定位和来源族；没有原文的结果只保存 MCP 原始回执。

## 环境

- Python 3.11+
- 依赖见 `requirements.txt`
- Yixin 密钥可放在 `YIXIN_API_KEY` 或 `~/.workbuddy/secrets/yixin-api/api-key.json`
- TDX 是计费源，默认关闭；只有显式传入 `--启用-tdx` 才调用

## 快速开始

```powershell
python scripts/行业研究.py 初始化 --行业 半导体膜材 --资料库 .\半导体膜材行业库
python scripts/行业研究.py 计划 --行业 半导体膜材 --全球
python scripts/行业研究.py 运行 --行业 半导体膜材 --资料库 .\半导体膜材行业库 --自动检索 --全球 --ignore-parse-fail
python scripts/行业研究.py 验收 --资料库 .\半导体膜材行业库
python scripts/生成出版报告.py --资料库 .\半导体膜材行业库 --行业 半导体膜材 --输出目录 .\半导体膜材行业库\研究报告 --生成PDF
```

在 NeoStar 内运行（`<NeoStar根目录>` 换成你的本机根路径；省略 `--neostar-root` 时会自动向上发现）：

```powershell
python 一级市场机会\行业研究.py 运行 --行业 半导体膜材 --资料库 一级市场机会\_知识库\半导体膜材 --自动检索 --全球 --启用-tdx --neostar-root <NeoStar根目录> --ignore-parse-fail
```

用户文件也可直接进入同一管道：

```powershell
python scripts/行业研究.py 运行 --行业 半导体膜材 --资料库 .\半导体膜材行业库 --输入 .\raw\report.pdf --region 中国
```

## 半导体膜材行业包

`industry-packs/半导体膜材` 包含：

- 五层 taxonomy：材料、工艺、器件结构、工程指标、产业与投资。
- ALD/CVD前驱体、High-k/Low-k、硅基/金属基前驱体、PVD高纯靶材、金属栅/阻挡层/互连。
- GAA、背面供电、DRAM电容、3D NAND高深宽比结构和先进封装薄膜需求。
- 中国与全球权威原始来源种子、来源矩阵、关系词表、100 项策展事实、九个证据模块、22 章出版正文和证据 Mapping。
- `research_analysis.json` 提供执行摘要、连续论证、量化表格、投资含义与证据边界；更换行业时可按同一结构复用。

未来新增光刻胶、CMP、先进封装材料等行业时，只需新增行业包，不修改通用核心。

## 输出目录

资料库包含原始资料、解析文本、来源目录、结构化事实、验证与冲突、行业图谱、研究报告、运行记录和 SQLite 行业索引。报告最后固定附完整来源、原始素材路径和原始链接。

## Skill 内凭据配置

独立交付时，凭据可放在 Skill 自己的 `config/credentials.env`；运行时环境变量优先。只识别以下键：

- `YIXIN_API_KEY`
- `TDX_MCP_URL`
- `TDX_MCP_API_KEY`
- `TDX_MCP_ENABLED`
- `TDX_MCP_DAILY_BUDGET`

代码和日志只允许显示键名、缺失项、文件大小与哈希，禁止显示值。Yixin/TDX 是发现与问数通道，关键结论仍必须回到可归档原文。

## 双版本分发

- **安全包**：默认；不含任何凭据、用户研报、SQLite、运行记录或 NeoStar 私有数据，适合公开或普通分享。
- **朋友明文凭据包**：仅在 `--包含明文凭据 --确认明文分发` 双确认后生成，包含 `config/credentials.env`。这是便携性优先的高风险模式，只能通过可信加密通道发送，并应设置短有效期、最小权限和费用上限。

```powershell
python scripts/打包技能.py --输出 yy-industry-r-skill-2.0.0.zip
python scripts/打包技能.py --输出 yy-industry-r-skill-2.0.0-朋友明文凭据.zip --包含明文凭据 --确认明文分发
```

## 分发边界

安全 Skill 包不含抓取后的研报、SQLite、运行记录、缓存、密钥或 NeoStar 私有数据。朋友明文凭据包是用户显式选择的例外，Manifest 会明确标记 `contains_credentials=true`，但不会展示凭据值。
