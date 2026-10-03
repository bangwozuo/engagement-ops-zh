# 评论运营官

> **把评论区从"成本中心"变成"选题矿藏"的运营副手**

[![Stage](https://img.shields.io/badge/stage-P0-orange)](https://github.com/bangwozuo)
[![Asset](https://img.shields.io/badge/asset-prompt%20%2B%20scripts-blueviolet)](#资产矩阵)
[![NoKey](https://img.shields.io/badge/API%20Key-not%20required-success)](#资产校验)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

![演示](docs/demo.mp4)

*上图为仓库实跑演示（5 个代表资产 × 4 秒）：评论情感四分类 → 高频问题聚类 → 回复工单 → 问题转选题 → 铁粉名单，全部来自 `--run` 真实执行的终端截图。*

---

## 数字员工总览

| 项目 | 内容 |
|------|------|
| 身份 | 面向**自媒体创作者**（万粉以上、评论量达到人工处理瓶颈）的评论运营副手 |
| 能力 | 评论四分类与 SLA 排序 · 高频问题聚类转选题 · 人设一致的回复草稿与质检 · 粉丝九宫格分层与铁粉名单 |
| 交付物 | 评论处理时长 1-2h → ≤20 分钟；高频问题→选题转化率 ≥10%/周；回复人设一致性质检通过率 ≥95% |
| 边界 | 只产队列/草稿/名单——**发布、隐藏、举报、私信、移交私域全部人工执行，发布率红线 0%** |
| KPI | 单日评论处理人工介入前 ≤5 分钟；选题库月度采纳率与评论区播放表现可回溯 |

---

## 资产矩阵

### 技能（6 个）

| 技能 | 一句话 | 类型 | README |
|------|--------|------|--------|
| 评论情感分析 | 评论四分类 + 情绪强度 1-5 + SLA 排序（黑粉 30 分钟/吐槽 2h/提问 4h） | T1 产物型（脚本） | [README](skills/comment-sentiment-analyze/README.md) |
| 高频问题聚类 | 双通道相似度 ≥0.60 聚类，Top 10 问题榜 + 可粘贴答案要点，覆盖率自检 | T1 产物型（脚本） | [README](skills/faq-cluster/README.md) |
| 人设语气库 | 语气库档案 + 草稿一致性打分（称呼40/口头禅20/句长20/零违禁20），合规否决一票制 | T1 产物型（脚本） | [README](skills/persona-voice-library/README.md) |
| 粉丝分层打标 | 频次 × 情感九宫格 + 铁粉评分 0-100，感谢/安抚/观察三张名单 | T1 产物型（脚本） | [README](skills/fan-segmentation-tag/README.md) |
| 回复话术生成 | 三类评论三套策略，写出能直接粘贴、过一致性检查的回复草稿 | T2 提示词型 | [README](skills/reply-script-generate/README.md) |
| 选题知识库 | 问题簇 → 查重 → 优先级 → 可开拍选题条目，库健康度双指标体检 | T4 连接器型 | [README](skills/topic-knowledge-base/README.md) |

### 工作流（4 条）

| 工作流 | 一句话 | 触发 | README |
|--------|--------|------|--------|
| 每日评论聚合分类 | 当日评论 → SLA 处理队列日报，双异常信号（负类>50% / 提问>40%） | 定时（每日 21:00） | [README](workflows/daily-comment-aggregate-flow/README.md) |
| 高频问题转选题 | 聚类 → 排榜 → 查重 → 选题条目（全部待人工确认），评论区需求不烂尾 | 事件（WF1 后自动） | [README](workflows/faq-to-topic-flow/README.md) |
| 回复话术建议 | 高优评论 → 四态回复工单（待确认/需改写/禁止发布/待生成），达标线 80 分 | 人工/事件 | [README](workflows/reply-script-advice-flow/README.md) |
| 铁粉识别与互动名单 | 九宫格分层 → 铁粉维护名单 + 私域移交确认清单 | 定时（每周一 10:00） | [README](workflows/superfan-identify-flow/README.md) |

---

## 快速开始

```text
1. 打开 skills/comment-sentiment-analyze/prompt.txt
2. 全文复制
3. 粘贴到你常用的 AI 工具（Coze / WorkBuddy / Dify / Claude / ChatGPT）
4. 按 SKILL.md 的输入规格提供数据
```

带脚本的资产（T1/工作流）可直接真实执行，无需 API Key：

```bash
pip install -r requirements.txt
cd skills/comment-sentiment-analyze
python scripts/sentiment_scan.py --demo   # 内置真实样例，产物落盘 out/
```

完整指引见 [使用手册](docs/04-usage.md)。

---

## 仓库结构

```text
engagement-ops-zh/
├── README.md / employee.md / package.yaml     # 入口与 12 字段定义卡
├── docs/demo.mp4                              # 仓库实跑演示视频（5 镜头）
├── docs/01~07                                 # 员工级文档（架构/流程/场景/手册/示例/录像/测试）
├── skills/                                    # 6 个原子技能
│   └── <skill>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       ├── scripts/                           # T1 技能自带确定性脚本（真实执行 → Excel/PNG/JSON）
│       └── docs/                              # 9 项文档 + run-terminal.png 实跑截图
├── workflows/                                 # 4 条工作流（端到端编排脚本）
│   └── <workflow>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       ├── scripts/run_flow.py                # 调用真实技能 slug 的 DAG 编排
│       └── docs/                              # 9 项文档 + run-terminal.png 实跑截图
├── knowledge/                                 # RAG wiki 知识库
├── connectors/                                # 连接器说明 + 合规红线
├── quality/                                   # 效果基线与追踪日志
└── tests/                                     # 资产校验测试（离线，无需密钥）
```

---

## 交付物导航

| 文档 | 内容 |
|------|------|
| [业务架构](docs/01-architecture.md) | 四层架构 + 数据流 + 能力边界 |
| [工作流流程](docs/02-workflow.md) | 4 条工作流的 DAG 可视化 |
| [使用场景](docs/03-scenarios.md) | 3 个真实场景（含前后对比） |
| [使用手册](docs/04-usage.md) | 各平台导入指引 + 常见问题 |
| [示例库](docs/05-examples.md) | 6 组输入输出示例 |
| [录像脚本](docs/06-recording-script.md) | 7 镜头分镜 + 旁白稿 |
| [校验报告](docs/07-test-report.md) | 资产质量校验结果 |

---

## 资产校验

```bash
pip install -r requirements.txt
pytest tests/ -v
```

校验技能完整性、提示词结构、契约一致性、工作流 DAG、技能级与工作流级 docs 完整性、知识库 wiki 与连接器结构。
**不需要任何 API Key。**

---

## 合规声明

- ✅ 所有输出为 **AI 辅助生成**，交付前须人工审核
- ✅ 提示词内置**违禁词禁止清单**，符合《广告法》要求
- ✅ 遵循《人工智能生成合成内容标识办法》
- ✅ 连接器只走**官方 API** 或**用户导出数据**
- ✅ 所有对外发布动作**保留人工确认环节**（发布率红线 0%）

---

## 许可

[Apache-2.0](LICENSE) — 可自由使用、修改、商用

---

*由 bangwozuo 业务库自动生成 · 2026-09-29 · README 投产级改造 2026-10-03*
