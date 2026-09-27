# -*- coding: utf-8 -*-
"""
生成质量评测纯逻辑层的单元测试（无需应用、无需 Ollama、无需数据库）。

    python -m pytest evaluation/tests -q
"""

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVAL_DIR))

from judge_core import (  # noqa: E402
    DIMENSIONS,
    bias_summary,
    binarize,
    build_judge_prompt,
    calibration,
    cohen_kappa,
    dimension_agreement,
    disagreement_details,
    evaluate_gate,
    expected_points_of,
    format_contexts,
    parse_judge_output,
    summarize_scores,
)


# ==================================================================
# 上下文与 prompt 构造
# ==================================================================

def test_format_contexts_renders_header_and_body():
    text = format_contexts([
        {"source": "redis.md", "section": "Redis 分布式锁", "content": "正文A"},
        {"source": "mysql.md", "section": "", "page_number": 3, "content": "正文B"},
    ])
    assert "[1] redis.md — Redis 分布式锁" in text
    assert "正文A" in text
    assert "[2] mysql.md — 第3页" in text
    assert "正文B" in text


def test_format_contexts_empty():
    assert format_contexts([]) == "（无检索片段）"


def test_format_contexts_null_sentinels_are_dropped():
    text = format_contexts([{"source": "a.md", "section": None, "page_number": "null", "content": "x"}])
    assert text.startswith("[1] a.md")
    assert "null" not in text


def test_build_prompt_includes_question_contexts_answer():
    prompt = build_judge_prompt(
        "Redis分布式锁怎么实现", [{"source": "redis.md", "content": "用 SETNX"}], "用 SETNX[1]"
    )
    assert "Redis分布式锁怎么实现" in prompt
    assert "用 SETNX" in prompt
    assert "faithfulness" in prompt


def test_build_prompt_with_expected_points():
    prompt = build_judge_prompt("q", [], "a", ["要点一", "要点二"])
    assert "【参考要点】（问题要答到这些才算完整" in prompt
    assert "要点一" in prompt and "要点二" in prompt
    assert "不要自行增删" in prompt


def test_build_prompt_without_expected_points_has_no_block():
    prompt = build_judge_prompt("q", [], "a")
    assert "【参考要点】（问题要答到这些才算完整" not in prompt
    assert "填进 correctness_points" in prompt


def test_build_prompt_forces_two_step_correctness():
    prompt = build_judge_prompt("q", [], "a")
    assert "第一步（列要点）" in prompt
    assert "第二步（核覆盖）" in prompt
    assert "不等于完整" in prompt
    assert "最多给 4 分" in prompt
    assert "correctness_points" in prompt


def test_expected_points_of_variants():
    assert expected_points_of({"expected_points": ["a", " b ", ""]}) == ["a", "b"]
    assert expected_points_of({}) == []
    assert expected_points_of({"expected_points": "notalist"}) == []


# ==================================================================
# 裁判输出解析（容错是重点）
# ==================================================================

def test_parse_plain_json():
    out = parse_judge_output('{"faithfulness":5,"relevancy":4,"correctness":3,"reason":"ok"}')
    assert out["faithfulness"] == 5
    assert out["relevancy"] == 4
    assert out["correctness"] == 3
    assert out["reason"] == "ok"


def test_parse_fenced_json():
    out = parse_judge_output('```json\n{"faithfulness":1,"relevancy":2,"correctness":3}\n```')
    assert out["faithfulness"] == 1


def test_parse_with_surrounding_prose():
    out = parse_judge_output(
        '好的，结果如下：{"faithfulness":4,"relevancy":4,"correctness":4,"reason":"x"} 完毕'
    )
    assert out["correctness"] == 4


def test_parse_coerces_float_and_numeric_string():
    out = parse_judge_output('{"faithfulness":"5","relevancy":3.0,"correctness":4}')
    assert out["faithfulness"] == 5
    assert out["relevancy"] == 3


