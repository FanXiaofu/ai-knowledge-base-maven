# -*- coding: utf-8 -*-
"""
交互式评分脚本的单元测试（用 monkeypatch 模拟键盘输入，不需要应用与 Ollama）。

    python -m pytest evaluation/tests -q
"""

import builtins
import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVAL_DIR))

import human_score  # noqa: E402


def test_load_items_from_rows_payload(tmp_path):
    path = tmp_path / "items.json"
    path.write_text(
        json.dumps({
            "rows": [
                {
                    "index": 1,
                    "question": "q1",
                    "expected_source": "a.md",
                    "relevant_sections": ["s"],
                    "refused": False,
                    "answer": "ans",
                    "contexts": [{"source": "a.md", "content": "c"}],
                }
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    items = human_score.load_items(str(path))

    assert "q1" in items
    assert items["q1"]["answer"] == "ans"
    assert items["q1"]["contexts"][0]["source"] == "a.md"
    assert items["q1"]["refused"] is False


def test_load_items_from_bare_list(tmp_path):
    path = tmp_path / "items.json"
    path.write_text(
        json.dumps([{"index": 1, "question": "q1", "answer": "a"}]), encoding="utf-8"
    )

    items = human_score.load_items(str(path))

    assert items["q1"]["answer"] == "a"
    # 缺省字段要能兜底，不能抛异常
    assert items["q1"]["contexts"] == []


def test_read_score_accepts_valid(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *args: "4")

    action, value = human_score.read_score("x")

    assert (action, value) == ("value", 4)


def test_read_score_rejects_out_of_range_then_accepts(monkeypatch):
    answers = iter(["7", "0", "3"])
    monkeypatch.setattr(builtins, "input", lambda *args: next(answers))

    action, value = human_score.read_score("x")

    assert (action, value) == ("value", 3)


def test_read_score_rejects_non_numeric_then_accepts(monkeypatch):
    answers = iter(["abc", "5"])
    monkeypatch.setattr(builtins, "input", lambda *args: next(answers))

    action, value = human_score.read_score("x")

    assert (action, value) == ("value", 5)


def test_read_score_commands(monkeypatch):
    cases = [
        ("", "skip"),
        ("b", "back"),
        ("r", "reload"),
        ("s", "save_exit"),
        ("q", "quit"),
        ("退出", "quit"),
        ("保存", "save_exit"),
    ]

    for raw, expected in cases:
        monkeypatch.setattr(builtins, "input", lambda *args, _raw=raw: _raw)
        action, value = human_score.read_score("x")
        assert action == expected, raw
        assert value is None


def test_ask_scores_collects_three_dimensions(monkeypatch):
    answers = iter(["5", "4", "3", "备注"])
    monkeypatch.setattr(builtins, "input", lambda *args: next(answers))

    action, payload = human_score.ask_scores()

    assert action == "saved"
    assert payload["scores"] == {"faithfulness": 5, "relevancy": 4, "correctness": 3}
    assert payload["comment"] == "备注"


def test_ask_scores_aborts_on_command(monkeypatch):
    answers = iter(["5", "b"])
    monkeypatch.setattr(builtins, "input", lambda *args: next(answers))

    action, payload = human_score.ask_scores()

    assert action == "back"
    assert payload is None
