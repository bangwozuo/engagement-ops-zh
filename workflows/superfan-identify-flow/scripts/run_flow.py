# -*- coding: utf-8 -*-
"""
铁粉识别与互动名单流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  周互动记录流 → [fan-segmentation-tag] 频次×情感九宫格分层 + 铁粉评分
             → 内置名单加工：
               铁粉候选 → 维护动作（感谢/福利/进群邀请，全部标「待人工确认」）
               需安抚   → 2 小时内回复工单（移交 reply-script-advice-flow）
               潜在黑粉观察 → 记录不互动
             → 铁粉维护名单 + 私域移交确认清单（供私域转化环节接手）

失败处理：
  - 上游 fan-segmentation-tag 退出码 != 0 或产物缺失 → 中止并打印错误
  - 周互动记录为空 → 输出「本周无互动」名单并正常退出
  - 铁粉候选为 0 → 正常退出，名单标注「本周无新增，检查阈值（≥5 次/周 且 正情感率 ≥60%）」
  - 疑似刷量号（互动数异常但无正负面区分）→ 保留在明细中，标注「待模型复核」

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(FLOW_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py", file=sys.stderr)
    sys.exit(2)

SEGMENT_SCRIPT = os.path.join(REPO, "skills", "fan-segmentation-tag", "scripts", "segment.py")

DEMO_INPUT = {
    "account": "@小鹿的好物日记",
    "weeks": 2,
    "interactions": [
        {"user": "奶盖不加糖", "type": "comment", "sentiment": "pos"},
        {"user": "奶盖不加糖", "type": "comment", "sentiment": "pos"},
        {"user": "奶盖不加糖", "type": "dm", "sentiment": "neutral"},
        {"user": "奶盖不加糖", "type": "like", "sentiment": ""},
        {"user": "奶盖不加糖", "type": "comment", "sentiment": "pos"},
        {"user": "奶盖不加糖", "type": "collect", "sentiment": ""},
        {"user": "奶盖不加糖", "type": "comment", "sentiment": "pos"},
        {"user": "奶盖不加糖", "type": "like", "sentiment": ""},
        {"user": "奶盖不加糖", "type": "share", "sentiment": ""},
        {"user": "奶盖不加糖", "type": "comment", "sentiment": "pos"},
        {"user": "美妆课代表", "type": "comment", "sentiment": "pos"},
        {"user": "美妆课代表", "type": "comment", "sentiment": "pos"},
        {"user": "美妆课代表", "type": "share", "sentiment": ""},
        {"user": "美妆课代表", "type": "comment", "sentiment": "pos"},
        {"user": "美妆课代表", "type": "like", "sentiment": ""},
        {"user": "美妆课代表", "type": "comment", "sentiment": "neutral"},
        {"user": "美妆课代表", "type": "comment", "sentiment": "pos"},
        {"user": "美妆课代表", "type": "like", "sentiment": ""},
        {"user": "美妆课代表", "type": "comment", "sentiment": "pos"},
        {"user": "美妆课代表", "type": "collect", "sentiment": ""},
        {"user": "打工人小王", "type": "comment", "sentiment": "neg"},
        {"user": "打工人小王", "type": "comment", "sentiment": "neg"},
        {"user": "打工人小王", "type": "comment", "sentiment": "neutral"},
        {"user": "打工人小王", "type": "comment", "sentiment": "neg"},
        {"user": "打工人小王", "type": "like", "sentiment": ""},
        {"user": "打工人小王", "type": "comment", "sentiment": "neg"},
        {"user": "打工人小王", "type": "comment", "sentiment": "neg"},
        {"user": "打工人小王", "type": "like", "sentiment": ""},
        {"user": "打工人小王", "type": "comment", "sentiment": "neg"},
        {"user": "打工人小王", "type": "comment", "sentiment": "neutral"},
        {"user": "油皮亲妈", "type": "comment", "sentiment": "pos"},
        {"user": "油皮亲妈", "type": "comment", "sentiment": "pos"},
        {"user": "油皮亲妈", "type": "like", "sentiment": ""},
        {"user": "油皮亲妈", "type": "comment", "sentiment": "neutral"},
        {"user": "今天也很困", "type": "comment", "sentiment": "neg"},
        {"user": "匿名潜水员", "type": "comment", "sentiment": "neutral"},
    ],
}

MAINTAIN_ACTION = {
    "感谢回访": "发布后 24 小时内私信/置顶回复感谢（话术由模型按 reply-script-generate 生成，人工确认后发送）",
    "专属福利": "粉丝群专属福利/抽奖需报备主理人确认预算与规则后再执行，不私下承诺",
    "进群邀请": "邀请进核心粉丝群（群人数 > 200 时改为分批邀请，避免触发平台私信任限制流）",
    "内容共创": "高评分铁粉可邀请参与选题投票/产品试用（试用需签收货协议，属商业行为需主理人确认）",
}


def main():
    ap = argparse.ArgumentParser(description="铁粉识别与互动名单流程")
    ap.add_argument("--input", help="流程输入 JSON（account/weeks/interactions）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    if a.demo:
        payload_path = os.path.join(a.outdir, "_demo_input.json")
        at.write_json(DEMO_INPUT, payload_path)
        payload = DEMO_INPUT
    elif a.input:
        payload_path = a.input
        payload = at.read_json(a.input)
    else:
        ap.error("需要 --input / --demo 之一")

    # 步骤 1：上游九宫格分层
    r = subprocess.run(
        [sys.executable, SEGMENT_SCRIPT, "--input", payload_path, "--outdir", a.outdir],
        cwd=FLOW_DIR, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"[失败处理] 上游技能 fan-segmentation-tag 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    seg_js = os.path.join(a.outdir, "segment.json")
    if not os.path.exists(seg_js):
        print(f"[失败处理] 上游产物 {seg_js} 缺失，流程中止。", file=sys.stderr)
        sys.exit(1)
    seg = at.read_json(seg_js)

    # 步骤 2：内置名单加工
    items = seg.get("items", [])
    superfans = [x for x in items if x["分层标签"] == "铁粉候选"]
    soothe = [x for x in items if x["分层标签"] == "需安抚"]
    watch = [x for x in items if x["分层标签"] == "潜在黑粉观察"]

    maintain_rows = []
    for i, x in enumerate(superfans, 1):
        actions = []
        for k, v in MAINTAIN_ACTION.items():
            if k == "内容共创" and x["铁粉评分"] < 70:
                continue  # 评分 < 70 暂不邀共创
            actions.append(f"[待人工确认] {k}：{v}")
        maintain_rows.append({
            "名单序号": i,
            "用户": x["用户"],
            "周均互动": x["周均互动"],
            "正情感率": x["正情感率"],
            "铁粉评分": x["铁粉评分"],
            "建议动作": "；".join(actions) if actions else "常规维护",
            "状态": "待人工确认",
        })
    if not maintain_rows:
        maintain_rows.append({"名单序号": "—", "用户": "（本周无铁粉候选）",
                              "提示": "检查阈值：≥5 次/周 且 正情感率 ≥60%；或延长统计周期"})

    handoff_rows = [{
        "移交项": "铁粉名单（私域转化环节接手）",
        "内容": f"共 {len(superfans)} 人：{'、'.join(x['用户'] for x in superfans) or '无'}",
        "确认点": "主理人勾选同意后才能移交联系方式/建联；未经确认不得私信营销",
    }, {
        "移交项": "需安抚名单（回复工单环节接手）",
        "内容": f"共 {len(soothe)} 人：{'、'.join(x['用户'] for x in soothe) or '无'}",
        "确认点": "2 小时 SLA 内回复；回复内容走 reply-script-advice-flow 生成工单",
    }, {
        "移交项": "潜在黑粉观察名单",
        "内容": f"共 {len(watch)} 人：{'、'.join(x['用户'] for x in watch) or '无'}",
        "确认点": "只记录不互动；升级为高频负面时再转需安抚流程",
    }]

    s = seg["summary"]
    summary = {
        "账号": payload.get("account", "未提供"),
        "统计周数": s["统计周数"],
        "粉丝总数": s["粉丝总数"],
        "铁粉候选": len(superfans),
        "需安抚": len(soothe),
        "潜在黑粉观察": len(watch),
        "TOP 10% 互动占比": s["TOP 10% 粉丝互动占比"],
        "基准": s["行业经验基准"],
        "维护动作数": len(maintain_rows),
        "人工确认点": "名单移交 / 福利发放 / 私信触达 全部需人工确认，脚本与模型不执行任何触达",
        "说明": "名单为机器统计结果；刷量号与语境由模型按 prompt.txt 复核后再进入移交环节",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "铁粉维护名单.xlsx"),
        {
            "铁粉维护名单": maintain_rows,
            "私域移交确认清单": handoff_rows,
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"铁粉维护名单": {"状态": "contains:待人工确认"}},
        widths={"铁粉维护名单": {"建议动作": 60, "用户": 14}},
    )

    result = {
        "flow": "superfan-identify-flow",
        "steps": [
            {"step": 1, "skill": "fan-segmentation-tag", "status": "ok", "output": seg_js},
            {"step": 2, "skill": "（内置）维护动作与移交清单", "status": "ok", "output": xlsx},
        ],
        "summary": summary,
        "files": [xlsx, seg_js],
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "superfan_flow_result.json"))
    print(f"铁粉候选 {len(superfans)} 人，需安抚 {len(soothe)} 人，黑粉观察 {len(watch)} 人")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