def test_parse_captures_correctness_points():
    out = parse_judge_output(
        '{"faithfulness":5,"relevancy":5,"correctness":4,'
        '"correctness_points":["要点一"," 要点二 "],"reason":"缺一个次要要点"}'
    )
    assert out["correctness_points"] == ["要点一", "要点二"]


def test_parse_missing_correctness_points_defaults_to_empty():
    out = parse_judge_output('{"faithfulness":5,"relevancy":5,"correctness":5}')
    assert out["correctness_points"] == []


def test_parse_malformed_correctness_points_is_not_fatal():
    out = parse_judge_output(
        '{"faithfulness":5,"relevancy":5,"correctness":5,"correctness_points":"notalist"}'
    )
    assert out["correctness"] == 5
    assert out["correctness_points"] == []


def test_parse_missing_dimension_raises():
    with pytest.raises(ValueError):
        parse_judge_output('{"faithfulness":5,"relevancy":4}')


def test_parse_out_of_range_raises():
    with pytest.raises(ValueError):
        parse_judge_output('{"faithfulness":9,"relevancy":4,"correctness":4}')


def test_parse_below_range_raises():
    with pytest.raises(ValueError):
        parse_judge_output('{"faithfulness":0,"relevancy":4,"correctness":4}')


def test_parse_no_json_raises():
    with pytest.raises(ValueError):
        parse_judge_output("完全不是 JSON")


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        parse_judge_output("")


# ==================================================================
# 指标汇总
# ==================================================================

def test_binarize():
    assert binarize(5) == 1
    assert binarize(4) == 1
    assert binarize(3) == 0
    assert binarize(None) is None


def test_summarize_scores_ignores_refused_and_errors():
    rows = [
        {"judge": {"faithfulness": 5, "relevancy": 4, "correctness": 5}},
        {"judge": {"faithfulness": 3, "relevancy": 4, "correctness": 2}},
        {"judge": None},
        {"judge": None, "error": "x"},
    ]
    summary = summarize_scores(rows)
    assert summary["faithfulness"]["n"] == 2
    assert summary["faithfulness"]["mean"] == 4.0
    assert summary["faithfulness"]["pass_rate"] == 0.5
    assert summary["faithfulness"]["distribution"]["5"] == 1


def test_summarize_scores_no_samples():
    summary = summarize_scores([{"judge": None}])
    for dimension in DIMENSIONS:
        assert summary[dimension] is None


# ==================================================================
# 一致性 / 校准
# ==================================================================

def test_cohen_kappa_perfect_agreement():
    assert cohen_kappa([0, 1, 1, 0], [0, 1, 1, 0]) == 1.0


def test_cohen_kappa_length_mismatch_returns_none():
    assert cohen_kappa([0, 1], [0, 1, 0]) is None


def test_cohen_kappa_degenerate_all_same():
    assert cohen_kappa([1, 1, 1], [1, 1, 1]) == 1.0
    assert cohen_kappa([1, 1, 1], [0, 0, 0]) == 0.0


def test_dimension_agreement_metrics():
    stats = dimension_agreement([5, 4, 3, None], [5, 3, 3, 4])
    assert stats["n"] == 3
    assert stats["exact"] == round(2 / 3, 4)
    assert stats["adjacent"] == 1.0
    assert stats["mae"] == round(1 / 3, 4)


def test_dimension_agreement_none_when_no_pairs():
    assert dimension_agreement([None], [None]) is None


def test_calibration_aligns_by_question():
    human = [
        {"question": "q1", "scores": {"faithfulness": 5, "relevancy": 5, "correctness": 5}},
        {"question": "q2", "scores": {"faithfulness": 3, "relevancy": 3, "correctness": 3}},
    ]
    judge = [
        {"question": "q1", "judge": {"faithfulness": 5, "relevancy": 4, "correctness": 5}},
        {"question": "q2", "judge": {"faithfulness": 3, "relevancy": 3, "correctness": 2}},
    ]
    per_dimension = calibration(human, judge)
    assert per_dimension["faithfulness"]["exact"] == 1.0
    assert per_dimension["relevancy"]["exact"] == 0.5
    assert per_dimension["relevancy"]["adjacent"] == 1.0


