# -*- coding: utf-8 -*-
"""
自进化闭环第 3 步：在标注验证集上扫参选优 → 写检索策略文件。

    evaluation/evaluation_questions.json
                │
                ├─ 遍历候选配置（候选数 × 精排数）
                │      └─ 每题调用 /api/knowledge/rerank-test?candidateK=&rerankTopK=
                ├─ 每个配置算 文档 R@1/R@3、章节 R@1，并对精排分数做拒答阈值扫描
                ▼
        evaluation/selected_policy.json ──► 应用启动时读取（RetrievalPolicyService）

阈值与候选数不再是写死的常量，而是评测集选出来的；选优规则与 target 都写在策略文件里，
可追溯到"哪个配置、在多少条数据上、按什么目标"得出的。

    python evolution/auto_tune.py --limit 40 --write
    python evolution/auto_tune.py --candidate-ks 5,10 --rerank-top-ks 3,5 --write
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evaluation"))

from evaluate import (  # noqa: E402  复用评测脚本的口径，避免两套算法
    BASE_URL,
    aggregate_metrics,
    calculate_section_metrics,
    calculate_source_metrics,
    evaluate_threshold,
    get_relevant_sections,
    get_result_list,
    load_dataset,
)

POLICY_PATH = ROOT / "evaluation" / "selected_policy.json"
DATASET_PATH = ROOT / "evaluation" / "evaluation_questions.json"

DEFAULT_OBJECTIVE = ["source_r1", "source_r3", "section_r1", "refusal_f1"]


def search_reranked(query: str, candidate_k: int, rerank_top_k: int) -> list:
    response = requests.get(
        f"{BASE_URL}/rerank-test",
        params={"query": query, "candidateK": candidate_k, "rerankTopK": rerank_top_k},
        timeout=180,
    )
    response.raise_for_status()
    return get_result_list(response)


def evaluate_config(dataset: list, candidate_k: int, rerank_top_k: int, thresholds: list) -> dict:
    """在一个 (候选数, 精排数) 配置下跑完整验证集，返回记录、指标与阈值扫描。"""
    records = []

    for item in dataset:
        expected_source = item.get("relevant_source")
        relevant_sections = get_relevant_sections(item)

        try:
            results = search_reranked(item["query"], candidate_k, rerank_top_k)
            error = None
        except Exception as exc:  # 单题失败不影响整体扫参，但要记录
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

    sweep = [evaluate_threshold(records, threshold) for threshold in thresholds]

    return {
        "records": records,
        "source": aggregate_metrics(records, "source"),
        "section": aggregate_metrics(records, "section"),
        "sweep": sweep,
        "errors": sum(1 for record in records if record["error"]),
    }


def best_refusal(sweep: list) -> dict:
    """阈值选优规则与 evaluation/evaluate.py 一致：F1 → FAR → FRR。"""
    return max(sweep, key=lambda row: (row["f1"], -row["far"], -row["frr"]))


def config_row(candidate_k: int, rerank_top_k: int, result: dict) -> dict:
    refusal = best_refusal(result["sweep"])
    return {
        "top_k": candidate_k,
        "rerank_top_k": rerank_top_k,
        "source_r1": round(result["source"]["recall@1"], 4) if result["source"] else None,
        "source_r3": round(result["source"]["recall@3"], 4) if result["source"] else None,
        "section_r1": round(result["section"]["recall@1"], 4) if result["section"] else None,
        "refusal_f1": refusal["f1"],
        "refusal_far": refusal["far"],
        "refusal_threshold": refusal["threshold"],
        "evaluated": len(result["records"]),
        "errors": result["errors"],
    }


def select_best(rows: list, objective: list) -> dict:
    """按目标指标字典序选优（默认：文档 R@1 → 文档 R@3 → 章节 R@1 → 拒答 F1）。"""
    def key(row):
        return tuple(row.get(name) if row.get(name) is not None else -1 for name in objective)

    return max(rows, key=key)


def build_policy(best: dict, rows: list, dataset_info: dict, objective: list) -> dict:
    return {
        "policy_version": 1,
        "selected_at": datetime.now().isoformat(timespec="seconds"),
        "source": "evolution/auto_tune.py",
        "objective": objective,
        "dataset": dataset_info,
        "method": "hybrid+rerank",
        "top_k": best["top_k"],
        "rerank_top_k": best["rerank_top_k"],
        "relevance_threshold": best["refusal_threshold"],
        "evidence": {
            "source_r1": best["source_r1"],
            "source_r3": best["source_r3"],
            "section_r1": best["section_r1"],
            "refusal": {
                "f1": best["refusal_f1"],
                "far": best["refusal_far"],
                "threshold": best["refusal_threshold"],
            },
        },
        "candidates_evaluated": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检索策略扫参选优")
    parser.add_argument("--limit", type=int, default=0, help="验证集取前 N 条（0=全量）")
    parser.add_argument("--candidate-ks", default="5,10", help="候选数候选值，逗号分隔")
    parser.add_argument("--rerank-top-ks", default="3,5", help="精排数候选值，逗号分隔")
    parser.add_argument(
        "--thresholds",
        default="0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75",
        help="拒答阈值扫描点，逗号分隔",
    )
    parser.add_argument("--objective", default=",".join(DEFAULT_OBJECTIVE),
                        help="选优目标（按优先级排序）")
    parser.add_argument("--policy-path", default=str(POLICY_PATH), help="策略文件输出路径")
    parser.add_argument("--write", action="store_true", help="写入策略文件（默认只打印）")
    args = parser.parse_args()

    dataset = load_dataset()
    if args.limit:
        dataset = dataset[: args.limit]

    candidate_ks = [int(value) for value in args.candidate_ks.split(",") if value.strip()]
    rerank_top_ks = [int(value) for value in args.rerank_top_ks.split(",") if value.strip()]
    thresholds = [float(value) for value in args.thresholds.split(",") if value.strip()]
    objective = [value.strip() for value in args.objective.split(",") if value.strip()]

    print(f"== 扫参：{len(dataset)} 条验证集 × {len(candidate_ks)}×{len(rerank_top_ks)} 配置 "
          f"× {len(thresholds)} 阈值 ==", flush=True)

    rows = []
    for candidate_k in candidate_ks:
        for rerank_top_k in rerank_top_ks:
            print(f"-- 配置 candidateK={candidate_k} rerankTopK={rerank_top_k} ...", flush=True)
            result = evaluate_config(dataset, candidate_k, rerank_top_k, thresholds)
            row = config_row(candidate_k, rerank_top_k, result)
            rows.append(row)
            print(
                f"   文档 R@1={row['source_r1']} R@3={row['source_r3']} "
                f"章节 R@1={row['section_r1']} | 拒答 F1={row['refusal_f1']} "
                f"阈值={row['refusal_threshold']} | 失败 {row['errors']} 题",
                flush=True,
            )

    best = select_best(rows, objective)

    print("\n== 结果汇总 ==")
    header = f"{'top_k':>6}{'rerank':>8}{'文档R@1':>10}{'文档R@3':>10}{'章节R@1':>10}{'拒答F1':>10}{'阈值':>8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        mark = " ←选中" if row is best else ""
        print(
            f"{row['top_k']:>6}{row['rerank_top_k']:>8}{row['source_r1']:>10}"
            f"{row['source_r3']:>10}{row['section_r1']:>10}{row['refusal_f1']:>10}"
            f"{row['refusal_threshold']:>8}{mark}"
        )

    policy = build_policy(
        best,
        rows,
        {
            "path": str(DATASET_PATH.relative_to(ROOT)).replace("\\", "/"),
            "evaluated": len(dataset),
            "total": len(load_dataset()),
            "in_kb": sum(1 for item in dataset if item.get("relevant_source")),
        },
        objective,
    )

    print(f"\n选优目标：{' > '.join(objective)}")
    print(f"选中策略：top_k={best['top_k']} rerank_top_k={best['rerank_top_k']} "
          f"阈值={best['refusal_threshold']}")

    if args.write:
        path = Path(args.policy_path)
        path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n已写入策略文件：{path}")
        print("生效方式：重启应用，或调用 POST /api/chat/policy/reload")
    else:
        print("\n（dry-run：加 --write 才会写入策略文件）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
