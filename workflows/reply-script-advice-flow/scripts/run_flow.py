# -*- coding: utf-8 -*-
"""
回复话术建议流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  当日评论流 → [comment-sentiment-analyze] 四分类 + SLA 排序 → 取高优队列（黑粉/吐槽/提问）
  回复草稿流 → [persona-voice-library] 一致性检查（称呼/口头禅/句长/禁用词，≥80 分达标）
  两路汇合 → 回复工单（逐条对齐：草稿 ↔ 评论；缺草稿的高优评论标「待生成」，
             交模型按 reply-script-generate 的 prompt 生成后再过一致性检查）
  → 人工确认后才发布（合规红线，脚本不执行任何发布动作）

失败处理：
  - 任一上游技能退出码 != 0 或产物缺失 → 中止并打印错误
  - 草稿引用了不存在的评论 ID → 该草稿标「评论不存在」并保留在工单中人工处理
  - 高优评论无对应草稿 → 不中断，工单标「待生成」
  - 草稿触发合规否决 → 工单标「禁止发布」，给出违禁明细

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
VOICE_SCRIPT = os.path.join(REPO, "skills", "persona-voice-library", "scripts", "voice_check.py")

DEMO_INPUT = {
    "account": "@小鹿的好物日记",
    "date": "2026-09-29",
    "comments": [
        {"id": "C001", "user": "奶盖不加糖", "text": "姐这个粉底液色号是多少呀？黄二白能用吗", "likes": 12},
        {"id": "C002", "user": "老张不老", "text": "讲得乱七八糟，三分钟还没到重点，浪费时间", "likes": 3},
        {"id": "C003", "user": "黑粉本粉", "text": "就是骗子！收钱恰烂饭，大家都别买，我去举报了😡", "likes": 1},
        {"id": "C005", "user": "打工人小王", "text": "广告太多了，划水的部分能不能剪掉", "likes": 8},
        {"id": "C006", "user": "蹲链接选手", "text": "求链接！在哪买啊", "likes": 6},
        {"id": "C011", "user": "油皮亲妈", "text": "油皮用了会闷痘吗？", "likes": 9},
    ],
    "voice": {
        "persona": "@小鹿的好物日记 —— 闺蜜式美妆好物分享",
        "platform": "抖音",
        "称呼": ["宝子", "姐妹", "家人们"],
        "口头禅": ["码住", "冲鸭", "亲测", "说真的"],
        "句长上限": 20,
        "禁用词": ["绝绝子", "yyds", "亲～"],
    },
    "drafts": [
        {"id": "D1", "comment_id": "C001", "text": "宝子，黄二白建议选 12 号，亲测不假白，色号对比在置顶视频码住～"},
        {"id": "D2", "comment_id": "C002", "text": "姐妹说得对！节奏问题这期就改，下期开头 30 秒直接上重点说真的。"},
        {"id": "D3", "comment_id": "C003", "text": "亲～本产品 100% 正品保证，加微信还有专属优惠哦！"},
        {"id": "D4", "comment_id": "C005", "text": "收到！以后广告会提前说明，剪辑节奏在改了。"},
        {"id": "D5", "comment_id": "C006", "text": "宝子，链接在小黄车第 3 个～"},
    ],
}

HIGH_PRIORITY = {"黑粉", "吐槽", "提问"}


def run_skill(script: str, payload_path: str, outdir: str, name: str) -> str:
    r = subprocess.run(
        [sys.executable, script, "--input", payload_path, "--outdir", outdir],
        cwd=FLOW_DIR, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"[失败处理] 上游技能 {name} 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    return name


def main():
    ap = argparse.ArgumentParser(description="回复话术建议流程")
    ap.add_argument("--input", help="流程输入 JSON（comments/voice/drafts）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    at.ensure_outdir(a.outdir)
    if a.demo:
        # 情感与语气两步需要不同输入：分别落盘
        sent_in = os.path.join(a.outdir, "_demo_sent_input.json")
        voice_in = os.path.join(a.outdir, "_demo_voice_input.json")
        at.write_json({"account": DEMO_INPUT["account"], "platform": "抖音",
                       "date": DEMO_INPUT["date"], "comments": DEMO_INPUT["comments"]}, sent_in)
        at.write_json({"voice": DEMO_INPUT["voice"], "drafts": DEMO_INPUT["drafts"]}, voice_in)
        payload = DEMO_INPUT
    elif a.input:
        payload = at.read_json(a.input)
        sent_in = voice_in = a.input
    else:
        ap.error("需要 --input / --demo 之一")

    # 步骤 1：评论四分类 + SLA
    run_skill(SENTIMENT_SCRIPT, sent_in, a.outdir, "comment-sentiment-analyze")
    sent = at.read_json(os.path.join(a.outdir, "sentiment.json"))
    by_comment = {x["评论ID"]: x for x in sent.get("items", [])}

    # 步骤 2：草稿一致性检查
    run_skill(VOICE_SCRIPT, voice_in, a.outdir, "persona-voice-library")
    voice = at.read_json(os.path.join(a.outdir, "voice_check.json"))
    draft_by_comment = {d.get("对应评论", d.get("comment_id", "")): d for d in voice.get("items", [])}

    # 步骤 3：汇合生成工单
    rows = []
    for cid, c in by_comment.items():
        if c["类别"] not in HIGH_PRIORITY:
            continue
        d = draft_by_comment.get(cid)
        if d is None:
            rows.append({
                "评论ID": cid, "用户": c["用户"], "类别": c["类别"],
                "处理时限(SLA)": c["处理时限(SLA)"],
                "评论摘要": c["评论内容"][:30],
                "草稿ID": "—", "一致性得分": "—", "工单状态": "待生成",
                "下一步": "交模型按 reply-script-generate 生成草稿 → 过一致性检查 → 人工确认",
            })
            continue
        if d["判定"] == "达标":
            status, nxt = "待人工确认", "人工确认后发布（发布动作永远由人执行）"
        elif "合规否决" in d["判定"]:
            status, nxt = "禁止发布", "按违禁明细改写：去掉承诺/导流/绝对化，再过一致性检查"
        else:
            status, nxt = "需改写", "补齐缺失项（称呼/口头禅/句长）后重检"
        rows.append({
            "评论ID": cid, "用户": c["用户"], "类别": c["类别"],
            "处理时限(SLA)": c["处理时限(SLA)"],
            "评论摘要": c["评论内容"][:30],
            "草稿ID": d["草稿ID"], "一致性得分": d["一致性得分"],
            "工单状态": status, "下一步": nxt,
        })

    n = len(rows) or 1
    summary = {
        "账号": payload.get("account", "未提供"),
        "日期": payload.get("date", ""),
        "高优评论数": len(rows),
        "黑粉/吐槽/提问": f"{sent['summary']['黑粉']}/{sent['summary']['吐槽']}/{sent['summary']['提问']}",
        "已备草稿": sum(1 for x in rows if x["草稿ID"] not in ("—",)),
        "待生成": sum(1 for x in rows if x["工单状态"] == "待生成"),
        "待人工确认": sum(1 for x in rows if x["工单状态"] == "待人工确认"),
        "需改写": sum(1 for x in rows if x["工单状态"] == "需改写"),
        "禁止发布": sum(1 for x in rows if x["工单状态"] == "禁止发布"),
        "发布率红线": "0% —— 脚本与模型均不执行发布；所有回复经人工确认后才对外",
        "覆盖率参考": "高优评论草稿覆盖率 < 80% 说明备稿不足，需扩大 draft 覆盖",
        "说明": "工单为机器对齐结果；草稿生成与语气润色由模型按 prompt.txt 完成",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "回复工单.xlsx"),
        {
            "回复工单": rows or [{"评论ID": "（无高优评论）"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"回复工单": {"工单状态": "contains:禁止发布"}},
        widths={"回复工单": {"下一步": 40, "评论摘要": 26}},
    )

    result = {
        "flow": "reply-script-advice-flow",
        "steps": [
            {"step": 1, "skill": "comment-sentiment-analyze", "status": "ok",
             "output": os.path.join(a.outdir, "sentiment.json")},
            {"step": 2, "skill": "persona-voice-library", "status": "ok",
             "output": os.path.join(a.outdir, "voice_check.json")},
            {"step": 3, "skill": "reply-script-generate（工单对齐/缺稿标记）", "status": "ok",
             "output": xlsx},
        ],
        "summary": summary,
        "files": [xlsx, os.path.join(a.outdir, "sentiment.json"),
                  os.path.join(a.outdir, "voice_check.json")],
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "advice_flow_result.json"))
    print(f"高优评论 {len(rows)} 条：待人工确认 {summary['待人工确认']}，"
          f"待生成 {summary['待生成']}，禁止发布 {summary['禁止发布']}")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
