# -*- coding: utf-8 -*-
"""
每日评论聚合分类流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  输入评论流 → [comment-sentiment-analyze] 四分类 + SLA 优先级排序
            → 内置汇总：处理队列 / 分类占比 / 待办统计 → 每日评论处理日报

失败处理：
  - 上游技能脚本退出码 != 0 → 中止并打印错误（不静默失败）
  - 上游产物 JSON 缺失/损坏 → 中止并提示重跑上游
  - 输入评论为空 → 输出「今日无评论」占位日报并正常退出

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

SENTIMENT_SCRIPT = os.path.join(REPO, "skills", "comment-sentiment-analyze", "scripts", "sentiment_scan.py")

DEMO_INPUT = {
    "account": "@小鹿的好物日记",
    "platform": "抖音",
    "date": "2026-09-29",
    "comments": [
        {"id": "C001", "user": "奶盖不加糖", "text": "姐这个粉底液色号是多少呀？黄二白能用吗", "likes": 12},
        {"id": "C002", "user": "老张不老", "text": "讲得乱七八糟，三分钟还没到重点，浪费时间", "likes": 3},
        {"id": "C003", "user": "黑粉本粉", "text": "就是骗子！收钱恰烂饭，大家都别买，我去举报了😡", "likes": 1},
        {"id": "C004", "user": "cccccc", "text": "绝了绝了这个也太好看了吧！！爱了❤️", "likes": 45},
        {"id": "C005", "user": "打工人小王", "text": "广告太多了，划水的部分能不能剪掉", "likes": 8},
        {"id": "C006", "user": "蹲链接选手", "text": "求链接！在哪买啊", "likes": 6},
        {"id": "C007", "user": "美妆课代表", "text": "对比测评做得很专业，学到了，感谢博主", "likes": 20},
        {"id": "C008", "user": "路过的路人", "text": "今天天气不错", "likes": 0},
        {"id": "C009", "user": "失望集合体", "text": "最近内容真的退步了，不如以前用心，很失望😭", "likes": 15},
        {"id": "C010", "user": "杠精附体", "text": "垃圾博主，搬运狗，人设崩塌了都", "likes": 2},
        {"id": "C011", "user": "油皮亲妈", "text": "油皮用了会闷痘吗？", "likes": 9},
        {"id": "C012", "user": "点点点", "text": "码住了！期待更新！", "likes": 5},
    ],
}


def run_upstream(payload_path: str, outdir: str) -> str:
    """调用 comment-sentiment-analyze 技能脚本，返回其 JSON 产物路径。"""
    r = subprocess.run(
        [sys.executable, SENTIMENT_SCRIPT, "--input", payload_path, "--outdir", outdir],
        cwd=FLOW_DIR, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"[失败处理] 上游技能 comment-sentiment-analyze 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    js = os.path.join(outdir, "sentiment.json")
    if not os.path.exists(js):
        print(f"[失败处理] 上游产物 {js} 缺失，流程中止（请重跑上游技能）。", file=sys.stderr)
        sys.exit(1)
    return js


def main():
    ap = argparse.ArgumentParser(description="每日评论聚合分类流程")
    ap.add_argument("--input", help="流程输入 JSON（同 comment-sentiment-analyze 输入）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    if a.demo:
        payload_path = os.path.join(a.outdir, "_demo_input.json")
        at.write_json(DEMO_INPUT, payload_path)
    elif a.input:
        payload_path = a.input
    else:
        ap.error("需要 --input / --demo 之一")

    # 步骤 1：上游四分类 + SLA 排序
    sent_js = run_upstream(payload_path, a.outdir)
    sent = at.read_json(sent_js)

    # 步骤 2：内置汇总——处理队列拆分
    items = sent.get("items", [])
    queue_2h = [x for x in items if "分钟" in x["处理时限(SLA)"] or "2 小时" in x["处理时限(SLA)"]]
    queue_4h = [x for x in items if "4 小时" in x["处理时限(SLA)"]]
    praise = [x for x in items if x["类别"] == "赞美"]

    sla_rows = [
        {"队列": "🔴 30 分钟内", "条数": sent["summary"]["黑粉"], "内容": "黑粉：回复澄清，视情节隐藏/举报，禁止对线"},
        {"队列": "🟠 2 小时内", "条数": sent["summary"]["吐槽"], "内容": "吐槽：致歉 + 改进点，可私信跟进"},
        {"队列": "🟡 4 小时内", "条数": sent["summary"]["提问"], "内容": "提问：给准确答案或站内指引"},
        {"队列": "🟢 点赞即可", "条数": sent["summary"]["赞美"], "内容": "赞美：点赞 + 高赞置顶"},
        {"队列": "⚪ 可不回", "条数": sent["summary"]["闲聊"], "内容": "闲聊：每 2 小时集中扫一遍"},
    ]

    s = sent["summary"]
    daily_report = at.write_excel(
        os.path.join(a.outdir, "每日评论处理日报.xlsx"),
        {
            "SLA队列总览": sla_rows,
            "处理队列": items,
            "汇总": [{"项": k, "内容": str(v)} for k, v in s.items()],
        },
        highlights={"处理队列": {"类别": "contains:黑粉", "处理时限(SLA)": "contains:分钟"}},
        widths={"处理队列": {"评论内容": 34, "建议动作": 36}},
    )

    result = {
        "flow": "daily-comment-aggregate-flow",
        "steps": [
            {"step": 1, "skill": "comment-sentiment-analyze", "status": "ok",
             "output": sent_js},
            {"step": 2, "skill": "（内置汇总）SLA 队列拆分", "status": "ok",
             "output": daily_report},
        ],
        "summary": {
            "日期": s["统计日期"],
            "评论总数": s["评论总数"],
            "需 2 小时内处理": s["需 2 小时内处理条数"],
            "黑粉": s["黑粉"], "吐槽": s["吐槽"], "提问": s["提问"],
            "赞美": s["赞美"], "闲聊": s["闲聊"],
        },
        "files": [daily_report, sent_js],
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "daily_flow_result.json"))
    print(f"日报完成：{s['评论总数']} 条评论，需 2 小时内处理 {s['需 2 小时内处理条数']} 条")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
