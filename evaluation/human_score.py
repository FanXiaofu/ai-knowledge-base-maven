# -*- coding: utf-8 -*-
"""
交互式人工评分：终端里逐题提示，直接敲 1~5，自动写进 human_labels.json。

为什么要它：手改 JSON 容易写坏（引号、逗号、括号），还得在两个文件之间来回看。
这个脚本把「看材料 → 打分 → 落盘」合成一步，每题答完立刻保存，中断不丢进度。

独立性保证：本脚本**只显示回答与上下文，绝不显示裁判分数**——即使材料取自
judge_scores.json，也只读 answer/contexts 字段，不读 judge 字段。人工与裁判必须
独立打分，否则校准出来的"一致率"没有意义。

材料来源（按优先级自动选择）：
    1. evaluation/judge/human_items.json   （human_rate.py 生成，推荐）
    2. evaluation/judge/judge_scores.json  （回退：只取 answer/contexts，不取 judge）

标签文件（就地更新，已填的保留）：
    evaluation/judge/human_labels.json

评分途中可用的命令（任意输入处敲）：
    回车   跳过本题（留空，稍后再填）
    b      回到上一题重打
    r      重新显示本题材料
    s      保存并退出（已填的保留）
    q      不保存退出

用法：
    python -X utf8 evaluation/human_score.py
    python -X utf8 evaluation/human_score.py --limit 8
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from judge_core import (  # noqa: E402
    DIMENSIONS,
    SCORE_MIN,
    SCORE_MAX,
    PASS_SCORE,
    format_contexts,
)

JUDGE_DIR = HERE / "judge"
ITEMS_PATH = JUDGE_DIR / "human_items.json"
JUDGE_SCORES_PATH = JUDGE_DIR / "judge_scores.json"
LABELS_PATH = JUDGE_DIR / "human_labels.json"

COMMANDS = {
    "": "skip",
    "b": "back",
    "r": "reload",
    "s": "save_exit",
    "q": "quit",
    "exit": "quit",
    "quit": "quit",
    "退出": "quit",
    "保存": "save_exit",
}

HINT = "  （1~5 整数；回车跳过 / b 上一题 / r 重看 / s 保存退出 / q 退出）"


def load_items(explicit: str | None) -> dict:
    """返回 {question: {expected_source, contexts, answer, refused}}。"""

    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates += [ITEMS_PATH, JUDGE_SCORES_PATH]

    for path in candidates:
        if not path.exists():
            continue

        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows") if isinstance(payload, dict) else payload

        if not rows:
            continue

        items = {}
        for row in rows:
            items[row.get("question")] = {
                "index": row.get("index"),
                "expected_source": row.get("expected_source"),
                "relevant_sections": row.get("relevant_sections") or [],
                "refused": row.get("refused"),
                "contexts": row.get("contexts") or [],
                "answer": row.get("answer") or "",
                "error": row.get("error"),
            }

        print(f"[材料] 读取自 {path.name}（{len(items)} 条）")
        return items

    raise SystemExit(
        "找不到评分材料。请先运行：\n"
        "    python -X utf8 evaluation/human_rate.py --limit 20"
    )


def show(record: dict, item: dict) -> None:
    print()
    print("=" * 72)
    print(f"[{record.get('index')}] {record.get('question')}")
    print("=" * 72)

    expected = record.get("expected_source") or "（库外题，正确行为应为拒答）"
    print(f"金标来源：{expected}")
    if record.get("relevant_sections"):
        print(f"金标章节：{', '.join(record['relevant_sections'])}")

    if item is None:
        print("\n> 该题没有材料（可能未取数成功），无法评判，将跳过。")
        return

    if item.get("error"):
        print(f"\n> 取数失败：{item['error']}")
        return

    if item.get("refused"):
        print("\n> 应用选择了拒答（库外题时属正确行为，不由本表评判），将跳过。")
        return

    print("\n--- 上下文片段（判 faithfulness 只看这里）---")
    print(format_contexts(item["contexts"]))
    print("\n--- 回答 ---")
    print(item["answer"])


def read_score(prompt_text: str):
    """返回 (action, value)。action 为 'value' | 'skip' | 'back' | 'reload' | 'save_exit' | 'quit'。"""

    while True:
        raw = input(prompt_text).strip().lower()

        if raw in COMMANDS:
            return COMMANDS[raw], None

        try:
            value = int(raw)
        except ValueError:
            print("  请输入 1~5 的整数。" + HINT)
            continue

        if not (SCORE_MIN <= value <= SCORE_MAX):
            print(f"  取值范围是 {SCORE_MIN}~{SCORE_MAX}。" + HINT)
            continue

        return "value", value


def ask_scores():
    """连续问三个维度，返回 (action, {scores, comment})。"""

    scores = {}

    for dimension in DIMENSIONS:
        action, value = read_score(f"  {dimension:<14}[1-{SCORE_MAX}]: ")
        if action != "value":
            return action, None
        scores[dimension] = value

    comment = input("  备注（可选，回车跳过）: ").strip()

    return "saved", {"scores": scores, "comment": comment}


def save(labels, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="交互式人工评分（写进 human_labels.json）")
    parser.add_argument("--limit", type=int, default=0, help="只评前 N 条（0=全部）")
    parser.add_argument("--items", default=None, help="材料文件（默认自动查找）")
    parser.add_argument("--labels", default=str(LABELS_PATH), help="标签文件（就地更新）")
    parser.add_argument("--restart", action="store_true", help="忽略已填分数，全部重打")
    args = parser.parse_args()

    labels_path = Path(args.labels)
    if not labels_path.exists():
        print(f"[错误] 找不到标签文件：{labels_path}")
        print("       请先运行：python -X utf8 evaluation/human_rate.py --limit 20")
        return 2

    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    items = load_items(args.items)

    if args.restart:
        for row in labels:
            row["scores"] = {dimension: None for dimension in DIMENSIONS}
            row["comment"] = ""

    if args.limit:
        labels = labels[: args.limit]

    pending = [row for row in labels if any(
        row.get("scores", {}).get(dimension) is None for dimension in DIMENSIONS
    )]

    print()
    print(f"共 {len(labels)} 条，待评 {len(pending)} 条。")
    print(f"评分锚点见 {JUDGE_DIR / 'human_rubric.md'}；材料逐题显示在下方。")
    print("提示：判 faithfulness 时只看给出的上下文片段，不要用你自己的知识补依据。")

    index = 0

    while 0 <= index < len(labels):

        record = labels[index]
        item = items.get(record.get("question"))

        scores = record.get("scores") or {}
        already = all(scores.get(dimension) is not None for dimension in DIMENSIONS)

        if already and not args.restart:
            print(f"\n[{record.get('index')}] 已评分 {scores}，跳过（改分请用 --restart）")
            index += 1
            continue

        show(record, item)

        if item is None or item.get("error") or item.get("refused"):
            if item is not None and item.get("refused"):
                record["scores"] = {dimension: None for dimension in DIMENSIONS}
                save(labels, labels_path)
            index += 1
            continue

        action, payload = ask_scores()

        if action == "quit":
            print("\n已放弃本次未保存的改动（此前每题都已即时保存）。")
            break

        if action == "save_exit":
            save(labels, labels_path)
            print(f"\n已保存：{labels_path}")
            break

        if action == "back":
            index = max(0, index - 1)
            continue

        if action == "reload":
            continue

        if action == "skip":
            print("  已跳过，稍后可重跑本脚本补填。")
            index += 1
            continue

        record["scores"] = payload["scores"]
        record["comment"] = payload["comment"]
        save(labels, labels_path)
        print(f"  ✓ 已保存：{payload['scores']}")
        index += 1

    filled = sum(
        1 for row in labels
        if all((row.get("scores") or {}).get(dimension) is not None for dimension in DIMENSIONS)
    )
    print()
    print(f"完成度：{filled}/{len(labels)} 条已评分（>= {PASS_SCORE} 记为通过）。")
    print(f"标签文件：{labels_path}")
    print("下一步：python -X utf8 evaluation/judge_calibrate.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
