# -*- coding: utf-8 -*-
"""
裁判校准：人工评分 vs LLM 裁判，一致率不达标则判定裁判不可信。

为什么必须有这一步：
    LLM 裁判会不稳、存在位置/啰嗦偏差。"裁判分数"若不经人工锚点验证，
    本质上只是把"没有数字"换成了"一个不敢信的数字"。本脚本按 question 对齐
    两种评分，逐维度算一致度；不达标即退出码 1，阻止拿它对外下结论。

放行条件（可用 --min-adjacent / --max-mae 调整）：
    每个维度都要满足 相邻一致率(|差| <= 1) >= 0.80 且 MAE <= 0.50。

用法：
    python evaluation/judge_calibrate.py
    python evaluation/judge_calibrate.py --min-adjacent 0.75 --max-mae 0.6
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
    bias_summary,
    calibration,
    disagreement_details,
    evaluate_gate,
)

HUMAN_PATH = HERE / "judge" / "human_labels.json"
JUDGE_PATH = HERE / "judge" / "judge_scores.json"
REPORT_PATH = HERE / "judge" / "calibration_report.md"


def load_judge_rows(path: Path) -> tuple:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(payload, dict):
        return payload.get("rows") or [], payload

    return payload, {}


def render_report(per_dimension, gate, diagnosis, human_rows, judge_meta, args) -> str:
    lines = [
        "# 裁判校准报告（人工 vs LLM-judge）",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 裁判模型：{judge_meta.get('judge_model', '未知')}",
        f"- 语料条件（note）：{judge_meta.get('note') or '未填写'}",
        f"- 人工样本：{len(human_rows)} 条；放行阈值：相邻一致率 >= {args.min_adjacent}、MAE <= {args.max_mae}",
        "",
        "## 一致度",
        "",
        "| 维度 | 可比条数 | 完全相同 | 相邻一致 | MAE | 二值 kappa |",
        "|---|---|---|---|---|---|",
    ]

    for dimension in DIMENSIONS:

        stats = per_dimension.get(dimension)

        if not stats:
            lines.append(f"| {dimension} | 0 | - | - | - | - |")
            continue

        kappa = stats["kappa_binary"]
        lines.append(
            f"| {dimension} | {stats['n']} | {stats['exact']} | {stats['adjacent']} "
            f"| {stats['mae']} | {'-' if kappa is None else kappa} |"
        )

    lines += ["", f"**结论：{'裁判可信，可用于规模化评测' if gate['passed'] else '裁判未达标，禁止直接采用'}**"]

    if gate["failures"]:
        lines += ["", "未达标项：", ""]
        lines += [f"- {failure}" for failure in gate["failures"]]

    bias = diagnosis.get("bias") or {}
    details = diagnosis.get("details") or []

    lines += [
        "",
        "## 方向性（人工 − 裁判）",
        "",
        "| 维度 | 可比 | 均值Δ | 裁判偏高 | 人工偏高 | 相同 |",
        "|---|---|---|---|---|---|",
    ]

    for dimension in DIMENSIONS:
        row = bias.get(dimension)
        if not row:
            lines.append(f"| {dimension} | 0 | - | - | - | - |")
            continue
        lines.append(
            f"| {dimension} | {row['n']} | {row['mean_delta']:+} | {row['judge_higher']} "
            f"| {row['human_higher']} | {row['equal']} |"
        )

    lines += ["", "> Δ > 0 = 人工给分更高（裁判偏严）；Δ < 0 = 裁判偏宽（给高了）。", ""]

    if details:
        lines += [
            "## 分歧明细（|人工 − 裁判| >= 1）",
            "",
            "| # | 维度 | 问题 | 人工 | 裁判 | Δ |",
            "|---|---|---|---|---|---|",
        ]
        for item in details:
            question = str(item["question"]).replace("|", "/")
            lines.append(
                f"| {item['index']} | {item['dimension']} | {question} | {item['human']} "
                f"| {item['judge']} | {item['delta']:+} |"
            )
        lines.append("")
    else:
        lines += ["## 分歧明细", "", "无（所有维度分差都 < 1）。", ""]

    lines += [
        "",
        "> 相邻一致 = 分差 <= 1 的比例（评分带主观性，比「完全相同」更稳）；",
        "> MAE = 平均绝对误差；二值 kappa = 以通过线二值化后的 Cohen's kappa。",
        "> 未达标时可行的动作：换更大的裁判模型、修裁判 prompt、或缩小人工样本的歧义。",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="裁判一致性校准（人工 vs LLM-judge）")
    parser.add_argument("--human", default=str(HUMAN_PATH), help="人工评分文件")
    parser.add_argument("--judge", default=str(JUDGE_PATH), help="裁判评分文件")
    parser.add_argument("--report", default=str(REPORT_PATH), help="报告输出路径")
    parser.add_argument("--min-adjacent", type=float, default=0.8, help="相邻一致率下限")
    parser.add_argument("--max-mae", type=float, default=0.5, help="MAE 上限")
    parser.add_argument("--threshold", type=int, default=PASS_SCORE, help="二值化通过线")
    args = parser.parse_args()

    human_path = Path(args.human)
    judge_path = Path(args.judge)

    if not human_path.exists():
        print(f"[错误] 缺少人工评分文件：{human_path}（先跑 python evaluation/human_rate.py）")
        return 2

    if not judge_path.exists():
        print(f"[错误] 缺少裁判评分文件：{judge_path}（先跑 python evaluation/judge_eval.py）")
        return 2

    human_rows = json.loads(human_path.read_text(encoding="utf-8"))
    judge_rows, judge_meta = load_judge_rows(judge_path)

    per_dimension = calibration(human_rows, judge_rows, args.threshold)
    gate = evaluate_gate(per_dimension, args.min_adjacent, args.max_mae)

    diagnosis = {
        "bias": {
            dimension: bias_summary(human_rows, judge_rows, dimension)
            for dimension in DIMENSIONS
        },
        "details": [
            detail
            for dimension in DIMENSIONS
            for detail in disagreement_details(human_rows, judge_rows, dimension)
        ],
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(per_dimension, gate, diagnosis, human_rows, judge_meta, args),
        encoding="utf-8",
    )

    print("=" * 72)
    print("裁判一致性（人工 vs LLM-judge）")
    print("=" * 72)
    for dimension in DIMENSIONS:
        stats = per_dimension.get(dimension)
        if not stats:
            print(f"  {dimension:<14} 无可比样本")
            continue
        print(
            f"  {dimension:<14} n={stats['n']:<4} 完全相同={stats['exact']:<7} "
            f"相邻一致={stats['adjacent']:<7} MAE={stats['mae']:<7} kappa={stats['kappa_binary']}"
        )

    print()
    print("方向性（人工 − 裁判；Δ<0 = 裁判偏宽）")
    for dimension in DIMENSIONS:
        row = diagnosis["bias"].get(dimension)
        if not row:
            continue
        print(
            f"  {dimension:<14} 均值Δ={row['mean_delta']:+}  "
            f"裁判偏高={row['judge_higher']}  人工偏高={row['human_higher']}  相同={row['equal']}"
        )

    details = diagnosis["details"]
    if details:
        print()
        print(f"分歧明细（{len(details)} 条，|Δ| >= 1）")
        for item in details:
            print(
                f"  [{item['index']:>2}] {item['dimension']:<12} 人工={item['human']} "
                f"裁判={item['judge']} Δ={item['delta']:+}  {str(item['question'])[:34]}"
            )

    print()
    print(f"报告：{report_path}")

    if gate["passed"]:
        print("[通过] 裁判可信，可用于规模化生成质量评测")
        return 0

    print(f"[失败] 裁判未达标：{'; '.join(gate['failures'])}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
