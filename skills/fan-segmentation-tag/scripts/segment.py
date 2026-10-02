# -*- coding: utf-8 -*-
"""
粉丝分层打标器 —— 互动频次 × 情感倾向二维矩阵的确定性分层。

职责边界：本脚本只做**互动记录的频次/情感统计、矩阵分层、铁粉评分与产物生成**
（机器的强项）。个别用户的语境甄别（如刷量号、互赞群）由模型按 prompt.txt 复核。

二维矩阵（判定标准，全部量化）：
  互动频次：高频 ≥ 5 次/周；中频 2-4 次/周；低频 < 2 次/周
  情感倾向：正情感率 = 正面互动 / (正面 + 负面)；正 ≥ 60%、中性 40%-60%、负 < 40%
  九宫格标签：高频正=铁粉候选 / 高频中性=高潜互动 / 高频负=需安抚 / 低频负=潜在黑粉观察 …
  经验基准：1% 超级用户约贡献 90% 互动；脚本输出本账号实际集中度供对照

用法：
  python segment.py --input input.json --outdir out
  python segment.py --demo

产物：
  out/粉丝分层清单.xlsx   分层明细 / 铁粉名单 / 集中度基准 / 汇总
  out/粉丝分层结构.png    各层人数柱状图
  out/segment.json        机器可读结果（供工作流读取）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py。请确认技能位于 <repo>/skills/<slug>/scripts/ 下，"
          "且 <repo>/lib/assettools.py 存在。", file=sys.stderr)
    sys.exit(2)

VALID_TYPES = {"comment", "like", "dm", "share", "collect"}
VALID_SENT = {"pos", "neg", "neutral", ""}

DEMO = {
    "account": "@小鹿的好物日记",
    "weeks": 2,
    "interactions": [
        # 铁粉候选：每周互动 ≥5 次且以正面为主
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
        {"user": "cccccc", "type": "comment", "sentiment": "pos"},
        {"user": "cccccc", "type": "like", "sentiment": ""},
        {"user": "cccccc", "type": "comment", "sentiment": "pos"},
        {"user": "cccccc", "type": "like", "sentiment": ""},
        {"user": "cccccc", "type": "comment", "sentiment": "pos"},
        {"user": "cccccc", "type": "share", "sentiment": ""},
        {"user": "cccccc", "type": "comment", "sentiment": "pos"},
        {"user": "cccccc", "type": "like", "sentiment": ""},
        {"user": "cccccc", "type": "comment", "sentiment": "pos"},
        {"user": "cccccc", "type": "like", "sentiment": ""},
        # 需安抚：高频但负面居多
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
        # 中频正面 → 活跃粉丝
        {"user": "油皮亲妈", "type": "comment", "sentiment": "pos"},
        {"user": "油皮亲妈", "type": "comment", "sentiment": "pos"},
        {"user": "油皮亲妈", "type": "like", "sentiment": ""},
        {"user": "油皮亲妈", "type": "comment", "sentiment": "neutral"},
        {"user": "蹲链接选手", "type": "comment", "sentiment": "neutral"},
        {"user": "蹲链接选手", "type": "comment", "sentiment": "neutral"},
        {"user": "点点点", "type": "like", "sentiment": ""},
        {"user": "点点点", "type": "comment", "sentiment": "pos"},
        {"user": "点点点", "type": "like", "sentiment": ""},
        # 低频各组
        {"user": "路过的路人", "type": "like", "sentiment": ""},
        {"user": "今天也很困", "type": "comment", "sentiment": "neg"},
        {"user": "匿名潜水员", "type": "comment", "sentiment": "neutral"},
    ],
}


def bucket_freq(per_week: float) -> str:
    if per_week >= 5:
        return "高频"
    if per_week >= 2:
        return "中频"
    return "低频"


def bucket_sent(rate: float) -> str:
    if rate >= 0.6:
        return "正面"
    if rate >= 0.4:
        return "中性"
    return "负面"


LABEL = {
    ("高频", "正面"): "铁粉候选",
    ("高频", "中性"): "高潜互动",
    ("高频", "负面"): "需安抚",
    ("中频", "正面"): "活跃粉丝",
    ("中频", "中性"): "普通互动",
    ("中频", "负面"): "预警观察",
    ("低频", "正面"): "好感路人",
    ("低频", "中性"): "路人",
    ("低频", "负面"): "潜在黑粉观察",
}

ACTION = {
    "铁粉候选": "重点维护：感谢 + 专属福利（人工确认后私信）；优先邀请进粉丝群",
    "高潜互动": "提升粘性：回复提问 + 引导关注，观察 2 周是否升级铁粉",
    "需安抚": "2 小时内回复致歉并给改进点；禁止删除负面评论（除非违规）",
    "活跃粉丝": "点赞互动 + 偶尔翻牌，培养为中频以上正面",
    "普通互动": "常规互动即可",
    "预警观察": "记录负面主题，连续 2 周负面则转入需安抚处理",
    "好感路人": "内容触达即可",
    "路人": "不主动互动",
    "潜在黑粉观察": "不主动互动；若升级为高频负面转「需安抚」，恶意攻击按黑粉流程",
}


def build(payload, outdir):
    account = payload.get("account", "未提供")
    weeks = float(payload.get("weeks") or 1) or 1
    inter = payload.get("interactions", [])

    stat = defaultdict(lambda: {"total": 0, "pos": 0, "neg": 0, "dm": 0})
    for it in inter:
        t = str(it.get("type", "")).lower()
        if t not in VALID_TYPES:
            continue
        s = str(it.get("sentiment", "")).lower()
        if s not in VALID_SENT:
            s = ""
        u = stat[it.get("user", "未知")]
        u["total"] += 1
        if s == "pos":
            u["pos"] += 1
        elif s == "neg":
            u["neg"] += 1
        if t == "dm":
            u["dm"] += 1

    rows, matrix_counts = [], defaultdict(int)
    for user, u in sorted(stat.items(), key=lambda kv: -kv[1]["total"]):
        per_week = round(u["total"] / weeks, 1)
        base = u["pos"] + u["neg"]
        rate = round(u["pos"] / base, 2) if base else 0.5
        fb, sb = bucket_freq(per_week), bucket_sent(rate)
        label = LABEL[(fb, sb)]
        matrix_counts[label] += 1
        # 铁粉评分：频次(50) + 正情感率(30) + 私信深度(20)，minmax 归一到 0-100
        f_score = at.minmax_score(per_week, 0, 7)
        s_score = rate * 100
        d_score = at.minmax_score(u["dm"], 0, 2)
        score, _ = at.weighted_score(
            {"频次": f_score, "正情感率": s_score, "私信深度": d_score},
            {"频次": 0.5, "正情感率": 0.3, "私信深度": 0.2})
        rows.append({
            "用户": user,
            "互动总数": u["total"],
            "周均互动": per_week,
            "频次档": fb,
            "正面互动": u["pos"],
            "负面互动": u["neg"],
            "正情感率": f"{rate:.0%}",
            "情感档": sb,
            "分层标签": label,
            "铁粉评分": score,
            "建议动作": ACTION[label],
        })
    rows.sort(key=lambda r: -r["铁粉评分"])

    fans = [r for r in rows]
    total_inter = sum(u["total"] for u in stat.values()) or 1
    fans_sorted = sorted(stat.items(), key=lambda kv: -kv[1]["total"])
    top10pct_n = max(1, round(len(fans_sorted) * 0.1))
    top10_share = sum(v["total"] for _, v in fans_sorted[:top10pct_n]) / total_inter
    benchmark = {
        "粉丝总数": len(stat),
        "互动总数": total_inter,
        "统计周数": weeks,
        "TOP 10% 粉丝互动占比": f"{top10_share:.0%}",
        "行业经验基准": "1% 超级用户约贡献 90% 互动；小样本下 TOP 10% 占比 ≥ 60% 即属健康头部集中",
        "铁粉候选数": matrix_counts.get("铁粉候选", 0),
        "需安抚数": matrix_counts.get("需安抚", 0),
        "潜在黑粉观察数": matrix_counts.get("潜在黑粉观察", 0),
        "说明": "分层为频次×情感的机器统计；刷量号/互赞群须由模型按 prompt.txt 复核后再进名单",
    }

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "粉丝分层清单.xlsx"),
        {
            "分层明细": rows,
            "铁粉名单": [r for r in rows if r["分层标签"] == "铁粉候选"]
                        or [{"用户": "（本周无铁粉候选）"}],
            "集中度基准": [{"项": k, "内容": str(v)} for k, v in benchmark.items()],
        },
        highlights={
            "分层明细": {"分层标签": "contains:需安抚"},
            "铁粉名单": {"分层标签": "contains:铁粉"},
        },
        widths={"分层明细": {"建议动作": 40, "用户": 16}},
    )
    labels = ["铁粉候选", "高潜互动", "需安抚", "活跃粉丝", "普通互动",
              "预警观察", "好感路人", "路人", "潜在黑粉观察"]
    chart = at.bar_chart(
        os.path.join(outdir, "粉丝分层结构.png"),
        [l for l in labels if matrix_counts.get(l)],
        [matrix_counts[l] for l in labels if matrix_counts.get(l)],
        title="粉丝分层结构（人数）", ylabel="人数", horizontal=True,
    )
    js = at.write_json({"summary": benchmark, "items": rows,
                        "generated_at": at.stamp(),
                        "note": "机器统计结果；异常账号由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "segment.json"))
    return {"files": [xlsx, chart, js], "summary": benchmark,
            "superfans": [r["用户"] for r in rows if r["分层标签"] == "铁粉候选"]}


def main():
    ap = argparse.ArgumentParser(description="粉丝分层打标")
    ap.add_argument("--input", help="输入 JSON（account/weeks/interactions）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    if a.demo:
        payload = DEMO
    elif a.input:
        payload = at.read_json(a.input)
    else:
        ap.error("需要 --input / --demo 之一")

    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"粉丝 {s['粉丝总数']} 人 —— 铁粉候选 {s['铁粉候选数']} / 需安抚 {s['需安抚数']} "
          f"/ 黑粉观察 {s['潜在黑粉观察数']}；TOP 10% 互动占比 {s['TOP 10% 粉丝互动占比']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
