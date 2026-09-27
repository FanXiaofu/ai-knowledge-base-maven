import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

import requests


BASE_URL = "http://localhost:8080/api/knowledge"

DATASET_PATH = Path(__file__).parent / "evaluation_questions.json"

RUN_LOG_PATH = Path(__file__).parent / "evaluation_runs.jsonl"

TOP_K = 5
RERANK_TOP_K = 3


def load_dataset():
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_metadata(result):
    """
    兼容 Spring Boot 返回的 Document JSON。
    """
    return result.get("metadata", {})


def get_source(result):
    metadata = get_metadata(result)

    return (
        metadata.get("source")
        or metadata.get("file_name")
        or metadata.get("filename")
    )


def get_section(result):
    metadata = get_metadata(result)

    return metadata.get("section")


def get_relevant_sections(item):
    """
    获取 Gold Section。

    支持：
    relevant_section:
        "IoC"

    relevant_sections:
        ["BeanFactory", "ApplicationContext"]
    """

    if item.get("relevant_sections"):
        return set(item["relevant_sections"])

    if item.get("relevant_section"):
        return {item["relevant_section"]}

    return set()


def source_hit(result, expected_source):
    if expected_source is None:
        return False

    return get_source(result) == expected_source


def section_hit(result, relevant_sections):
    section = get_section(result)

    if section is None:
        return False

    return section in relevant_sections


def calculate_source_metrics(results, expected_source):
    """
    Source-level Recall@1 / Recall@3 / MRR@3
    """

    if expected_source is None:
        return None

    hits = [
        source_hit(result, expected_source)
        for result in results
    ]

    recall_1 = 1 if len(hits) >= 1 and hits[0] else 0

    recall_3 = (
        1
        if any(hits[:3])
        else 0
    )

    mrr_3 = 0.0

    for rank, hit in enumerate(hits[:3], start=1):
        if hit:
            mrr_3 = 1.0 / rank
            break

    return {
        "recall@1": recall_1,
        "recall@3": recall_3,
        "mrr@3": mrr_3
    }


def calculate_section_metrics(results, relevant_sections):
    """
    Section-level Recall@1 / Recall@3 / MRR@3
    """

    if not relevant_sections:
        return None

    hits = [
        section_hit(result, relevant_sections)
        for result in results
    ]

    recall_1 = (
        1
        if len(hits) >= 1 and hits[0]
        else 0
    )

    recall_3 = (
        1
        if any(hits[:3])
        else 0
    )

    mrr_3 = 0.0

    for rank, hit in enumerate(hits[:3], start=1):
        if hit:
            mrr_3 = 1.0 / rank
            break

    return {
        "recall@1": recall_1,
        "recall@3": recall_3,
        "mrr@3": mrr_3
    }


def get_result_list(response):
    """
    兼容：
    1. 直接返回数组
    2. {"results": [...]}
    3. {"data": [...]}
    """

    data = response.json()

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        if isinstance(data.get("results"), list):
            return data["results"]

        if isinstance(data.get("data"), list):
            return data["data"]

    raise RuntimeError(
        f"无法识别接口返回格式：{data}"
    )





def request_search(
        endpoint,
        query,
        top_k=TOP_K,
        extra_params=None
):
    url = f"{BASE_URL}/{endpoint}"

    params = {
        "query": query,
        "topK": top_k
    }

    if extra_params:
        params.update(extra_params)

    response = requests.get(
        url,
        params=params,
        timeout=60
    )

    response.raise_for_status()

    return get_result_list(response)



def request_rerank(endpoint, query, top_k=RERANK_TOP_K):
    url = f"{BASE_URL}/{endpoint}"

    response = requests.get(
        url,
        params={
            "query": query,
            "topK": top_k
        },
        timeout=120
    )

    response.raise_for_status()

    return get_result_list(response)


def evaluate_method(
        dataset,
        method_name,
        endpoint,
        rerank=False,
        extra_params=None
):
    """
    执行某一种检索方式。

    返回：
    - 每题结果
    - Source-level 指标
    - Section-level 指标
    """

    records = []

    for index, item in enumerate(dataset, start=1):

        query = item["query"]
        expected_source = item.get("relevant_source")

        relevant_sections = get_relevant_sections(item)

        try:

            if rerank:
                results = request_rerank(
                    endpoint,
                    query,
                    RERANK_TOP_K
                )
            else:
                results = request_search(
                    endpoint,
                    query,
                    TOP_K,
                    extra_params=extra_params
                )

            source_metrics = calculate_source_metrics(
                results,
                expected_source
            )

            section_metrics = calculate_section_metrics(
                results,
                relevant_sections
            )

            records.append({
                "query": query,
                "expected_source": expected_source,
                "relevant_sections": list(
                    relevant_sections
                ),
                "results": results,
                "source": source_metrics,
                "section": section_metrics,
                "error": None
            })

            print(
                f"[{index:02d}/{len(dataset)}] "
                f"{method_name:<24} "
                f"{query}"
            )

        except Exception as e:

            print(
                f"[{index:02d}/{len(dataset)}] "
                f"{method_name:<24} "
                f"ERROR: {e}"
            )

            records.append({
                "query": query,
                "expected_source": expected_source,
                "relevant_sections": list(
                    relevant_sections
                ),
                "results": [],
                "source": None,
                "section": None,
                "error": str(e)
            })

    return records


