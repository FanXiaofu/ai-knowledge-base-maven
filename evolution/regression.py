# -*- coding: utf-8 -*-
"""
自进化闭环第 4 步：回归门禁。

改语料、改切分、改 prompt、换策略文件之后，检索指标有没有退？靠人眼看报告不可靠，
所以做成脚本 + 非零退出码，可以挂到提交前检查或 CI 上。

    python evolution/regression.py                     # 用当前策略跑基线对比
    python evolution/regression.py --update-baseline   # 把当前指标固化为新基线
    python evolution/regression.py --limit 20          # 快速门禁（只跑前 20 条）

判定规则：
- 检索指标（文档 R@1 / 文档 R@3 / 章节 R@1）低于基线超过 --tolerance（默认 0.01）→ 失败；
- 拒答 FAR 高于基线超过同一容差 → 失败（放进了不该答的问题）；
- 其余指标（拒答 P/R/F1、耗时）只报告，不作为门禁。

评测口径与 evaluation/evaluate.py 完全一致（同一套函数），否则门禁数字与历史报告对不上。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evaluation"))

from evaluate import (  # noqa: E402
    BASE_URL,
    aggregate_metrics,
    calculate_section_metrics,
    calculate_source_metrics,
    evaluate_threshold,
    get_relevant_sections,
    get_result_list,
    load_dataset,
)

BASELINE_PATH = ROOT / "evaluation" / "baseline_metrics.json"
EVOLVED_CASES = ROOT / "evaluation" / "evolved_cases.json"
POLICY_PATH = ROOT / "evaluation" / "selected_policy.json"
REPORT_PATH = ROOT / "evaluation" / "regression_report.md"

GATED_ASC = ["source_r1", "source_r3", "section_r1"]  # 越高越好，低于基线即回退
GATED_DESC = ["refusal_far"]                          # 越低越好，高于基线即回退

LABELS = {
    "source_r1": "文档 R@1",
    "source_r3": "文档 R@3",
    "section_r1": "章节 R@1",
    "refusal_precision": "拒答 Precision",
    "refusal_f1": "拒答 F1",
    "refusal_far": "拒答 FAR（库外误答率）",
}


def load_policy() -> dict:
    if POLICY_PATH.exists():
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    return {}


def rerank(query: str, candidate_k: int, rerank_top_k: int) -> list:
    response = requests.get(
        f"{BASE_URL}/rerank-test",
        params={"query": query, "candidateK": candidate_k, "rerankTopK": rerank_top_k},
        timeout=180,
    )
    response.raise_for_status()
    return get_result_list(response)


def evaluate(dataset: list, candidate_k: int, rerank_top_k: int, threshold: float) -> dict:
    records = []

    for item in dataset:
        expected_source = item.get("relevant_source")
        relevant_sections = get_relevant_sections(item)

        try:
            results = rerank(item["query"], candidate_k, rerank_top_k)
            error = None
        except Exception as exc:
            results = []
            error = f"{type(exc).__name__}: {exc}"

        records.append({
            "query": item["query"],
            "expected_source": expected_source,
            "relevant_sections": list(relevant_sections),
            "results": results,
            "source": calculate_source_metrics(results, expected_source),
            "section": calculate_section_metrics(results, relevant_sections),
            "error": error,
        })

    source = aggregate_metrics(records, "source") or {}
    section = aggregate_metrics(records, "section") or {}
    refusal = evaluate_threshold(records, threshold)

    return {
        "n": len(records),
        "errors": sum(1 for record in records if record["error"]),
        "source_r1": round(source.get("recall@1", 0.0), 4),
        "source_r3": round(source.get("recall@3", 0.0), 4),
        "section_r1": round(section.get("recall@1", 0.0), 4),
        "refusal_precision": refusal["precision"],
        "refusal_f1": refusal["f1"],
        "refusal_far": refusal["far"],
        "refusal_frr": refusal["frr"],
        "threshold": threshold,
    }


def compare(baseline: dict, current: dict, tolerance: float) -> tuple:
    """返回 (结果行, 是否有回退)。"""
    rows, regressed = [], []

    for key in GATED_ASC:
        base, now = baseline.get(key), current.get(key)
        if base is None or now is None:
            continue
        delta = round(now - base, 4)
        failed = delta < -tolerance
        if failed:
            regressed.append(key)
        rows.append({"key": key, "baseline": base, "current": now, "delta": delta,
                     "gated": True, "failed": failed})

    for key in GATED_DESC:
        base, now = baseline.get(key), current.get(key)
        if base is None or now is None:
            continue
        delta = round(now - base, 4)
        failed = delta > tolerance
        if failed:
            regressed.append(key)
        rows.append({"key": key, "baseline": base, "current": now, "delta": delta,
                     "gated": True, "failed": failed})

    for key in ("refusal_precision", "refusal_f1"):
        base, now = baseline.get(key), current.get(key)
        if base is None or now is None:
            continue
        rows.append({"key": key, "baseline": base, "current": now,
                     "delta": round(now - base, 4), "gated": False, "failed": False})

    return rows, regressed


def render(rows: list, regressed: list, baseline: dict, current: dict, policy: dict,
           evolved: dict | None, tolerance: float) -> str:
    lines = [
        "# 回归门禁报告",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 容差：{tolerance}（绝对差超过容差判为回退）",
        f"- 策略：top_k={current['candidate_k']} rerank_top_k={current['rerank_top_k']} "
        f"阈值={current['threshold']}"
        f"（来源：{policy.get('source', '内置默认值')}）",
        f"- 数据：基线 {baseline.get('dataset', {}).get('evaluated', '-')} 条 / "
        f"本次 {current['n']} 条（失败 {current['errors']} 题）",
        "",
        "| 指标 | 基线 | 本次 | Δ | 是否门禁 | 判定 |",
        "|---|---|---|---|---|---|",
    ]

    for row in rows:
        verdict = "回退" if row["failed"] else "通过"
        lines.append(
            f"| {LABELS.get(row['key'], row['key'])} | {row['baseline']} | {row['current']} "
            f"| {row['delta']:+} | {'是' if row['gated'] else '否'} | {verdict} |"
        )

    lines += [
        "",
        f"**结论：{'存在回退（' + '、'.join(LABELS.get(k, k) for k in regressed) + '）' if regressed else '无回退'}**",
    ]

    if evolved:
        lines += [
            "",
            "## 自进化用例（badcase 转来的新增集，无历史基线，只报水平）",
            "",
            f"- 用例数：{evolved['n']}（失败 {evolved['errors']} 题）",
            f"- 文档 R@1={evolved['source_r1']} ｜ 文档 R@3={evolved['source_r3']} "
            f"｜ 章节 R@1={evolved['section_r1']}",
            "",
            "> 这批用例来自线上负反馈，代表真实失败分布；水平低于基础集是正常的，",
            "> 关键是每次迭代它是否在上升。",
        ]

    lines += [
        "",
        "> 门禁只卡检索与拒答的硬指标；拒答 P/R/F1 与耗时仅报告，避免把噪声当回退。",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="评测回归门禁")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全量）")
    parser.add_argument("--tolerance", type=float, default=0.01, help="允许的绝对回退幅度")
    parser.add_argument("--candidate-k", type=int, help="覆盖策略里的候选数")
    parser.add_argument("--rerank-top-k", type=int, help="覆盖策略里的精排数")
    parser.add_argument("--threshold", type=float, help="覆盖策略里的拒答阈值")
    parser.add_argument("--update-baseline", action="store_true", help="把当前指标固化为新基线")
    parser.add_argument("--skip-evolved", action="store_true", help="不跑自进化用例集")
    args = parser.parse_args()

    policy = load_policy()

    candidate_k = args.candidate_k or policy.get("top_k", 5)
    rerank_top_k = args.rerank_top_k or policy.get("rerank_top_k", 3)
    threshold = args.threshold if args.threshold is not None else policy.get("relevance_threshold", 0.60)

    dataset = load_dataset()
    if args.limit:
        dataset = dataset[: args.limit]

    print(
        f"== 回归评测：{len(dataset)} 条 | top_k={candidate_k} rerank_top_k={rerank_top_k} "
        f"阈值={threshold} | 策略来源={policy.get('source', '内置默认值')} ==",
        flush=True,
    )

    try:
        current = evaluate(dataset, candidate_k, rerank_top_k, threshold)
    except requests.exceptions.ConnectionError:
        print("[错误] 无法连接应用（http://localhost:8080），请先启动服务", flush=True)
        return 2

    current.update({
        "candidate_k": candidate_k,
        "rerank_top_k": rerank_top_k,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    })

    evolved_metrics = None
    if not args.skip_evolved and EVOLVED_CASES.exists():
        evolved_cases = json.loads(EVOLVED_CASES.read_text(encoding="utf-8"))
        if evolved_cases:
            print(f"-- 自进化用例集 {len(evolved_cases)} 条 ...", flush=True)
            evolved_metrics = evaluate(evolved_cases, candidate_k, rerank_top_k, threshold)

    if args.update_baseline:
        payload = dict(current)
        payload["dataset"] = {"path": "evaluation/evaluation_questions.json", "evaluated": len(dataset)}
        BASELINE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"已更新基线：{BASELINE_PATH}")
        return 0

    if not BASELINE_PATH.exists():
        print("[错误] 缺少基线文件，请先运行 python evolution/regression.py --update-baseline")
        return 2

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    rows, regressed = compare(baseline, current, args.tolerance)

    REPORT_PATH.write_text(
        render(rows, regressed, baseline, current, policy, evolved_metrics, args.tolerance),
        encoding="utf-8",
    )

    print()
    for row in rows:
        flag = "回退" if row["failed"] else "通过"
        print(f"  {LABELS.get(row['key'], row['key']):<24} 基线={row['baseline']:<8} "
              f"本次={row['current']:<8} Δ={row['delta']:+} [{flag}]")
    if evolved_metrics:
        print(f"  自进化用例集：n={evolved_metrics['n']} 文档 R@1={evolved_metrics['source_r1']} "
              f"章节 R@1={evolved_metrics['section_r1']}")

    print(f"\n报告：{REPORT_PATH}")

    if regressed:
        print(f"[失败] 存在回退：{', '.join(regressed)}")
        return 1

    print("[通过] 无回退")
    return 0


if __name__ == "__main__":
    sys.exit(main())
