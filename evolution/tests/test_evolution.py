"""evolution/ 的纯逻辑测试：归因规则、阈值重标定、扫参选优。

    python -m pytest evolution/tests -q

不依赖运行中的应用与数据库：归因只吃"轨迹 + 反馈"结构体，
扫参选优只吃指标行，都是纯函数。
"""
import json
import sys
from pathlib import Path

import pytest

EVOLUTION_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVOLUTION_DIR))

from attribution import attribute, build_case, citation_stats, recommend_threshold  # noqa: E402
import auto_tune  # noqa: E402
import evolve  # noqa: E402


def trace(refused=False, top1=0.80, threshold=0.60, answer="答案 [1]", candidates=None, context=None):
    return {
        "trace_id": "qa-test-0001",
        "question": "Redis 分布式锁怎么实现",
        "refused": refused,
        "top1_score": top1,
        "threshold_used": threshold,
        "answer": answer,
        "hits": {
            "candidates": [{"source": s} for s in (candidates if candidates is not None else ["redis.md", "mysql.md"])],
            "reranked": [{"source": s} for s in (context if context is not None else ["redis.md"])],
        },
    }


def with_feedback(record, rating="down", expected_source="", expected_section=""):
    record = dict(record)
    record["feedback"] = {
        "rating": rating,
        "expected_source": expected_source,
        "expected_section": expected_section,
    }
    return record


# ---------- 引用统计 ----------

def test_citation_stats_counts_compound_citations():
    stats = citation_stats("结论 A [1]，结论 B [2, 3]。\n\n参考来源：\n[1] redis.md", n_sources=3)
    assert stats["n_citations"] == 3
    assert stats["n_out_of_range"] == 0
    assert stats["citation_valid"] is True


def test_citation_stats_flags_out_of_range():
    stats = citation_stats("结论 [1] 与 [7]", n_sources=3)
    assert stats["n_out_of_range"] == 1
    assert stats["citation_valid"] is False


def test_citation_stats_flags_missing_citations():
    stats = citation_stats("这是一个没有任何引用的回答。", n_sources=3)
    assert stats["n_citations"] == 0
    assert stats["citation_valid"] is False


def test_citation_stats_ignores_reference_block():
    stats = citation_stats("回答没有编号 [1]\n\n参考来源：\n[1] a.md\n[2] b.md", n_sources=2)
    assert stats["n_citations"] == 1


# ---------- 归因 ----------

def test_positive_feedback_is_ok():
    result = attribute(with_feedback(trace(), rating="up"))
    assert result["layer"] == "ok"


def test_gold_absent_from_candidates_is_retrieval_miss():
    result = attribute(with_feedback(trace(), expected_source="kafka.md"))
    assert result["layer"] == "retrieval_miss"
    assert result["gold_in_candidates"] is False


def test_gold_in_candidates_but_not_in_context_is_ranking_error():
    result = attribute(with_feedback(trace(), expected_source="mysql.md"))
    assert result["layer"] == "ranking_error"
    assert result["gold_in_candidates"] is True
    assert result["gold_in_context"] is False


def test_gold_in_context_but_refused_is_threshold_error():
    record = with_feedback(
        trace(refused=True, top1=0.58, threshold=0.60), expected_source="redis.md"
    )
    result = attribute(record)
    assert result["layer"] == "threshold_error"
    assert result["boundary"] is True


def test_gold_in_context_and_answered_is_generation_issue():
    result = attribute(with_feedback(trace(), expected_source="redis.md"))
    assert result["layer"] == "generation_issue"


def test_invalid_citation_outranks_generation_issue():
    result = attribute(with_feedback(trace(answer="没有引用"), expected_source="redis.md"))
    assert result["layer"] == "citation_issue"


def test_refusal_without_gold_needs_label():
    result = attribute(with_feedback(trace(refused=True, top1=0.30), expected_source=""))
    assert result["layer"] == "refusal_needs_label"


def test_no_gold_no_refusal_needs_label():
    result = attribute(with_feedback(trace(), expected_source=""))
    assert result["layer"] == "needs_label"


def test_boundary_flag_only_near_threshold():
    far = attribute(with_feedback(trace(refused=True, top1=0.10, threshold=0.60), expected_source="redis.md"))
    assert far["boundary"] is False


def test_every_layer_has_action_text():
    from attribution import ACTIONS, LAYERS

    assert set(ACTIONS) == set(LAYERS)
    for layer in LAYERS:
        assert ACTIONS[layer]


def test_build_case_carries_gold_and_origin():
    record = with_feedback(trace(), expected_source="redis.md", expected_section="Redis 分布式锁")
    case = build_case(record, attribute(record))

    assert case["query"] == record["question"]
    assert case["relevant_source"] == "redis.md"
    assert case["relevant_section"] == "Redis 分布式锁"
    assert case["origin"]["layer"] == "generation_issue"
    assert case["origin"]["trace_id"] == "qa-test-0001"