def aggregate_metrics(records, metric_type):
    """
    聚合 In-KB 指标。

    metric_type:
        source
        section
    """

    values_r1 = []
    values_r3 = []
    values_mrr = []

    for record in records:

        metrics = record.get(metric_type)

        if metrics is None:
            continue

        values_r1.append(metrics["recall@1"])
        values_r3.append(metrics["recall@3"])
        values_mrr.append(metrics["mrr@3"])

    if not values_r1:
        return None

    return {
        "recall@1": sum(values_r1) / len(values_r1),
        "recall@3": sum(values_r3) / len(values_r3),
        "mrr@3": sum(values_mrr) / len(values_mrr),
        "count": len(values_r1)
    }


def print_metric_table(results):
    print()
    print("=" * 72)
    print("Source-level Retrieval")
    print("=" * 72)

    print(
        f"{'Method':<26}"
        f"{'Recall@1':>12}"
        f"{'Recall@3':>12}"
        f"{'MRR@3':>12}"
    )

    print("-" * 72)

    for method_name, records in results.items():

        metrics = aggregate_metrics(
            records,
            "source"
        )

        if metrics is None:
            continue

        print(
            f"{method_name:<26}"
            f"{metrics['recall@1']:>12.4f}"
            f"{metrics['recall@3']:>12.4f}"
            f"{metrics['mrr@3']:>12.4f}"
        )

    print()
    print("=" * 72)
    print("Section-level Retrieval")
    print("=" * 72)

    print(
        f"{'Method':<26}"
        f"{'Recall@1':>12}"
        f"{'Recall@3':>12}"
        f"{'MRR@3':>12}"
    )

    print("-" * 72)

    for method_name, records in results.items():

        metrics = aggregate_metrics(
            records,
            "section"
        )

        if metrics is None:
            continue

        print(
            f"{method_name:<26}"
            f"{metrics['recall@1']:>12.4f}"
            f"{metrics['recall@3']:>12.4f}"
            f"{metrics['mrr@3']:>12.4f}"
        )


def print_detail_comparison(results):
    """
    输出 Section-level 排名变化。
    """

    print()
    print("=" * 100)
    print("Section-level Detailed Comparison")
    print("=" * 100)

    method_names = list(results.keys())

    dataset_size = len(
        results[method_names[0]]
    )

    for i in range(dataset_size):

        base_record = results[
            method_names[0]
        ][i]

        query = base_record["query"]

        relevant_sections = (
            base_record["relevant_sections"]
        )

        # Out-of-KB 不打印 Section 结果
        if not relevant_sections:
            continue

        print()
        print(f"[{i + 1}] {query}")
        print(
            f"Gold Section: "
            f"{', '.join(relevant_sections)}"
        )

        for method_name in method_names:

            record = results[
                method_name
            ][i]

            result_list = record["results"]

            top_sections = [
                get_section(result)
                for result in result_list[:3]
            ]

            metrics = record.get(
                "section"
            )

            if metrics is None:
                continue

            print(
                f"  {method_name:<24} "
                f"R@1={metrics['recall@1']} "
                f"R@3={metrics['recall@3']} "
                f"MRR@3={metrics['mrr@3']:.3f} "
                f"Top3={top_sections}"
            )


def get_reranker_score(result):
    metadata = get_metadata(result)

    score = metadata.get(
        "reranker_score"
    )

    if score is None:
        score = metadata.get(
            "score"
        )

    if score is None:
        return None

    try:
        return float(score)
    except (ValueError, TypeError):
        return None


def collect_reranker_scores(records):
    """
    收集 Reranker Top-1 score。

    只对：
    - In-KB
    - Out-of-KB

    分开统计。
    """

    in_scores = []
    out_scores = []

    for record in records:

        results = record["results"]

        if not results:
            continue

        score = get_reranker_score(
            results[0]
        )

        if score is None:
            continue

        if record["expected_source"] is None:
            out_scores.append(score)
        else:
            in_scores.append(score)

    return in_scores, out_scores


