# -*- coding: utf-8 -*-
"""
人工评分表生成：为裁判校准准备"人打的同一批分"。

LLM 裁判本身也要被验证——没有人工这个锚点，裁判分数只是"一个不敢信的数字"。
本脚本负责生成校准所需的两份东西：

    evaluation/judge/human_sheet.md     人看的可读评分表（含评分锚点、上下文、回答）
    evaluation/judge/human_labels.json  待填的评分骨架（scores 三个维度初始为 null）

取数与 judge_eval.py **相互独立**（各自调一次 /api/chat），这是刻意的：
先看裁判分数再人工打分会被锚定，两种评分必须独立产生，一致率才有意义。

人工只需在 human_labels.json 里把三个维度填成 1~5 的整数（拒答条可跳过），然后：
    python evaluation/judge_calibrate.py

用法：
    python evaluation/human_rate.py --limit 20
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from judge_core import DIMENSIONS, SCORE_MIN, SCORE_MAX, PASS_SCORE, format_contexts  # noqa: E402
from judge_io import (  # noqa: E402
    DEFAULT_BASE_URL,
    fetch_answer,
    fetch_contexts,
    policy_of,
)

DATASET_PATH = HERE / "evaluation_questions.json"
OUT_PATH = HERE / "judge" / "human_labels.json"
SHEET_PATH = HERE / "judge" / "human_sheet.md"
RUBRIC_PATH = HERE / "judge" / "human_rubric.md"
ITEMS_PATH = HERE / "judge" / "human_items.json"


def relevant_sections_of(item) -> list:
    if item.get("relevant_sections"):
        return list(item["relevant_sections"])
    if item.get("relevant_section"):
        return [item["relevant_section"]]
    return []


def collect_item(item, index, args) -> dict:
    """取回回答与上下文（独立于裁判）。失败只记录 error，不中断。"""

    question = item["query"]

    record = {
        "index": index,
        "question": question,
        "expected_source": item.get("relevant_source"),
        "relevant_sections": relevant_sections_of(item),
        "refused": None,
        "answer": "",
        "contexts": [],
        "error": None,
        "scores": {dimension: None for dimension in DIMENSIONS},
        "comment": "",
    }

    try:
        body = fetch_answer(args.base_url, question)

        record["refused"] = bool(body.get("refused"))
        record["answer"] = body.get("answer") or ""

        if not record["refused"]:
            candidate_k, rerank_top_k = policy_of(body, args.candidate_k, args.rerank_top_k)
            record["contexts"] = fetch_contexts(
                args.base_url,
                body.get("retrieval_query") or question,
                candidate_k,
                rerank_top_k,
            )

    except Exception as error:  # noqa: BLE001
        record["error"] = f"{type(error).__name__}: {error}"

    return record


def render_sheet(records, rubric_text, args) -> str:
    lines = [
        "# 人工评分表（裁判校准用）",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 样本：{len(records)} 条",
        f"- 打分方式：在 `evaluation/judge/human_labels.json` 里填 "
        f"`scores.faithfulness / relevancy / correctness`（{SCORE_MIN}~{SCORE_MAX} 的整数，>= {PASS_SCORE} 为通过）",
        "- 独立评分：本表不含任何裁判分数，请勿参考 judge_scores.json，否则一致率失真",
        "",
    ]

    if rubric_text:
        lines += ["## 评分锚点", "", rubric_text.strip(), ""]

    lines += ["## 逐题", ""]

    for record in records:

        lines.append(f"### [{record['index']}] {record['question']}")
        lines.append("")

        expected = record.get("expected_source") or "（库外题，正确行为应为拒答）"
        lines.append(f"- 金标来源：{expected}")
        if record.get("relevant_sections"):
            lines.append(f"- 金标章节：{', '.join(record['relevant_sections'])}")

        if record.get("error"):
            lines += ["", f"> 取数失败：{record['error']}", ""]
            continue

        if record.get("refused"):
            lines += ["", "> 应用选择了拒答（库外题时属正确行为；库内题若被拒答，"
                          "问题在阈值层，不由本表评判）", ""]
            continue

        lines += ["", "**上下文片段**", "", "```", format_contexts(record["contexts"]), "```", ""]
        lines += ["**回答**", "", "```", record["answer"], "```", ""]
        lines += [
            "评分：faithfulness = ?　relevancy = ?　correctness = ?",
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="人工评分表生成（裁判校准）")
    parser.add_argument("--limit", type=int, default=20, help="取前 N 条（默认 20）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="应用地址")
    parser.add_argument("--dataset", default=str(DATASET_PATH), help="评测集路径")
    parser.add_argument("--out", default=str(OUT_PATH), help="标签骨架输出路径")
    parser.add_argument("--sheet", default=str(SHEET_PATH), help="评分表输出路径")
    parser.add_argument("--items", default=str(ITEMS_PATH), help="机器可读材料输出路径（供 human_score.py 用）")
    parser.add_argument("--rubric", default=str(RUBRIC_PATH), help="评分锚点文件路径")
    parser.add_argument("--candidate-k", type=int, default=5, help="复现检索时的候选数")
    parser.add_argument("--rerank-top-k", type=int, default=3, help="复现检索时的精排数")
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    dataset = dataset[: args.limit]

    print(f"== 人工评分表：{len(dataset)} 条 ==", flush=True)

    records = []

    for index, item in enumerate(dataset, start=1):
        records.append(collect_item(item, index, args))
        print(f"[{index:02d}/{len(dataset)}] {item['query']}", flush=True)

    labels = [
        {
            "index": record["index"],
            "question": record["question"],
            "expected_source": record["expected_source"],
            "refused": record["refused"],
            "scores": record["scores"],
            "comment": record["comment"],
        }
        for record in records
    ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rubric_text = ""
    rubric_path = Path(args.rubric)
    if rubric_path.exists():
        rubric_text = rubric_path.read_text(encoding="utf-8")

    sheet_path = Path(args.sheet)
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.write_text(render_sheet(records, rubric_text, args), encoding="utf-8")

    items_path = Path(args.items)
    items_path.parent.mkdir(parents=True, exist_ok=True)
    items_path.write_text(
        json.dumps(
            [
                {
                    "index": record["index"],
                    "question": record["question"],
                    "expected_source": record["expected_source"],
                    "relevant_sections": record["relevant_sections"],
                    "refused": record["refused"],
                    "answer": record["answer"],
                    "contexts": record["contexts"],
                    "error": record["error"],
                }
                for record in records
            ],
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"评分表（人看）：{sheet_path}")
    print(f"评分材料（机器读）：{items_path}")
    print(f"标签骨架（待填）：{out_path}")
    print("下一步：python -X utf8 evaluation/human_score.py 交互式打分（或手改本文件），"
          "再跑 python evaluation/judge_calibrate.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