# ---------- 阈值重标定 ----------

def _calibration_records():
    records = []
    for score in (0.90, 0.80, 0.70):
        record = trace(top1=score, candidates=["redis.md"], context=["redis.md"])
        records.append(with_feedback(record, expected_source="redis.md"))
    for score in (0.50, 0.40, 0.30):
        record = trace(top1=score, candidates=["mysql.md"], context=["mysql.md"])
        records.append(with_feedback(record, expected_source="redis.md"))
    return records


def test_recommend_threshold_separates_accept_and_refuse():
    result = recommend_threshold(_calibration_records(), thresholds=[0.30, 0.45, 0.55, 0.60, 0.65, 0.70, 0.80])

    assert result["n_labeled"] == 6
    best = result["recommended"]
    assert 0.55 <= best["threshold"] <= 0.70
    assert best["f1"] == 1.0
    assert best["far"] == 0.0


def test_recommend_threshold_marks_small_samples_unreliable():
    records = _calibration_records()[:2]
    result = recommend_threshold(records, min_samples=10)
    assert result["reliable"] is False


def test_recommend_threshold_excludes_ranking_cases():
    record = trace(top1=0.70, candidates=["redis.md", "mysql.md"], context=["mysql.md"])
    records = _calibration_records() + [with_feedback(record, expected_source="redis.md")]

    result = recommend_threshold(records)

    assert result["n_labeled"] == 6  # 金标在候选但被挤出上下文的样本不参与调阈值
    assert result["n_records"] == 7


# ---------- 扫参选优 ----------

def _row(top_k, rerank_top_k, source_r1, source_r3, section_r1, refusal_f1=0.9, threshold=0.6):
    return {
        "top_k": top_k,
        "rerank_top_k": rerank_top_k,
        "source_r1": source_r1,
        "source_r3": source_r3,
        "section_r1": section_r1,
        "refusal_f1": refusal_f1,
        "refusal_far": 0.0,
        "refusal_threshold": threshold,
        "evaluated": 100,
        "errors": 0,
    }


def test_select_best_follows_objective_order():
    rows = [
        _row(5, 3, 0.90, 0.99, 0.80),
        _row(10, 3, 0.92, 0.99, 0.78),
        _row(5, 5, 0.91, 0.98, 0.85),
    ]

    best = auto_tune.select_best(rows, ["source_r1", "source_r3", "section_r1"])
    assert best["top_k"] == 10  # 文档 R@1 优先

    best_section = auto_tune.select_best(rows, ["section_r1"])
    assert best_section["rerank_top_k"] == 5  # 只看章节 R@1 时选它


def test_build_policy_records_provenance():
    rows = [_row(5, 3, 0.98, 1.0, 0.90)]
    policy = auto_tune.build_policy(
        rows[0], rows, {"path": "evaluation/evaluation_questions.json", "evaluated": 134, "total": 134, "in_kb": 109},
        ["source_r1"],
    )

    assert policy["relevance_threshold"] == 0.6
    assert policy["top_k"] == 5 and policy["rerank_top_k"] == 3
    assert policy["source"] == "evolution/auto_tune.py"
    assert policy["dataset"]["evaluated"] == 134
    assert policy["candidates_evaluated"] == rows
    assert policy["evidence"]["source_r1"] == 0.98


def test_best_refusal_uses_f1_then_far():
    sweep = [
        {"threshold": 0.5, "f1": 0.9, "far": 0.1, "frr": 0.1},
        {"threshold": 0.6, "f1": 0.9, "far": 0.0, "frr": 0.2},
        {"threshold": 0.7, "f1": 0.8, "far": 0.0, "frr": 0.2},
    ]
    assert auto_tune.best_refusal(sweep)["threshold"] == 0.6


# ---------- evolve 的合并与去重 ----------

def test_merge_records_keeps_latest_feedback():
    export = {
        "traces": [{"trace_id": "t1", "question": "q", "hits": "{\"candidates\": []}"}],
        "feedback": [
            {"id": 1, "trace_id": "t1", "rating": "up"},
            {"id": 2, "trace_id": "t1", "rating": "down"},
        ],
    }
    records = evolve.merge_records(export)
    assert len(records) == 1
    assert records[0]["feedback"]["rating"] == "down"
    assert records[0]["hits"] == {"candidates": []}


def test_analyze_skips_traces_without_feedback():
    export = {
        "traces": [
            {"trace_id": "t1", "question": "有反馈", "hits": {"candidates": [], "reranked": []}},
            {"trace_id": "t2", "question": "没反馈", "hits": {}},
        ],
        "feedback": [{"id": 1, "trace_id": "t1", "rating": "up"}],
    }
    analysis = evolve.analyze(evolve.merge_records(export))
    assert len(analysis["analyzed"]) == 1
    assert analysis["layer_counter"]["ok"] == 1


