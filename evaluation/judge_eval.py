# -*- coding: utf-8 -*-
"""
生成质量评测（LLM-as-judge，本地裁判）。

补的是此前完全空白的一层：检索（文档/章节 R@1/R@3）与拒答（阈值 P/R/F1/FAR）
都测了，但**回答本身的生成质量没有任何自动指标**。

每条问题的流程：
    1. 调 /api/chat 拿真实回答（与线上链路一致，不带 sessionId 即单轮）
    2. 若拒答 → 跳过裁判，标记 refused（拒答的恰当性属于拒答层，不在此测）
    3. 否则用同一 query 与同一 (candidateK, rerankTopK) 复现检索，取回上下文
    4. 本地 Ollama 裁判打 faithfulness / relevancy / correctness（1~5）
    5. 汇总 + 落盘 judge_scores.json + 生成 markdown 报告

口径纪律（与 evaluate.py 一致）：
    报告与落盘都必须带 --note 语料条件，不同语料的数字不可比、不可混用。

成本提示：
    每条要 2 次本地 LLM 调用（生成 + 裁判），且两次用不同模型会触发 Ollama
    换模型加载，**这是分钟级评测，不是检索评测那种秒级**。建议先 --limit 20。

用法：
    python evaluation/judge_eval.py --limit 20 --note "172 篇：27 自建 + 142 官方 + 3 测试"
    python evaluation/judge_eval.py --judge-model qwen2.5:7b-instruct     # 全量（较慢）
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from judge_core import (  # noqa: E402
    DIMENSIONS,
    PASS_SCORE,
    build_judge_prompt,
    expected_points_of,
    parse_judge_output,
    summarize_scores,
)
from judge_io import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_OLLAMA_URL,
    fetch_answer,
    fetch_contexts,
    ollama_judge,
    policy_of,
)

DATASET_PATH = HERE / "evaluation_questions.json"
OUT_PATH = HERE / "judge" / "judge_scores.json"
REPORT_PATH = HERE / "judge" / "judge_report.md"


def relevant_sections_of(item) -> list:
    if item.get("relevant_sections"):
        return list(item["relevant_sections"])
    if item.get("relevant_section"):
        return [item["relevant_section"]]
    return []


def evaluate_item(item, index, args) -> dict:
    """单条：取回答 →（必要时）取上下文 → 裁判打分。任何异常都记录到 error，不中断整批。"""

    question = item["query"]
    expected_source = item.get("relevant_source")

    row = {
        "index": index,
        "question": question,
        "expected_source": expected_source,
        "relevant_sections": relevant_sections_of(item),
        "refused": None,
        "answer": "",
        "retrieval_query": None,
        "top1_score": None,
        "threshold": None,
        "contexts": [],
        "context_hit": None,
        "judge": None,
        "error": None,
    }

    try:
        body = fetch_answer(args.base_url, question)

        row["refused"] = bool(body.get("refused"))
        row["answer"] = body.get("answer") or ""
        row["retrieval_query"] = body.get("retrieval_query")
        row["top1_score"] = body.get("top1_score")
        row["threshold"] = body.get("threshold")

        if row["refused"]:
            return row

        candidate_k, rerank_top_k = policy_of(body, args.candidate_k, args.rerank_top_k)
        query = row["retrieval_query"] or question

        contexts = fetch_contexts(
            args.base_url, query, candidate_k, rerank_top_k
        )
        row["contexts"] = contexts

        if expected_source is not None:
            row["context_hit"] = expected_source in [
                context.get("source") for context in contexts
            ]

        prompt = build_judge_prompt(
            question, contexts, row["answer"], expected_points_of(item)
        )
        raw = ollama_judge(
            prompt, model=args.judge_model, ollama_url=args.ollama_url
        )
        row["judge"] = parse_judge_output(raw)

    except Exception as error:  # noqa: BLE001 —— 单题失败不影响整批，但必须留痕
        row["error"] = f"{type(error).__name__}: {error}"

    return row


def render_report(rows, summary, args) -> str:
    judged = [row for row in rows if row.get("judge")]
    refused = [row for row in rows if row.get("refused")]
    errored = [row for row in rows if row.get("error")]

    lines = [
        "# 生成质量评测报告（LLM-as-judge）",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 语料条件（note）：{args.note or '未填写（数字不可对外引用）'}",
        f"- 裁判模型：{args.judge_model}（生成模型为应用侧配置，通常 qwen3:4b——异族裁判，降低自偏好）",
        f"- 样本：{len(rows)} 条（已评判 {len(judged)} 条，拒答 {len(refused)} 条，失败 {len(errored)} 条）",
        f"- 计分：1~5，>= {PASS_SCORE} 视为通过",
        "",
        "## 汇总",
        "",
        "| 维度 | n | 均值 | 通过率 | 分布(1/2/3/4/5) |",
        "|---|---|---|---|---|",
    ]

    for dimension in DIMENSIONS:

        stats = summary.get(dimension)

        if not stats:
            lines.append(f"| {dimension} | 0 | - | - | - |")
            continue

        distribution = stats["distribution"]
        spread = "/".join(str(distribution[str(score)]) for score in range(1, 6))

        lines.append(
            f"| {dimension} | {stats['n']} | {stats['mean']} "
            f"| {stats['pass_rate']} | {spread} |"
        )

    context_hits = [row for row in judged if row.get("context_hit") is not None]
    if context_hits:
        hit_rate = sum(1 for row in context_hits if row["context_hit"]) / len(context_hits)
        lines += [
            "",
            "## 检索代理指标（用于区分「生成不行」还是「没给对上下文」）",
            "",
            f"- 已评判样本中，金标文档进入上下文的比例（context_hit）："
            f"{round(hit_rate, 4)}（{len(context_hits)} 条）",
            "- 若某条 correctness 低但 context_hit=True，问题在生成层；"
            "若 context_hit=False，则应先修召回/精排，不该算到生成头上。",
        ]

    lines += [
        "",
        "## 逐题明细",
        "",
        "| # | 问题 | 拒答 | 上下文命中 | faithfulness | relevancy | correctness | 裁判理由 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for row in rows:

        judge = row.get("judge") or {}

        def cell(dimension):
            return str(judge.get(dimension)) if judge.get(dimension) is not None else "-"

        refused_cell = "是" if row.get("refused") else ("-" if row.get("refused") is None else "否")
        hit_cell = "-" if row.get("context_hit") is None else ("✓" if row["context_hit"] else "✗")

        reason = (judge.get("reason") or "").replace("|", "/")
        if row.get("error"):
            reason = f"ERROR: {row['error']}".replace("|", "/")

        lines.append(
            f"| {row['index']} | {row['question']} | {refused_cell} | {hit_cell} "
            f"| {cell('faithfulness')} | {cell('relevancy')} | {cell('correctness')} | {reason} |"
        )

    lines += [
        "",
        "> 裁判分数在用于对外结论之前，必须先跑 `python evaluation/judge_calibrate.py`"
        " 与人工评分比对一致率；未校准的裁判分数只能内部参考。",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成质量评测（LLM-as-judge）")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全量）")
    parser.add_argument("--note", default="", help="语料条件说明（写进报告，避免数字脱离上下文）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="应用地址")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama 地址")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="裁判模型")
    parser.add_argument("--dataset", default=str(DATASET_PATH), help="评测集路径")
    parser.add_argument("--out", default=str(OUT_PATH), help="逐题结果输出路径")
    parser.add_argument("--report", default=str(REPORT_PATH), help="报告输出路径")
    parser.add_argument("--candidate-k", type=int, default=5, help="复现检索时的候选数（回落到策略）")
    parser.add_argument("--rerank-top-k", type=int, default=3, help="复现检索时的精排数（回落到策略）")
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if args.limit:
        dataset = dataset[: args.limit]

    print(
        f"== 生成质量评测：{len(dataset)} 条 | 裁判={args.judge_model} | "
        f"note={args.note or '未填写'} ==",
        flush=True,
    )

    rows = []

    for index, item in enumerate(dataset, start=1):

        row = evaluate_item(item, index, args)
        rows.append(row)

        status = "拒答" if row.get("refused") else (
            "ERROR" if row.get("error") else "已评判"
        )
        print(f"[{index:02d}/{len(dataset)}] {status:<5} {row['question']}", flush=True)

    summary = summarize_scores(rows)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({
            "note": args.note,
            "judge_model": args.judge_model,
            "evaluated_at": datetime.now().isoformat(timespec="seconds"),
            "summary": summary,
            "rows": rows,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(rows, summary, args), encoding="utf-8")

    print()
    print("=" * 72)
    print("汇总（1~5，>= 4 通过）")
    print("=" * 72)
    for dimension in DIMENSIONS:
        stats = summary.get(dimension)
        if stats:
            print(f"  {dimension:<14} n={stats['n']:<4} 均值={stats['mean']:<7} 通过率={stats['pass_rate']}")
        else:
            print(f"  {dimension:<14} 无样本")

    print()
    print(f"逐题结果：{out_path}")
    print(f"报告：{report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
