# -*- coding: utf-8 -*-
"""
人设语气一致性检查器 —— 语气库档案核对与回复草稿的一致性打分。

职责边界：本脚本只做**称呼/口头禅命中率、句长、禁用词与合规词表的确定性检查**
（机器的强项）。语气是否「像本人」、梗用得是否自然，由模型按 prompt.txt 判断。

一致性评分（满分 100，≥ 80 达标）：
  称呼命中（命中语气库称呼词表任一）…… 40 分
  口头禅命中（命中口头禅词表任一）…… 20 分
  句长达标（平均句长 ≤ 上限，默认 20 字/句）…… 20 分
  零违禁（禁用词 + 效果承诺 + 绝对化用语 + 站外导流 全部未命中）…… 20 分
  任一违禁词命中 → 该项 0 分并标红，整条判「不达标（合规否决）」

用法：
  python voice_check.py --input input.json --outdir out
  python voice_check.py --demo

产物：
  out/语气一致性检查.xlsx   语气库档案 / 检查明细（不达标标红）/ 汇总
  out/voice_scores.png      各草稿一致性得分柱状图
  out/voice_check.json      机器可读结果（供工作流读取）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

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

PASS_LINE = 80        # 一致性达标线
DEFAULT_MAX_LEN = 20  # 默认句长上限（字/句）

# 合规词表（无论语气库如何设置都必须拦截）——面向评论区回复场景
COMPLIANCE = {
    "效果承诺": [(r"保证|一定[能让]|百分[之百]|100\s*%|绝对[能会]|肯定[能让]|包好|无效退款", "回复不得承诺内容效果或商品效果")],
    "绝对化用语": [(r"最好|最佳|第一(?!时间)|顶级|绝无仅有|全网最|史上最", "《广告法》第九条：禁用绝对化用语")],
    "站外导流": [(r"加微信|加V|\+v|加v|VX|vx|私信发你|看主页私|扫码|QQ群", "平台规则：评论区不得引导站外交易/导流")],
    "诱导互动": [(r"点赞过[0-9]+就|转发抽奖|评论[0-9]+楼送|双击么么哒", "平台规范：诱导性互动话术有限流风险")],
}

DEMO = {
    "voice": {
        "persona": "@小鹿的好物日记 —— 闺蜜式美妆好物分享，B 端合作号不可用网感词",
        "platform": "抖音",
        "audience": "18-30 岁女性，学生党与职场新人为主",
        "称呼": ["宝子", "姐妹", "家人们"],
        "口头禅": ["码住", "冲鸭", "亲测", "说真的"],
        "句长上限": 20,
        "禁用词": ["绝绝子", "yyds", "亲～", "宝～", "无人机", "家银们"],
        "禁用词理由": "官方合作账号不用过时网络梗；「亲～」是电商客服腔，与闺蜜人设冲突",
    },
    "drafts": [
        {"id": "D1", "comment_id": "C001", "text": "宝子，黄二白建议选 12 号，亲测不假白，色号对比我置顶视频里有码住～"},
        {"id": "D2", "comment_id": "C005", "text": "姐妹说得对！以后广告内容我会提前说明，剪辑节奏也在改了，感谢反馈说真的。"},
        {"id": "D3", "comment_id": "C006", "text": "链接在小黄车第 3 个哦宝子～"},
        {"id": "D4", "comment_id": "C003", "text": "亲～本产品 100% 正品保证，绝绝子好用，加微信还有专属优惠哦！"},
        {"id": "D5", "comment_id": "C007", "text": "谢谢宝子！下期出全程步骤教程，姐妹们记得码住，更新了第一时间告诉你。"},
        {"id": "D6", "comment_id": "C011", "text": "油皮建议先看第 2 点的持妆实测，本视频实测 8 小时不斑驳，但每个人肤质不同，严重痘痘肌建议先问医生哦。"},
    ],
}


def split_sentences(text: str):
    # 评论回复是口语短句：逗号也作为断句点，否则一整句无句号的长评论会把平均句长撑爆
    parts = re.split(r"[。！？!?~～；;，,\n]+", text)
    return [p for p in (s.strip() for s in parts) if p]


def check_draft(draft: str, voice: dict):
    称呼 = voice.get("称呼", [])
    口头禅 = voice.get("口头禅", [])
    禁用词 = voice.get("禁用词", [])
    max_len = int(voice.get("句长上限") or DEFAULT_MAX_LEN)

    hit_call = [w for w in 称呼 if w and w in draft]
    hit_tick = [w for w in 口头禅 if w and w in draft]
    sents = split_sentences(draft)
    avg_len = round(sum(len(s) for s in sents) / len(sents), 1) if sents else len(draft)
    len_ok = avg_len <= max_len

    banned, compliance = [], []
    for w in 禁用词:
        if w and w in draft:
            banned.append(f"{w}(语气库禁用)")
    for cat, rules in COMPLIANCE.items():
        for pat, why in rules:
            for m in re.finditer(pat, draft):
                compliance.append(f"{cat}:{m.group(0)}（{why}）")
                break  # 每类报一条即可

    s_call = 40 if hit_call else 0
    s_tick = 20 if hit_tick else 0
    s_len = 20 if len_ok else 0
    s_ban = 0 if (banned or compliance) else 20
    score = s_call + s_tick + s_len + s_ban
    veto = bool(banned or compliance)

    evidence = []
    if hit_call:
        evidence.append(f"称呼:{'/'.join(hit_call)}")
    else:
        evidence.append("未命中称呼")
    if hit_tick:
        evidence.append(f"口头禅:{'/'.join(hit_tick)}")
    else:
        evidence.append("未命中口头禅")
    evidence.append(f"平均句长 {avg_len} 字（上限 {max_len}）")
    if banned:
        evidence += banned
    if compliance:
        evidence += compliance

    if veto:
        verdict = "不达标（合规否决）"
    elif score >= PASS_LINE:
        verdict = "达标"
    else:
        verdict = "不达标"

    return {
        "得分": score, "称呼": s_call, "口头禅": s_tick, "句长": s_len, "零违禁": s_ban,
        "平均句长": avg_len, "判语": evidence, "判定": verdict,
    }


def build(payload, outdir):
    voice = payload.get("voice", {})
    drafts = payload.get("drafts", [])

    rows, n_pass = [], 0
    for d in drafts:
        r = check_draft(str(d.get("text", "")), voice)
        if r["判定"] == "达标":
            n_pass += 1
        rows.append({
            "草稿ID": d.get("id", ""),
            "对应评论": d.get("comment_id", ""),
            "回复草稿": str(d.get("text", "")),
            "称呼分": r["称呼"],
            "口头禅分": r["口头禅"],
            "句长分": r["句长"],
            "零违禁分": r["零违禁"],
            "一致性得分": r["得分"],
            "判定": r["判定"],
            "检查明细": "；".join(r["判语"]),
        })

    total = len(rows) or 1
    rate = n_pass / total
    summary = {
        "人设": voice.get("persona", "未提供"),
        "平台/受众": f"{voice.get('platform', '通用')} / {voice.get('audience', '未提供')}",
        "称呼词表": "/".join(map(str, voice.get("称呼", []))),
        "口头禅词表": "/".join(map(str, voice.get("口头禅", []))),
        "句长上限": f"{voice.get('句长上限', DEFAULT_MAX_LEN)} 字/句",
        "语气库禁用词": "/".join(map(str, voice.get("禁用词", [])))
                        + f"（{voice.get('禁用词理由', '')}）",
        "达标线": PASS_LINE,
        "草稿总数": len(rows),
        "达标数": n_pass,
        "达标率": f"{rate:.0%}",
        "达标率参考": "一致性达标率 ≥ 80% 视为人设稳定；连续两批 < 60% 需回炉语气库",
        "合规否决": sum(1 for r in rows if r["判定"] == "不达标（合规否决）"),
        "说明": "机器只查命中率与违禁词；语气自然度由模型按 prompt.txt 复核，对外发布保留人工确认",
    }

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "语气一致性检查.xlsx"),
        {
            "语气库档案": [{"项": k, "内容": str(v)} for k, v in summary.items()],
            "检查明细": rows,
            "汇总": [{"达标草稿": n_pass, "总草稿": len(rows),
                      "达标率": f"{rate:.0%}", "合规否决": summary["合规否决"]}],
        },
        highlights={"检查明细": {"判定": "contains:不达标"}},
        widths={"检查明细": {"回复草稿": 38, "检查明细": 40}},
    )
    chart = at.bar_chart(
        os.path.join(outdir, "voice_scores.png"),
        [r["草稿ID"] for r in rows],
        [r["一致性得分"] for r in rows],
        title=f"各草稿一致性得分（达标线 {PASS_LINE}）", ylabel="得分",
    )
    js = at.write_json({"summary": summary, "items": rows, "generated_at": at.stamp(),
                        "note": "机器检查结果；语气自然度由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "voice_check.json"))
    return {"files": [xlsx, chart, js], "summary": summary,
            "pass_rate": rate, "veto": summary["合规否决"]}


def main():
    ap = argparse.ArgumentParser(description="人设语气一致性检查")
    ap.add_argument("--input", help="输入 JSON（voice/drafts）")
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
    print(f"草稿 {s['草稿总数']} 条 —— 达标 {s['达标数']}（{s['达标率']}），合规否决 {s['合规否决']} 条")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