def test_calibration_skips_refused_judge():
    human = [{"question": "q1", "scores": {"faithfulness": 5, "relevancy": 5, "correctness": 5}}]
    judge = [{"question": "q1", "judge": None}]
    per_dimension = calibration(human, judge)
    assert per_dimension["faithfulness"] is None


def test_bias_summary_detects_lenient_judge():
    human = [
        {"question": "q1", "scores": {"correctness": 3}},
        {"question": "q2", "scores": {"correctness": 4}},
        {"question": "q3", "scores": {"correctness": 5}},
    ]
    judge = [
        {"question": "q1", "judge": {"correctness": 5}},
        {"question": "q2", "judge": {"correctness": 5}},
        {"question": "q3", "judge": {"correctness": 5}},
    ]

    summary = bias_summary(human, judge, "correctness")

    assert summary["n"] == 3
    assert summary["judge_higher"] == 2
    assert summary["equal"] == 1
    assert summary["human_higher"] == 0
    assert summary["mean_delta"] == round(-3 / 3, 4)


def test_bias_summary_none_when_no_pairs():
    assert bias_summary([{"question": "q1", "scores": {}}], [], "correctness") is None


def test_disagreement_details_sorted_and_filtered():
    human = [
        {"index": 1, "question": "q1", "scores": {"correctness": 3}},
        {"index": 2, "question": "q2", "scores": {"correctness": 5}},
        {"index": 3, "question": "q3", "scores": {"correctness": 4}},
    ]
    judge = [
        {"question": "q1", "judge": {"correctness": 5}},   # Δ=-2
        {"question": "q2", "judge": {"correctness": 5}},   # 一致
        {"question": "q3", "judge": {"correctness": 4}},   # 一致
    ]

    details = disagreement_details(human, judge, "correctness")

    assert len(details) == 1
    assert details[0]["index"] == 1
    assert details[0]["delta"] == -2


def test_disagreement_details_respects_min_delta():
    human = [{"index": 1, "question": "q1", "scores": {"correctness": 5}}]
    judge = [{"question": "q1", "judge": {"correctness": 5}}]

    assert disagreement_details(human, judge, "correctness", min_delta=1) == []
    assert len(disagreement_details(human, judge, "correctness", min_delta=0)) == 1


def test_disagreement_details_includes_exactly_one_apart():
    human = [{"index": 1, "question": "q1", "scores": {"correctness": 4}}]
    judge = [{"question": "q1", "judge": {"correctness": 5}}]

    details = disagreement_details(human, judge, "correctness", min_delta=1)

    assert len(details) == 1
    assert details[0]["delta"] == -1


def test_evaluate_gate_passes_when_agreement_high():
    per_dimension = {
        dim: {"n": 20, "exact": 0.9, "adjacent": 0.95, "mae": 0.1, "kappa_binary": 0.9}
        for dim in DIMENSIONS
    }
    gate = evaluate_gate(per_dimension)
    assert gate["passed"] is True
    assert gate["compared"] == 60


def test_evaluate_gate_fails_on_low_adjacent():
    per_dimension = {
        dim: {"n": 20, "exact": 0.5, "adjacent": 0.6, "mae": 0.1, "kappa_binary": 0.3}
        for dim in DIMENSIONS
    }
    gate = evaluate_gate(per_dimension)
    assert gate["passed"] is False
    assert any("相邻一致率" in failure for failure in gate["failures"])


def test_evaluate_gate_fails_on_high_mae():
    per_dimension = {
        dim: {"n": 20, "exact": 0.9, "adjacent": 0.9, "mae": 0.9, "kappa_binary": 0.9}
        for dim in DIMENSIONS
    }
    gate = evaluate_gate(per_dimension)
    assert gate["passed"] is False


def test_evaluate_gate_fails_on_missing_dimension():
    gate = evaluate_gate({"faithfulness": None})
    assert gate["passed"] is False
    assert gate["compared"] == 0
