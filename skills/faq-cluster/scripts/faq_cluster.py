# -*- coding: utf-8 -*-
"""
高频问题聚类器 —— 相似度聚类的确定性实现（频次排序 + Top 10 FAQ 库）。

职责边界：本脚本只做**文本归一化、相似度计算（字符 bigram Jaccard / 编辑距离比）、
贪心聚类、频次排序与产物生成**（机器的强项）。语义近似但用词完全不同的问法
（如「怎么入手」vs「如何购买」）由模型按 prompt.txt 二次合并。

聚类规则（量化标准）：
  相似度 = max(字符 bigram Jaccard, difflib 编辑距离相似度)
  相似度 ≥ 0.60 归同簇（60% 为默认合并阈值，低于它拆开宁可漏合不可错合）
  簇按总频次降序，Top 10 进 FAQ 库
  覆盖率 = Top 10 簇覆盖题数 / 总题数；< 60% 判定「分类有误/问题过散」，需人工复核

用法：
  python faq_cluster.py --input input.json --outdir out
  python faq_cluster.py --demo

产物：
  out/高频问题聚类.xlsx   问题簇明细 / FAQ库Top10（含答案要点）/ 汇总
  out/faq_top10.png       Top 10 问题频次柱状图
  out/faq_cluster.json    机器可读结果（供工作流读取）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from difflib import SequenceMatcher

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

MERGE_THRESHOLD = 0.60   # 相似度 ≥ 0.60 归同簇
COVERAGE_FLOOR = 0.60    # Top10 覆盖率下限，低于则判定分类有误
TOP_N = 10               # 进入 FAQ 库的簇数

# 关键词 → 标准答案要点（FAQ 库用；命中即给要点，未命中给通用要点）
ANSWER_MAP = [
    (r"链接|在哪买|哪里买|哪里有|求购|怎么买|如何购买|下单|店铺", "给出购买渠道与口径：平台橱窗链接位置 + 备选渠道，注明以官方渠道为准，不引导站外交易"),
    (r"多少钱|价格|价位|贵不贵|值不值|几钱", "给出价格区间与查询口径（活动价/日常价分开说明），不承诺最低价"),
    (r"色号|色号推荐|哪个色|显白", "按肤色给出 2-3 个色号选项 + 试色说明，提示个体差异"),
    (r"油皮|干皮|敏感肌|痘痘|闷痘|过敏|适合什么肤质", "按肤质分类说明适用性，注明仅为经验分享、严重肌肤问题建议就医"),
    (r"教程|怎么用|怎么画|步骤|手法|新手", "给出分步教程要点（≤5 步），并链接往期教程期数"),
    (r"什么时候|更新|下一期|拖更|停更", "说明更新节奏（每周 X 更），预告下一期主题"),
    (r"型号|参数|配置|规格|尺寸|尺码", "列出关键参数对比表口径，注明以商品详情页为准"),
    (r"平价|替代|平替|学生党", "给出平价替代选项与差异说明，不做效果承诺"),
    (r"保质期|真假|鉴别|正品", "说明正品渠道鉴别要点，不替品牌方下结论"),
    (r"好不好用|推荐|值得买吗|测评", "给出适用人群 + 优缺点各 1-2 条，避免绝对化用语"),
]

DEMO = {
    "account": "@小鹿的好物日记",
    "period": "2026-09-23 ~ 2026-09-29",
    "questions": [
        "在哪买", "在哪买啊", "姐妹在哪买",
        "求链接", "求个链接", "求链接！",
        "多少钱", "这个多少钱", "多少钱呀",
        "油皮能用吗", "油皮可以用吗",
        "黄皮色号推荐", "色号推荐",
        "什么时候更新", "什么时候更新呀",
        "有没有平替", "有没有平价替代",
        "新手怎么画", "求新手教程",
        "敏感肌适合吗", "这个是正品吗",
        "贵不贵", "会不会闷痘",
    ],
}


def normalize(text: str) -> str:
    """小写化，去标点/表情/空白，只留中英文与数字。"""
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())
    return text


def bigrams(text: str):
    return set(text[i:i + 2] for i in range(len(text) - 1)) if len(text) > 1 else {text}


def similarity(a: str, b: str) -> float:
    """字符 bigram Jaccard 与编辑距离比取最大值。"""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ba, bb = bigrams(a), bigrams(b)
    jac = len(ba & bb) / len(ba | bb) if ba | bb else 0.0
    ed = SequenceMatcher(None, a, b).ratio()
    return max(jac, ed)


def answer_points(rep: str) -> str:
    for pat, points in ANSWER_MAP:
        if re.search(pat, rep):
            return points
    return "通用要点：先复述问题确认理解，给出可执行答案或说明何时能给出答案；不承诺效果、不引导站外交易"


def build(payload, outdir):
    account = payload.get("account", "未提供")
    period = payload.get("period", "")
    raw = payload.get("questions", [])
    texts = [str(q) if not isinstance(q, dict) else str(q.get("text", "")) for q in raw]

    norm_counter = Counter(normalize(t) for t in texts if normalize(t))
    # 按归一化后频次降序贪心聚类：与已有簇代表相似度 ≥ 0.60 即并入
    clusters = []  # [{members:[原文...], norm, freq}]
    for norm, freq in norm_counter.most_common():
        placed = False
        for c in clusters:
            if similarity(norm, c["norm"]) >= MERGE_THRESHOLD:
                c["freq"] += freq
                c["members"].append(norm)
                placed = True
                break
        if not placed:
            clusters.append({"members": [norm], "norm": norm, "freq": freq})

    clusters.sort(key=lambda c: -c["freq"])
    total_q = sum(c["freq"] for c in clusters) or 1
    top = clusters[:TOP_N]
    coverage = sum(c["freq"] for c in top) / total_q

    cluster_rows = []
    faq_rows = []
    for i, c in enumerate(clusters, 1):
        rep = c["norm"]
        cluster_rows.append({
            "簇ID": f"Q{i:02d}",
            "代表问题": rep,
            "簇内变体数": len(c["members"]),
            "提问频次": c["freq"],
            "占总提问": f"{c['freq'] / total_q:.0%}",
            "是否进FAQ库": "✅ Top10" if i <= TOP_N else "—",
        })
        if i <= TOP_N:
            faq_rows.append({
                "FAQ排名": i,
                "标准问法": rep,
                "提问频次": c["freq"],
                "建议答案要点": answer_points(rep),
                "回复口径限制": "不承诺效果 / 不绝对化 / 不引导站外交易 / 保留人工确认",
            })

    verdict = "正常" if coverage >= COVERAGE_FLOOR else "分类有误/问题过散，需人工复核"
    summary = {
        "账号": account,
        "统计周期": period,
        "原始提问数": len(texts),
        "归一化后独立问法数": len(norm_counter),
        "聚类簇数": len(clusters),
        "合并阈值": MERGE_THRESHOLD,
        "Top10 覆盖率": f"{coverage:.0%}",
        "覆盖率下限": COVERAGE_FLOOR,
        "判定": verdict,
        "说明": "聚类为编辑距离/bigram 的机器判定；语义近似但用词不同的问法由模型按 prompt.txt 二次合并",
    }

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "高频问题聚类.xlsx"),
        {
            "FAQ库Top10": faq_rows or [{"FAQ排名": "（无）"}],
            "问题簇明细": cluster_rows,
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"问题簇明细": {"是否进FAQ库": "contains:Top10"}},
        widths={"FAQ库Top10": {"建议答案要点": 46, "标准问法": 18},
                "问题簇明细": {"代表问题": 18}},
    )
    chart = at.bar_chart(
        os.path.join(outdir, "faq_top10.png"),
        [f"Q{i:02d} {c['norm'][:8]}" for i, c in enumerate(top, 1)][::-1],
        [c["freq"] for c in top][::-1],
        title="Top 10 高频问题（按频次）", horizontal=True,
    )
    js = at.write_json({"summary": summary, "clusters": cluster_rows, "faq": faq_rows,
                        "generated_at": at.stamp(),
                        "note": "机器聚类结果；语义合并由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "faq_cluster.json"))
    return {"files": [xlsx, chart, js], "summary": summary,
            "top_faq": [(r["标准问法"], r["提问频次"]) for r in faq_rows[:5]]}


def main():
    ap = argparse.ArgumentParser(description="高频问题聚类")
    ap.add_argument("--input", help="输入 JSON（account/period/questions）")
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
    print(f"{s['原始提问数']} 条提问 → {s['聚类簇数']} 簇；Top10 覆盖率 {s['Top10 覆盖率']}，判定：{s['判定']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
