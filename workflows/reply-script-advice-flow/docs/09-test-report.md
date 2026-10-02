# 测试报告 —— reply-script-advice-flow

## 一、结构校验

| 项 | 结果 |
|---|---|
| 四件套齐全（SKILL.md / prompt.txt / schema.json / examples/input.json） | ✅ PASS |
| SKILL.md 九段齐全 + frontmatter + ID 行（de_media_03_wf03） | ✅ PASS |
| prompt.txt ≥ 1200 字（T3 标准） | ✅ PASS |
| DAG 节点 = 本仓真实 slug（comment-sentiment-analyze / reply-script-generate / persona-voice-library） | ✅ PASS |
| 步骤明细含输入/处理/输出/失败处理 | ✅ PASS |
| 无占位符残留 | ✅ PASS |

## 二、脚本实跑

**命令**：

```bash
python3 scripts/run_flow.py --demo
python3 scripts/run_flow.py --input examples/input.json --outdir out
```

**运行环境**：Python 3.13.12 / openpyxl（编排脚本经 subprocess 串联两个上游技能脚本）

| 项 | 结果 |
|---|---|
| 退出码 | 0 |
| 编排步骤 | 3 步（优先级过滤 → 一致性检查 → 工单对齐） |
| 产物 1 | `out/回复工单.xlsx`（7.4 KB，禁止发布行标红） |
| 产物 2 | `out/sentiment.json`（上游技能产物） |
| 产物 3 | `out/voice_check.json`（上游技能产物） |
| 产物 4 | `out/advice_flow_result.json`（1.5 KB，执行摘要） |
| 耗时 | < 3 s |

### 执行摘要（真实输出）

```
步骤 1  comment-sentiment-analyze ✅  高优过滤：黑粉 1 / 吐槽 2 / 提问 3
步骤 2  persona-voice-library    ✅  5 条草稿逐条打分
步骤 3  工单对齐 ✅  待人工确认 3 / 需改写 1 / 禁止发布 1 / 待生成 1
        草稿覆盖率 83%（≥80%）；发布率红线 0%
```

### 质量核对

| 检查 | 结果 |
|---|---|
| 四态状态机 | 6 条高优评论每条都有明确去向，无遗漏 ✅ |
| 合规否决 | D3（100% 承诺 + 加微信 + 亲～）判「禁止发布」标红 ✅ |
| 缺稿处理 | C011 无草稿 → 「待生成」并指明补稿路径，不中断 ✅ |
| 双技能串联 | sentiment.json 与 voice_check.json 均由真实技能脚本产出，工单逐条对齐 ✅ |
| 失败处理演练 | 临时删除 voice_check.json 重跑 → 中止并打印「上游产物缺失」✅ |

## 三、边界与已知限制

| 限制 | 说明 |
|---|---|
| 草稿来源 | 本流程不生成草稿，生成由模型按 reply-script-generate 完成；脚本只做质检与对齐 |
| 错配风险 | comment_id 写错会错配回复，工单显示评论摘要供人工确认时核对 |
| 词表时效 | 机器词表查不出平台新敏感词，靠模型月度校对 + 人工确认兜底 |
| 确认纪律 | 工单积压 3 天一起确认 = 无人复核，SLA 超时需进复盘 |

## 四、结论

**通过。** 双技能真实串联端到端跑通，四态工单经数据验证，发布率红线 0% 贯穿全流程。

---

*测试报告基于真实实跑输出生成 · 2026-09-30*