def test_dedupe_cases_skips_queries_already_in_dataset(tmp_path):
    (tmp_path / "evaluation_questions.json").write_text(
        '[{"query": "Redis 分布式锁怎么实现", "relevant_source": "redis.md"}]', encoding="utf-8"
    )
    (tmp_path / "evolved_cases.json").write_text("[]", encoding="utf-8")

    cases = [
        {"query": "Redis 分布式锁怎么实现", "relevant_source": "redis.md"},
        {"query": "Kubernetes 探针有哪几种", "relevant_source": "k8s.md"},
        {"query": "Kubernetes 探针有哪几种", "relevant_source": "k8s.md"},
    ]

    fresh, duplicated, _ = evolve.dedupe_cases(cases, tmp_path)

    assert [case["query"] for case in fresh] == ["Kubernetes 探针有哪几种"]
    assert len(duplicated) == 2  # 与基础集重复 1 条 + 本轮内部重复 1 条


def test_write_outputs_writes_cases_pending_and_report(tmp_path):
    export = {
        "traces": [
            {
                "trace_id": "t1",
                "question": "Redis 分布式锁怎么实现",
                "refused": False,
                "top1_score": 0.8,
                "threshold_used": 0.6,
                "answer": "答案 [1]",
                "hits": {"candidates": [{"source": "redis.md"}], "reranked": [{"source": "redis.md"}]},
            },
            {
                "trace_id": "t2",
                "question": "Kubernetes 探针有哪几种",
                "refused": True,
                "top1_score": 0.2,
                "threshold_used": 0.6,
                "answer": "知识库中没有足够的信息，无法回答该问题。",
                "hits": {"candidates": [{"source": "k8s.md"}], "reranked": []},
            },
        ],
        "feedback": [
            {"id": 1, "trace_id": "t1", "rating": "down", "expected_source": "redis.md",
             "expected_section": "Redis 分布式锁"},
            {"id": 2, "trace_id": "t2", "rating": "down"},
        ],
    }

    records = evolve.merge_records(export)
    analysis = evolve.analyze(records)
    fresh, duplicated, evolved = evolve.dedupe_cases(analysis["cases"], tmp_path)
    result = evolve.write_outputs(fresh, analysis["pending"], evolved, analysis, tmp_path)

    assert result["evolved_total"] == 1
    assert result["pending_total"] == 1

    cases = json.loads((tmp_path / "evolved_cases.json").read_text(encoding="utf-8"))
    assert cases[0]["relevant_source"] == "redis.md"
    assert cases[0]["origin"]["layer"] == "generation_issue"

    pending = json.loads((tmp_path / "pending_labels.json").read_text(encoding="utf-8"))
    assert pending[0]["suspect_layer"] == "refusal_needs_label"

    report = (tmp_path / "evolution_report.md").read_text(encoding="utf-8")
    assert "失败层分布" in report
    assert "阈值重标定" in report
    assert "Redis 分布式锁怎么实现" in report


# ---------- 评测运行日志（指标自带语料上下文） ----------

def test_write_run_log_records_corpus_condition(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "evaluation"))
    import evaluate

    monkeypatch.setattr(evaluate, "RUN_LOG_PATH", tmp_path / "evaluation_runs.jsonl")

    results = [{"metadata": {"source": "redis.md", "section": "Redis 分布式锁"}}]
    records = [{
        "query": "Redis 分布式锁怎么实现",
        "expected_source": "redis.md",
        "relevant_sections": ["Redis 分布式锁"],
        "results": results,
        "source": evaluate.calculate_source_metrics(results, "redis.md"),
        "section": evaluate.calculate_section_metrics(results, {"Redis 分布式锁"}),
        "error": None,
    }]

    path = evaluate.write_run_log(
        "172 篇：27 自建 + 142 官方 + 3 测试",
        [{"query": "Redis 分布式锁怎么实现", "relevant_source": "redis.md"}],
        {"Hybrid + Reranker": records},
        {"Hybrid + Reranker": {"threshold": 0.60}},
    )

    entry = json.loads(path.read_text(encoding="utf-8").strip())

    assert entry["note"] == "172 篇：27 自建 + 142 官方 + 3 测试"
    assert entry["dataset"] == {
        "path": "evaluation_questions.json", "size": 1, "in_kb": 1, "out_of_kb": 0
    }
    assert entry["methods"]["Hybrid + Reranker"]["source_recall@1"] == 1.0
    assert entry["methods"]["Hybrid + Reranker"]["section_recall@1"] == 1.0
    assert entry["recommended_thresholds"]["Hybrid + Reranker"] == 0.60