def print_score_distribution(records):
    in_scores, out_scores = (
        collect_reranker_scores(records)
    )

    print()
    print("=" * 72)
    print("Reranker Score Distribution")
    print("=" * 72)

    if in_scores:

        print(
            f"In-KB:      "
            f"count={len(in_scores):2d}, "
            f"min={min(in_scores):.4f}, "
            f"max={max(in_scores):.4f}, "
            f"avg={statistics.mean(in_scores):.4f}"
        )

    if out_scores:

        print(
            f"Out-of-KB:  "
            f"count={len(out_scores):2d}, "
            f"min={min(out_scores):.4f}, "
            f"max={max(out_scores):.4f}, "
            f"avg={statistics.mean(out_scores):.4f}"
        )


def evaluate_threshold(records, threshold):
    """
    根据 Top-1 reranker score 判断：
    score >= threshold -> accept
    score < threshold  -> abstain

    In-KB:
        score >= threshold -> TP
        score < threshold  -> FN

    Out-of-KB:
        score >= threshold -> FP
        score < threshold  -> TN
    """

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    for record in records:

        results = record["results"]

        if not results:
            continue

        score = get_reranker_score(
            results[0]
        )

        if score is None:
            continue

        accepted = score >= threshold

        is_in_kb = (
            record["expected_source"] is not None
        )

        if is_in_kb:

            if accepted:
                tp += 1
            else:
                fn += 1

        else:

            if accepted:
                fp += 1
            else:
                tn += 1

    precision = (
        tp / (tp + fp)
        if tp + fp > 0
        else 0
    )

    recall = (
        tp / (tp + fn)
        if tp + fn > 0
        else 0
    )

    f1 = (
        2 * precision * recall
        / (precision + recall)
        if precision + recall > 0
        else 0
    )

    far = (
        fp / (fp + tn)
        if fp + tn > 0
        else 0
    )

    frr = (
        fn / (tp + fn)
        if tp + fn > 0
        else 0
    )

    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "far": far,
        "frr": frr
    }


def print_threshold_sweep(records):
    print()
    print("=" * 100)
    print("Reranker Threshold Sweep")
    print("=" * 100)

    print(
        f"{'Threshold':>10}"
        f"{'Precision':>12}"
        f"{'Recall':>12}"
        f"{'F1':>12}"
        f"{'FAR':>12}"
        f"{'FRR':>12}"
        f"{'TP':>6}"
        f"{'FP':>6}"
        f"{'TN':>6}"
        f"{'FN':>6}"
    )

    print("-" * 100)

    best = None

    thresholds = [
        0.00,
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
        0.95
    ]

    for threshold in thresholds:

        result = evaluate_threshold(
            records,
            threshold
        )

        print(
            f"{result['threshold']:>10.2f}"
            f"{result['precision']:>12.4f}"
            f"{result['recall']:>12.4f}"
            f"{result['f1']:>12.4f}"
            f"{result['far']:>12.4f}"
            f"{result['frr']:>12.4f}"
            f"{result['tp']:>6}"
            f"{result['fp']:>6}"
            f"{result['tn']:>6}"
            f"{result['fn']:>6}"
        )

        # 优先 F1，其次 FAR，最后 FRR
        if best is None:
            best = result
        else:
            current_key = (
                result["f1"],
                -result["far"],
                -result["frr"]
            )

            best_key = (
                best["f1"],
                -best["far"],
                -best["frr"]
            )

            if current_key > best_key:
                best = result

    print()
    print(
        f"Recommended threshold: "
        f"{best['threshold']:.2f}"
    )

    return best


