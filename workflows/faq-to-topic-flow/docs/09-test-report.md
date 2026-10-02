# 测试报告 —— faq-to-topic-flow

## 一、结构校验

| 项 | 结果 |
|---|---|
| 四件套齐全（SKILL.md / prompt.txt / schema.json / examples/input.json） | ✅ PASS |
| SKILL.md 九段齐全 + frontmatter + ID 行（de_media_03_wf02） | ✅ PASS |
| prompt.txt ≥ 1200 字（T3 标准） | ✅ PASS |
| DAG 节点 = 本仓真实 slug（faq-cluster → topic-knowledge-base） | ✅ PASS |
| 步骤明细含输入/处理/输出/失败处理 | ✅ PASS |
| 无占位符残留 | ✅ PASS |

## 二、脚本实跑

**命令**：

```bash
python3 scripts/run_flow.py --demo
python3 scripts/run_flow.py --input examples/input.json --outdir out
```

**运行环境**：Python 3.13.12 / openpyxl / matplotlib（编排脚本经 subprocess 调用上游 faq_cluster.py）

| 项 | 结果 |
|---|---|
| 退出码 | 0 |
| 编排步骤 | 2 步自动（聚类 + 查重条目化）+ 1 步人工（确认入库） |
| 产物 1 | `out/选题库新增条目.xlsx`（7.8 KB，重复行标红） |
| 产物 2 | `out/faq_cluster.json`（6.3 KB，上游技能产物） |
| 产物 3 | `out/topic_flow_result.json`（1.2 KB，执行摘要） |
| 附属产物 | `out/高频问题聚类.xlsx`、`out/faq_top10.png` |
| 耗时 | < 4 s |

### 执行摘要（真实输出）

```
步骤 1  faq-cluster ✅  23 条提问 → 13 簇，Top10 覆盖率 87%
步骤 2  topic-knowledge-base（查重+条目化）✅  10 条候选：9 新增 / 1 重复
汇总    高优先级 0（最高频次 3）；全部待人工确认
```

### 质量核对

| 检查 | 结果 |
|---|---|
| 查重拦截 | 「求新手教程」与既有「新手化妆顺序教程」命中（编辑距离比 ≥ 0.60）✅ |
| 优先级规则 | 频次 3 → 中；频次 2/1 → 低，与规则一致 ✅ |
| 选题建议映射 | 渠道类→WHERE 买指南；价格类→值不值横评；肤质类→按肤质怎么选 ✅ |
| 人工确认 | 10/10 条目「待人工确认」，零自动入库 ✅ |
| 失败处理演练 | 上游产物 JSON 删除后重跑 → 中止并打印「上游产物缺失」；退出码 1 ✅ |

## 三、边界与已知限制

| 限制 | 说明 |
|---|---|
| 语义查重盲区 | 用词完全不同的近似选题（「平替合集」vs「学生党好物」）需模型复核 |
| 跨周期重复 | 本流程只查"既有库"，跨周重复靠月度库体检兜底 |
| 频次时效 | 单条爆款会制造临时高频，条目标注统计周期，跨周频次才可信 |
| 数据源前提 | 提问子集须先经情感分类，混入吐槽会污染候选（汇总标注风险） |

## 四、结论

**通过。** 端到端实跑产出真实候选清单，查重与优先级规则经数据验证，失败处理可演练。

---

*测试报告基于真实实跑输出生成 · 2026-09-30*
