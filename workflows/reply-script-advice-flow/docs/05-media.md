# 截图与录屏

> 以下素材均来自**真实执行**：`--run` 实拍终端 / 实跑产物文件，无摆拍。

## 演示视频

![演示视频](assets/demo.mp4)

*第二帧为实跑产物图表*

## 执行截图

![真实执行](assets/run-terminal.png)

## 实跑产物

| 文件 | 说明 |
|---|---|
| [`out/_demo_sent_input.json`](out/_demo_sent_input.json) | 结构化结果（实跑生成） · 1 KB |
| [`out/_demo_voice_input.json`](out/_demo_voice_input.json) | 结构化结果（实跑生成） · 1 KB |
| [`out/advice_flow_result.json`](out/advice_flow_result.json) | 结构化结果（实跑生成） · 1 KB |
| [`out/sentiment.json`](out/sentiment.json) | 结构化结果（实跑生成） · 3 KB |
| [`out/voice_check.json`](out/voice_check.json) | 结构化结果（实跑生成） · 3 KB |
| [`out/voice_scores.png`](out/voice_scores.png) | 图表产物（实跑生成） · 23 KB |
| [`out/回复工单.xlsx`](out/回复工单.xlsx) | Excel 工作簿（实跑生成） · 7 KB |
| [`out/评论分类处理清单.xlsx`](out/评论分类处理清单.xlsx) | Excel 工作簿（实跑生成） · 7 KB |
| [`out/评论情感分布.png`](out/评论情感分布.png) | 图表产物（实跑生成） · 23 KB |
| [`out/语气一致性检查.xlsx`](out/语气一致性检查.xlsx) | Excel 工作簿（实跑生成） · 8 KB |


---

## 附录：实跑输出明细

> 本资产为纯提示词客户端资产，无界面可截图。以下为**实跑运行效果**。

## 运行效果

### 输入

```json
{
  "input": "请提供工作流的初始输入数据"
}

```

### 输出

## 执行摘要

本次执行因缺少有效初始输入数据，工作流在入口阶段即提示补充信息，未进入回复话术生成与人设语气库技能的处理环节。

## 分步结果

1. 步骤 1（回复话术生成）：检测到输入为占位符"请提供工作流的初始输入数据"，无法生成应答话术与升级判断，已返回提示信息要求补充用户消息与背景信息。
2. 步骤 2（人设语气库）：前一步输出不完整，跳过执行。

## 最终交付物

> **待补充信息**：请提供用户消息（question）、背景信息（context，可选）以及人设与口径（persona，可选），以便执行回复话术建议工作流。

*AI 生成内容*


---

*运行效果由实跑验证生成*
