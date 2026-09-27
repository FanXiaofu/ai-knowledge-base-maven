# -*- coding: utf-8 -*-
"""
脚本层渲染路径的单元测试（纯函数，不联网、不依赖应用与 Ollama）。

覆盖 judge_eval / human_rate / judge_calibrate 的报告渲染，确保
"取到数据后能正确落成报告"这条路径不会在评测中途才炸。

    python -m pytest evaluation/tests -q
"""

import sys
from pathlib import Path
from types import SimpleNamespace

EVAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVAL_DIR))

from judge_calibrate import render_report as render_calibration  # noqa: E402
from judge_core import DIMENSIONS, summarize_scores  # noqa: E402
from judge_eval import render_report as render_judge_report  # noqa: E402
from human_rate import render_sheet  # noqa: E402


def _args(**overrides):
    base = {
        "note": "smoke",
        "judge_model": "qwen2.5:7b-instruct",
        "min_adjacent": 0.8,
        "max_mae": 0.5,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _judged_row(index, judge):
    return {
        "index": index,
        "question": f"q{index}",
        "expected_source": "redis.md",
        "relevant_sections": ["Redis 分布式锁"],
        "refused": False,
        "answer": "回答[1]",
        "retrieval_query": f"q{index}",
        "top1_score": 0.9,
        "threshold": 0.6,
        "contexts": [{"source": "redis.md", "section": "s", "content": "c"}],
        "context_hit": True,
        "judge": judge,
        "error": None,
    }


def test_judge_report_renders_summary_and_rows():
    rows = [
        _judged_row(1, {"faithfulness": 5, "relevancy": 4, "correctness": 5, "reason": "ok"}),
        {
            "index": 2, "question": "q2", "expected_source": None, "relevant_sections": [],
            "refused": True, "answer": "知识库中没有足够的信息", "retrieval_query": "q2",
            "top1_score": None, "threshold": 0.6, "contexts": [], "context_hit": None,
            "judge": None, "error": None,
        },
        {
            "index": 3, "question": "q3", "expected_source": "a.md", "relevant_sections": [],
            "refused": False, "answer": "", "retrieval_query": "q3", "top1_score": 0.7,
            "threshold": 0.6, "contexts": [], "context_hit": False, "judge": None,
            "error": "TimeoutError: x",
        },
    ]
    report = render_judge_report(rows, summarize_scores(rows), _args())

    assert "生成质量评测报告" in report
    assert "faithfulness" in report
    assert "smoke" in report
    assert "context_hit" in report
    assert "ERROR: TimeoutError" in report


def test_human_sheet_renders_answer_and_contexts():
    records = [
        {
            "index": 1, "question": "q1", "expected_source": "redis.md",
            "relevant_sections": ["Redis 分布式锁"], "refused": False,
            "answer": "回答[1]", "contexts": [{"source": "redis.md", "content": "片段"}],
            "error": None, "scores": {d: None for d in DIMENSIONS}, "comment": "",
        },
        {
            "index": 2, "question": "q2", "expected_source": None,
            "relevant_sections": [], "refused": True, "answer": "拒答",
            "contexts": [], "error": None, "scores": {d: None for d in DIMENSIONS}, "comment": "",
        },
    ]
    sheet = render_sheet(records, "rubric 文本", _args())

    assert "人工评分表" in sheet
    assert "rubric 文本" in sheet
    assert "片段" in sheet
    assert "回答[1]" in sheet
    assert "库外题" in sheet


def _diagnosis(details=None, mean_delta=-0.5):
    return {
        "bias": {
            dimension: {
                "n": 5,
                "mean_delta": mean_delta,
                "judge_higher": 3,
                "human_higher": 1,
                "equal": 1,
            }
            for dimension in DIMENSIONS
        },
        "details": details or [],
    }


def test_calibration_report_renders_gate_verdict():
    per_dimension = {
        dimension: {"n": 5, "exact": 0.8, "adjacent": 0.9, "mae": 0.2, "kappa_binary": 0.7}
        for dimension in DIMENSIONS
    }
    gate = {"passed": True, "failures": [], "compared": 15}

    report = render_calibration(per_dimension, gate, _diagnosis(), [{"question": "q1"}],
                                {"judge_model": "m", "note": "n"}, _args())

    assert "裁判校准报告" in report
    assert "裁判可信" in report
    assert "faithfulness" in report
    assert "方向性" in report


def test_calibration_report_renders_failures():
    per_dimension = {
        dimension: {"n": 5, "exact": 0.4, "adjacent": 0.5, "mae": 0.9, "kappa_binary": 0.1}
        for dimension in DIMENSIONS
    }
    gate = {"passed": False, "failures": ["faithfulness: MAE 0.9 > 0.5"], "compared": 15}

    report = render_calibration(per_dimension, gate, _diagnosis(), [{"question": "q1"}],
                                {"judge_model": "m", "note": "n"}, _args())

    assert "禁止直接采用" in report
    assert "MAE 0.9 > 0.5" in report


def test_calibration_report_lists_disagreements():
    details = [{
        "index": 5, "dimension": "correctness", "question": "q5",
        "human": 3, "judge": 5, "delta": -2,
    }]
    per_dimension = {
        dimension: {"n": 1, "exact": 0.0, "adjacent": 0.0, "mae": 2.0, "kappa_binary": 0.0}
        for dimension in DIMENSIONS
    }
    gate = {"passed": False, "failures": ["correctness: MAE 2.0 > 0.5"], "compared": 3}

    report = render_calibration(per_dimension, gate, _diagnosis(details), [{"question": "q5"}],
                                {"judge_model": "m", "note": "n"}, _args())

    assert "分歧明细" in report
    assert "| 5 | correctness | q5 | 3 | 5 | -2 |" in report


def test_calibration_report_no_disagreements():
    per_dimension = {
        dimension: {"n": 1, "exact": 1.0, "adjacent": 1.0, "mae": 0.0, "kappa_binary": 1.0}
        for dimension in DIMENSIONS
    }
    gate = {"passed": True, "failures": [], "compared": 3}

    report = render_calibration(per_dimension, gate, _diagnosis(details=[]),
                                [{"question": "q1"}], {"judge_model": "m", "note": "n"}, _args())

    assert "所有维度分差都 < 1" in report