def write_run_log(note, dataset, results, threshold_choices):
    """
    追加一行运行日志（evaluation_runs.jsonl）。

    动机：历史上出现过"同一指标有两套数字、说不清是哪版语料测的"——
    语料从 27 篇扩到 172 篇后，章节命中率的分母完全变了，
    旧数字与新数字混用会直接误导判断。

    因此每次评测都把"语料条件（--note）+ 验证集规模 + 各方案指标 + 推荐阈值"
    一起落盘，指标从此自带上下文。
    """
    entry = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "note": note or "",
        "dataset": {
            "path": str(DATASET_PATH.name),
            "size": len(dataset),
            "in_kb": sum(1 for item in dataset if item.get("relevant_source")),
            "out_of_kb": sum(1 for item in dataset if not item.get("relevant_source")),
        },
        "methods": {},
        "recommended_thresholds": {
            name: (row["threshold"] if row else None)
            for name, row in threshold_choices.items()
        },
    }

    for method_name, records in results.items():
        source = aggregate_metrics(records, "source")
        section = aggregate_metrics(records, "section")
        errors = sum(1 for record in records if record.get("error"))

        entry["methods"][method_name] = {
            "source_recall@1": round(source["recall@1"], 4) if source else None,
            "source_recall@3": round(source["recall@3"], 4) if source else None,
            "source_mrr@3": round(source["mrr@3"], 4) if source else None,
            "section_recall@1": round(section["recall@1"], 4) if section else None,
            "section_recall@3": round(section["recall@3"], 4) if section else None,
            "errors": errors,
        }

    with open(RUN_LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return RUN_LOG_PATH


def main(note=""):

    dataset = load_dataset()

    print("=" * 72)
    print("Retrieval Evaluation")
    print("=" * 72)

    print(
        f"Dataset size: {len(dataset)}"
    )

    print()

    results = {}

    # --------------------------------------------------
    # 1. Vector
    # --------------------------------------------------

    print("=" * 72)
    print("Evaluating Vector Retrieval")
    print("=" * 72)

    results["Vector"] = evaluate_method(
        dataset,
        "Vector",
        "search"
    )

    # --------------------------------------------------
    # 2. BM25
    # --------------------------------------------------

    print()
    print("=" * 72)
    print("Evaluating BM25 Retrieval")
    print("=" * 72)

    results["BM25"] = evaluate_method(
        dataset,
        "BM25",
        "bm25-search"
    )

    # --------------------------------------------------
    # 3. Hybrid
    # --------------------------------------------------

    print()
    print("=" * 72)
    print("Evaluating Hybrid Retrieval")
    print("=" * 72)

    results["Hybrid"] = evaluate_method(
        dataset,
        "Hybrid",
        "hybrid-search"
    )

    # --------------------------------------------------
    # 3.1 Hybrid Parameter Experiments
    # --------------------------------------------------

    hybrid_experiments = {
        "Hybrid A (V5+B5)": {
            "vectorK": 5,
            "bm25K": 5,
            "rrfK": 60
        },
        "Hybrid B (V10+B10)": {
            "vectorK": 10,
            "bm25K": 10,
            "rrfK": 60
        },
        "Hybrid C (V5+B10)": {
            "vectorK": 5,
            "bm25K": 10,
            "rrfK": 60
        },
        "Hybrid D (V10+B5)": {
            "vectorK": 10,
            "bm25K": 5,
            "rrfK": 60
        }
    }

    for method_name, params in hybrid_experiments.items():

        print()
        print("=" * 72)
        print(f"Evaluating {method_name}")
        print("=" * 72)

        results[method_name] = evaluate_method(
            dataset,
            method_name,
            "hybrid-experiment",
            extra_params=params
        )




    # --------------------------------------------------
    # 4. Hybrid + Reranker
    # --------------------------------------------------

    print()
    print("=" * 72)
    print("Evaluating Hybrid + Reranker")
    print("=" * 72)

    results["Hybrid + Reranker"] = evaluate_method(
        dataset,
        "Hybrid + Reranker",
        "rerank-test",
        rerank=True
    )

    # --------------------------------------------------
    # 5. Query Expansion + Reranker
    # --------------------------------------------------

    print()
    print("=" * 72)
    print("Evaluating Expansion + Reranker")
    print("=" * 72)

    results["Expansion + Reranker"] = evaluate_method(
        dataset,
        "Expansion + Reranker",
        "expansion-rerank-test",
        rerank=True
    )

    # --------------------------------------------------
    # Retrieval Metrics
    # --------------------------------------------------

    print_metric_table(results)

    # --------------------------------------------------
    # Detailed Section Comparison
    # --------------------------------------------------

    print_detail_comparison(results)

    # --------------------------------------------------
    # Reranker score analysis
    # --------------------------------------------------

    print_score_distribution(
        results["Hybrid + Reranker"]
    )

    print()
    print("=" * 72)
    print("Hybrid + Reranker Threshold Evaluation")
    print("=" * 72)

    hybrid_best = print_threshold_sweep(
        results["Hybrid + Reranker"]
    )

    print()
    print("=" * 72)
    print("Expansion + Reranker Threshold Evaluation")
    print("=" * 72)

    expansion_best = print_threshold_sweep(
        results["Expansion + Reranker"]
    )
    # --------------------------------------------------
    # Save complete result
    # --------------------------------------------------

    output_path = (
        Path(__file__).parent
        / "evaluation_results.json"
    )

    serializable_results = {}

    for method_name, records in results.items():

        serializable_results[
            method_name
        ] = records

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            serializable_results,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("=" * 72)
    print(
        f"Evaluation results saved to:"
        f"\n{output_path}"
    )
    print("=" * 72)

    run_log = write_run_log(
        note,
        dataset,
        results,
        {
            "Hybrid + Reranker": hybrid_best,
            "Expansion + Reranker": expansion_best,
        },
    )

    print()
    print(
        f"运行日志已追加：{run_log}"
        f"（note={note or '未填写'}；建议写明语料条件，如 '172 篇：27 自建 + 142 官方 + 3 测试'）"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="检索方案评测（含阈值扫描与运行日志）"
    )
    parser.add_argument(
        "--note",
        default="",
        help="本次评测的语料条件说明（写进 evaluation_runs.jsonl，避免数字脱离上下文）",
    )
    main(note=parser.parse_args().note)