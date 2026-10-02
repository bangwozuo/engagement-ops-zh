# 测试报告 —— faq-cluster

## 一、结构校验

| 项 | 结果 |
|---|---|
| 四件套齐全（SKILL.md / prompt.txt / schema.json / examples/input.json） | ✅ PASS |
| SKILL.md 九段齐全 + frontmatter + ID 行 | ✅ PASS |
| prompt.txt ≥ 800 字（T1 标准） | ✅ PASS |
| 无占位符残留 | ✅ PASS |
| 无 API Key / 无模型调用代码 | ✅ PASS |

## 二、脚本实跑

**命令**：

```bash
python3 scripts/faq_cluster.py --demo
python3 scripts/faq_cluster.py --input examples/input.json --outdir out
```

**运行环境**：Python 3.13.12 / openpyxl / matplotlib（标准库 difflib 做编辑距离，无额外依赖）

| 项 | 结果 |
|---|---|
| 退出码 | 0 |
| 处理规模 | 23 条提问 |
| 产物 1 | `out/高频问题聚类.xlsx`（8.5 KB，含 FAQ库Top10 / 问题簇明细 / 汇总 三 sheet） |
| 产物 2 | `out/faq_top10.png`（42 KB 横向柱状图） |
| 产物 3 | `out/faq_cluster.json`（6.5 KB） |
| 耗时 | < 1 s |

### 聚类结果（真实输出）

```
Q01 求链接        变体2 频次3 ✅
Q02 在哪买        变体3 频次3 ✅
Q03 多少钱        变体3 频次3 ✅
Q04 油皮能用吗     变体2 频次2 ✅
Q05 黄皮色号推荐   变体2 频次2 ✅
Q06 什么时候更新   变体2 频次2 ✅
Q07 有没有平替     变体2 频次2 ✅
Q08-Q10 单问法簇                  ✅
Q11-Q13 单问法簇                  —
```

### 质量核对

| 检查 | 结果 |
|---|---|
| 重复问法合并 | 「求链接/求个链接/求链接！」等 7 组变体全部归簇 ✅ |
| 不该合并的未合并 | 「贵不贵」≠「多少钱」（答案口径不同）、「油皮能用吗」≠「油皮会闷痘吗」（0.55 < 0.60）✅ |
| 覆盖率计算 | Top10 覆盖 20/23 = 87%，与手算一致 ✅ |
| 频次排序 | 频次 3 → 2 → 1 严格降序 ✅ |

## 三、边界与已知限制

| 限制 | 说明 |
|---|---|
| 语义合并盲区 | 「怎么入手」vs「如何购买」表面相似度不足，需模型按 prompt.txt 二次合并 |
| 无历史查重 | 本脚本只做当期聚类；与历史 FAQ 库查重由 faq-to-topic-flow 的下一环节完成 |
| 吐槽混入 | 输入若未先过情感分类，负面评论会进簇——上游应为 comment-sentiment-analyze |
| 问法时效 | 平台改版（如"小黄车"改名）后 FAQ 口径需每月校对 |

## 四、结论

**通过。** 结构与实跑双向验证达标，合并/不合并行为经逐簇核对正确，
脚本产出真实文件（Excel/PNG/JSON）。

---

*测试报告基于真实实跑输出生成 · 2026-09-30*
