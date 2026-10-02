# -*- coding: utf-8 -*-
"""
评论情感四分类扫描器 —— 词表 + 表情权重的确定性分类与优先级排序。

职责边界：本脚本只做**词表/表情的确定性匹配、强度打分、SLA 排序与产物生成**
（这是机器的强项）。反讽识别、语境判断、黑粉与重度吐槽的二次甄别由模型按
prompt.txt 完成（这是模型的强项）。

四分类：提问 / 赞美 / 吐槽 / 黑粉
优先级（SLA）：黑粉 30 分钟内 > 吐槽 2 小时内 > 提问 4 小时内 > 赞美 点赞即可

用法：
  python sentiment_scan.py --input input.json --outdir out
  python sentiment_scan.py --demo                # 用内置样例跑一遍

产物：
  out/评论分类处理清单.xlsx   分类明细（黑粉标红）/ 处理队列 / 汇总
  out/评论情感分布.png        四分类占比饼图
  out/sentiment.json          机器可读结果（供工作流读取）
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


# ---------------------------------------------------------------- 词表
# 每张表：(词/正则, 权重)。权重用于情绪强度打分（1-5）。

# 黑粉词：人身攻击 / 动机质疑 / 恶意举报 / 主动扩散负面。判定即最高优先级。
BLACK_WORDS = [
    (r"垃圾|废物|脑残|智障|恶心|呸|滚|傻[逼bBxX]|又蠢", 3),
    (r"骗子|骗钱|割韭菜|恰烂饭|收钱办事|充钱|水军|托", 3),
    (r"造假|假货|抄袭狗|偷内容|搬运狗|卖惨|人设崩塌|塌房", 2),
    (r"举报你|举报了|投诉你|挂你|曝光你|让大家避雷|都别买|取关了再见|脱粉回踩", 2),
]

# 吐槽词：负面但指向内容/产品/服务，未攻击人格。
COMPLAIN_WORDS = [
    (r"失望|难看|太差|好差|退步|不如以前|变味|水了|划水|敷衍|糊弄", 2),
    (r"更新太慢|鸽了|拖更|广告太多|全是广告|太硬了|恰饭太明显|内容注水", 2),
    (r"无聊|没意思|浪费时间|看不懂|讲得乱|噪音|画质差|收音差|剪辑乱", 1),
    (r"无语|尴尬|尬|离谱|翻车|踩坑|智商税|不值|后悔", 1),
]

# 提问线索分级：强线索单独即可判提问；弱线索（信息寻求词）须无赞美/正表情佐证才判提问，
# 避免「这个色号太好看了」被误判为提问。
QUESTION_STRONG = [
    r"？|\?|吗[？?。！!～~]*$|呢[？?。！!～~]*$",
    r"怎么|怎样|怎么样|如何|多少|几个|哪[里儿个]|什么牌|什么时候|多久",
    r"求[分享推荐链接教程测评]|请问|有没有|能不能|可以吗|求告知|蹲一个|蹲链接",
]
QUESTION_WEAK = [
    r"链接|型号|色号|尺码|尺寸|价格|多少钱|教程|测评|对比|参数",
]

# 赞美词：正向表达。
PRAISE_WORDS = [
    (r"好看|漂亮|绝了|绝美|爱了|太棒|厉害|牛|优秀|宝藏|喜欢|支持|赞", 1),
    (r"感谢|谢谢|学到了|有用|实用|干货|清晰|专业|良心|靠谱|安利|收藏了|三连|关注了", 1),
    (r"期待更新|加油|冲|冲鸭|码住|马克|跟着买|已下单|回购", 1),
]

# 表情权重：强负表情权重高，正表情作为赞美证据。
NEG_EMOJI = {"😡": 2, "🤬": 2, "😭": 1, "😤": 1, "😒": 1, "💀": 1, "👎": 1, "🙄": 1}
POS_EMOJI = {"🙂": 1, "😊": 1, "🥰": 1, "😍": 1, "❤️": 1, "❤": 1, "👍": 1, "🔥": 1, "🎉": 1, "💪": 1}

SLA = {
    "黑粉": ("30 分钟内", "回复澄清事实，视情节隐藏/举报；禁止对线、禁止拉踩回击"),
    "吐槽": ("2 小时内", "真诚致歉 + 给出具体改进点；可私信跟进，避免评论区反复拉扯"),
    "提问": ("4 小时内", "给出准确答案或站内指引；缺信息先回复「已记录，X 小时内补答案」"),
    "赞美": ("点赞即可", "点赞 + 高赞评论置顶；不逐条复制粘贴式回复"),
    "闲聊": ("可不回", "集中每 2 小时扫一遍，有梗可玩则轻互动"),
}

DEMO = {
    "account": "@小鹿的好物日记",
    "platform": "抖音",
    "date": "2026-09-29",
    "comments": [
        {"id": "C001", "user": "奶盖不加糖", "text": "姐这个粉底液色号是多少呀？黄二白能用吗", "likes": 12},
        {"id": "C002", "user": "老张不老", "text": "讲得乱七八糟，三分钟还没到重点，浪费时间", "likes": 3},
        {"id": "C003", "user": "黑粉本粉", "text": "就是骗子！收钱恰烂饭，大家都别买，我去举报了😡", "likes": 1},
        {"id": "C004", "user": "cccccc", "text": "绝了绝了这个色号也太好看了吧！！爱了❤️", "likes": 45},
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


def _count_hits(text: str, table) -> tuple[int, list[str]]:
    hits, weight = [], 0
    for pat, w in table:
        for m in re.finditer(pat, text):
            hits.append(m.group(0))
            weight += w
    return weight, hits


def classify(text: str) -> dict:
    """规则树：黑粉 → 吐槽 → 提问 → 赞美 → 闲聊。返回类别/强度/依据。"""
    black_w, black_hits = _count_hits(text, BLACK_WORDS)
    complain_w, complain_hits = _count_hits(text, COMPLAIN_WORDS)
    praise_w, praise_hits = _count_hits(text, PRAISE_WORDS)
    q_strong = [c for c in QUESTION_STRONG if re.search(c, text)]
    q_weak = [c for c in QUESTION_WEAK if re.search(c, text)]
    is_question = bool(q_strong) or (bool(q_weak) and not praise_hits and not pos_emoji)
    neg_emoji = [e for e in NEG_EMOJI if e in text]
    pos_emoji = [e for e in POS_EMOJI if e in text]
    bang = bool(re.search(r"[！!]{2,}|[？?]{2,}", text))

    intensity = 1
    if black_w or complain_w:
        intensity += black_w + complain_w
    intensity += sum(NEG_EMOJI[e] for e in neg_emoji)
    intensity += sum(POS_EMOJI[e] for e in pos_emoji)
    if bang:
        intensity += 1
    intensity = max(1, min(5, intensity))

    evidence = []
    if black_hits:
        evidence += [f"黑粉词:{w}" for w in black_hits[:3]]
    if complain_hits:
        evidence += [f"吐槽词:{w}" for w in complain_hits[:3]]
    if praise_hits:
        evidence += [f"赞美词:{w}" for w in praise_hits[:2]]
    if neg_emoji:
        evidence.append(f"强负表情:{''.join(neg_emoji)}")
    if pos_emoji:
        evidence.append(f"正表情:{''.join(pos_emoji)}")
    if q_strong:
        evidence.append("疑问句式(强)")
    elif q_weak:
        evidence.append("信息寻求词(弱)")
    if bang:
        evidence.append("重复标点")

    if black_hits:
        cat = "黑粉"
    elif (complain_hits or neg_emoji) and not is_question:
        cat = "吐槽"
    elif complain_hits or neg_emoji:  # 负面 + 疑问：先安抚情绪，归吐槽并标注
        cat = "吐槽"
        evidence.append("含问题需一并回复")
    elif is_question:
        cat = "提问"
    elif praise_hits or pos_emoji:
        cat = "赞美"
    else:
        cat = "闲聊"

    return {"类别": cat, "强度": intensity, "依据": "；".join(evidence) if evidence else "无显著线索"}


def build(payload, outdir):
    account = payload.get("account", "未提供")
    platform = payload.get("platform", "通用")
    date = payload.get("date", "")
    comments = payload.get("comments", [])

    at.need("openpyxl")
    rows = []
    for c in comments:
        r = classify(str(c.get("text", "")))
        sla, action = SLA[r["类别"]]
        rows.append({
            "评论ID": c.get("id", ""),
            "用户": c.get("user", ""),
            "评论内容": str(c.get("text", "")),
            "点赞": c.get("likes", 0),
            "类别": r["类别"],
            "情绪强度": r["强度"],
            "处理时限(SLA)": sla,
            "建议动作": action,
            "命中依据": r["依据"],
        })
    order = {"黑粉": 0, "吐槽": 1, "提问": 2, "赞美": 3, "闲聊": 4}
    rows.sort(key=lambda x: (order[x["类别"]], -int(x["情绪强度"]), -int(x["点赞"])))

    counts = {}
    for r in rows:
        counts[r["类别"]] = counts.get(r["类别"], 0) + 1
    n = len(rows) or 1
    summary = {
        "账号": account,
        "平台": platform,
        "统计日期": date,
        "评论总数": len(rows),
        "黑粉": counts.get("黑粉", 0),
        "吐槽": counts.get("吐槽", 0),
        "提问": counts.get("提问", 0),
        "赞美": counts.get("赞美", 0),
        "闲聊": counts.get("闲聊", 0),
        "黑粉占比": f"{counts.get('黑粉', 0) / n * 100:.1f}%",
        "负类合计占比": f"{(counts.get('黑粉', 0) + counts.get('吐槽', 0)) / n * 100:.1f}%",
        "需 2 小时内处理条数": counts.get("黑粉", 0) + counts.get("吐槽", 0),
        "说明": "分类为词表机器判定；反讽与语境须由模型按 prompt.txt 复核，对外回复保留人工确认",
    }

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "评论分类处理清单.xlsx"),
        {
            "处理队列": rows,
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={
            "处理队列": {"类别": "contains:黑粉", "处理时限(SLA)": "contains:分钟"},
        },
        widths={"处理队列": {"评论内容": 34, "建议动作": 38, "命中依据": 26}},
    )
    pie = at.pie_chart(
        os.path.join(outdir, "评论情感分布.png"),
        [k for k in ["黑粉", "吐槽", "提问", "赞美", "闲聊"] if counts.get(k)],
        [counts[k] for k in ["黑粉", "吐槽", "提问", "赞美", "闲聊"] if counts.get(k)],
        title=f"评论情感四分占比（{date or '本次'}）",
    )
    js = at.write_json({"summary": summary, "items": rows, "generated_at": at.stamp(),
                        "note": "词表机器分类结果；反讽/语境由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "sentiment.json"))
    return {"files": [xlsx, pie, js], "summary": summary, "count": len(rows)}


def main():
    ap = argparse.ArgumentParser(description="评论情感四分类扫描")
    ap.add_argument("--input", help="输入 JSON（account/platform/date/comments）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    if a.demo:
        payload = DEMO
    elif a.input:
        payload = at.read_json(a.input)
    else:
        ap.error("需要 --input / --demo 之一")

    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"共 {r['count']} 条 —— 黑粉 {s['黑粉']} / 吐槽 {s['吐槽']} / 提问 {s['提问']} "
          f"/ 赞美 {s['赞美']} / 闲聊 {s['闲聊']}；需 2 小时内处理 {s['需 2 小时内处理条数']} 条")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
