# -*- coding: utf-8 -*-
"""
高频问题转选题流程 —— 端到端编排脚本。

编排逻辑（与 SKILL.md 的 DAG 一致）：
  提问类评论流 → [faq-cluster] 相似度聚类（≥0.60 归同簇）+ 频次排序 Top10
              → [topic-knowledge-base] 逐簇生成选题条目：
                 查重（与既有选题库相似度 ≥ 0.60 判重复）→ 优先级（频次 ≥5 高 / 3-4 中 / <3 低）
              → 选题库新增条目清单（人工确认后才真正入库）

失败处理：
  - 上游 faq-cluster 退出码 != 0 或产物缺失 → 中止并打印错误
  - 提问类评论为空 → 输出「本周无新增选题」清单并正常退出
  - 全部条目与既有库重复 → 正常退出，清单标注「无新增，跳过入库」

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(FLOW_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py", file=sys.stderr)
    sys.exit(2)

FAQ_SCRIPT = os.path.join(REPO, "skills", "faq-cluster", "scripts", "faq_cluster.py")
DUP_THRESHOLD = 0.60

# 选题角度映射：簇关键词 → 选题建议（与 faq-cluster 的 ANSWER_MAP 呼应但服务于选题）
TOPIC_ANGLE = [
    (r"链接|在哪买|哪里买|求购|怎么买", "「WHERE 买指南」：全渠道购买攻略 + 防坑清单"),
    (r"多少钱|价格|贵不贵|值不值", "「值不值」横评：同价位 3 款对比 + 适合人群"),
    (r"色号|显白|黄皮|白皮", "「全肤色试色」合集：按肤色索引的色号数据库"),
    (r"油皮|干皮|敏感肌|痘痘|肤质", "「按肤质怎么选」：肤质自测 + 分肤质推荐"),
    (r"教程|怎么画|步骤|新手|手法", "「新手 0 基础」分步教程（≤5 步 + 常见翻车点）"),
    (r"什么时候|更新|下一期", "「更新预告 + 往期索引」：置顶汇总帖，降低重复提问"),
    (r"平替|平价|学生党|替代", "「平替实验室」：大牌 vs 平替盲测对比"),
    (r"正品|真假|鉴别|保质期", "「正品鉴别指南」：渠道对比 + 官方验证路径"),
    (r"测评|好不好用|推荐", "「评论区点名测评」：回应高频求测评单品"),
]

DEMO_INPUT = {
    "account": "@小鹿的好物日记",
    "period": "2026-09-23 ~ 2026-09-29",
    "existing_topics": ["新手化妆顺序教程", "平价粉底液合集"],
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


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, re.sub(r"[^\w\u4e00-\u9fff]+", "", a.lower()),
                           re.sub(r"[^\w\u4e00-\u9fff]+", "", b.lower())).ratio()


def topic_angle(rep: str) -> str:
    for pat, angle in TOPIC_ANGLE:
        if re.search(pat, rep):
            return angle
    return "「评论区问答」合集：集中回应本周高频问题"


def priority(freq: int) -> str:
    if freq >= 5:
        return "高"
    if freq >= 3:
        return "中"
    return "低"


def main():
    ap = argparse.ArgumentParser(description="高频问题转选题流程")
    ap.add_argument("--input", help="流程输入 JSON（account/period/questions/existing_topics）")
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

    # 步骤 1：上游聚类
    r = subprocess.run(
        [sys.executable, FAQ_SCRIPT, "--input", payload_path, "--outdir", a.outdir],
        cwd=FLOW_DIR, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"[失败处理] 上游技能 faq-cluster 退出码 {r.returncode}，流程中止。", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)
        sys.exit(1)
    faq_js = os.path.join(a.outdir, "faq_cluster.json")
    if not os.path.exists(faq_js):
        print(f"[失败处理] 上游产物 {faq_js} 缺失，流程中止。", file=sys.stderr)
        sys.exit(1)
    faq = at.read_json(faq_js)

    # 步骤 2：查重 + 生成选题条目（topic-knowledge-base 环节）
    existing = [str(t) for t in payload.get("existing_topics", [])]
    rows = []
    for f in faq.get("faq", []):
        rep, freq = f["标准问法"], int(f["提问频次"])
        dup = next((t for t in existing if sim(rep, t) >= DUP_THRESHOLD), None)
        rows.append({
            "选题ID": f"T{len(rows) + 1:03d}",
            "来源问题簇": rep,
            "提问频次": freq,
            "优先级": priority(freq),
            "选题建议": topic_angle(rep),
            "答案要点(可复用FAQ)": f["建议答案要点"],
            "查重结果": f"与既有选题「{dup}」重复" if dup else "新增",
            "状态": "待人工确认",
        })

    n_new = sum(1 for x in rows if x["查重结果"] == "新增")
    summary = {
        "账号": payload.get("account", "未提供"),
        "统计周期": payload.get("period", ""),
        "上游聚类簇数": faq["summary"]["聚类簇数"],
        "Top10 覆盖率": faq["summary"]["Top10 覆盖率"],
        "候选选题数": len(rows),
        "查重后新增": n_new,
        "与既有库重复": len(rows) - n_new,
        "高优先级选题": sum(1 for x in rows if x["优先级"] == "高"),
        "入库规则": "全部条目为「待人工确认」；人工勾选后才写入正式选题库（合规要求）",
        "说明": "选题热度=提问频次；频次 ≥5 为高优。语义查重（用词不同的近似选题）由模型按 prompt.txt 复核",
    }

    xlsx = at.write_excel(
        os.path.join(a.outdir, "选题库新增条目.xlsx"),
        {
            "候选选题": rows or [{"选题ID": "（本周无候选选题）"}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"候选选题": {"查重结果": "contains:重复", "优先级": "contains:高"}},
        widths={"候选选题": {"选题建议": 40, "答案要点(可复用FAQ)": 40, "来源问题簇": 14}},
    )

    result = {
        "flow": "faq-to-topic-flow",
        "steps": [
            {"step": 1, "skill": "faq-cluster", "status": "ok", "output": faq_js},
            {"step": 2, "skill": "topic-knowledge-base（查重+条目生成）", "status": "ok",
             "output": xlsx},
        ],
        "summary": summary,
        "files": [xlsx, faq_js],
        "generated_at": at.stamp(),
    }
    at.write_json(result, os.path.join(a.outdir, "topic_flow_result.json"))
    print(f"候选选题 {len(rows)} 条，查重后新增 {n_new} 条（待人工确认）")
    for f in result["files"]:
        print(" 产物:", f)
    at.emit(result)


if __name__ == "__main__":
    main()
