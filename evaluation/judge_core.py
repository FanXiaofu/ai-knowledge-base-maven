# -*- coding: utf-8 -*-
"""
生成质量评测的纯逻辑层（无网络、无文件 IO，可单测）。

在此之前，评测只覆盖"检索层"（文档/章节 R@1/R@3）与"拒答层"（阈值 P/R/F1/FAR），
回答本身的**生成质量没有任何自动指标**。这里补齐三个维度（对齐 RAGAS 的核心口径，
但用本地裁判而不是外部服务）：

    faithfulness 忠实度：回答中的事实性陈述是否都能在检索到的片段里找到依据（= 幻觉检测）
    relevancy    切题度：回答是否直接命中用户问题
    correctness  正确性：内容是否正确（提供 expected_points 时按要点覆盖评判）

分数区间 1~5，>= PASS_SCORE(4) 视为通过。

设计约束：
- 全部为确定性函数，便于回归与复算（与 evaluation/evaluate.py 的口径纪律一致）；
- 裁判模型输出格式不可全信，解析层必须容错（代码块包裹、前后夹带解释都要能救回来）；
- 与人工评分的一致率由 judge_calibrate.py 判定，本模块只提供计算，不做放行决定。
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional, Sequence

DIMENSIONS = ("faithfulness", "relevancy", "correctness")

SCORE_MIN = 1
SCORE_MAX = 5
PASS_SCORE = 4

# 裁判可能把 JSON 包在 ```json ... ``` 里，也可能在前后夹带解释文字
_FENCED_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


# ==================================================================
# 输入构造
# ==================================================================

def format_contexts(contexts: Sequence[dict]) -> str:
    """把检索片段渲染成裁判可读的带编号上下文（编号口径与 buildContext() 一致）。"""

    if not contexts:
        return "（无检索片段）"

    lines = []

    for index, context in enumerate(contexts, start=1):

        source = context.get("source") or "未知来源"
        section = context.get("section")
        page_number = context.get("page_number")

        header = f"[{index}] {source}"

        if page_number not in (None, "", "null"):
            header += f" — 第{page_number}页"

        if section not in (None, "", "null"):
            header += f" — {section}"

        content = (context.get("content") or "").strip()
        lines.append(f"{header}\n{content}" if content else header)

    return "\n\n".join(lines)


def build_judge_prompt(
        question: str,
        contexts: Sequence[dict],
        answer: str,
        expected_points: Optional[Sequence[str]] = None,
) -> str:
    """构造裁判 prompt。

    faithfulness 只依据 contexts 判断（不允许裁判用自己的知识"补依据"）。

    correctness 强制两步（先列要点、再核覆盖）：实测发现，若只写"正确且完整"，裁判会凭
    "内容出自知识库、且切题"直接给 5，对"答全没答全"完全不敏感——人工与裁判在
    correctness 上因此系统性分歧（裁判偏宽）。把完整性拆成显式步骤、并写明"漏关键要点
    最多 4 分"，才逼得裁判真的去核对覆盖情况。

    有 expected_points 时以它为要点清单（问题作者定的标尺），否则由裁判自己列。
    """

    context_text = format_contexts(contexts)

    if expected_points:
        points = "\n".join(f"- {point}" for point in expected_points)
        points_block = (
            "\n【参考要点】（问题要答到这些才算完整；correctness 以它为准）\n"
            + points
            + "\n"
        )
        first_step = "直接采用下面【参考要点】里列出的要点，不要自行增删"
    else:
        points_block = ""
        first_step = "先自己想清楚该问题要答到哪些要点（2~5 条），填进 correctness_points"

    return f"""请你对下面这条 RAG 回答打分。三个维度各自独立评判，取值均为 1~5 的整数。

【评分维度】
1. faithfulness（忠实度）：回答中的事实性陈述，是否都能在【知识库片段】中找到依据。
   - 5 = 全程有据；4 = 个别无依据的引申；3 = 少量无依据；2 = 多处无依据；1 = 明显编造。
2. relevancy（切题度）：回答是否直接命中【用户问题】。
   - 5 = 完全切题；4 = 基本切题略有冗余；3 = 部分偏题；2 = 大多偏离；1 = 答非所问。
3. correctness（正确性）：**必须先做两步，禁止凭整体印象直接给分。**
   第一步（列要点）：{first_step}。
   第二步（核覆盖）：逐条核对回答是否答到了每个要点，统计覆盖情况。
   打分标尺（以要点覆盖为准）：
     5 = 要点全部覆盖，且内容无误
     4 = 覆盖大部分要点，仅缺 1 个次要要点
     3 = 缺关键要点，或部分内容有误
     2 = 只覆盖少量要点
     1 = 基本没答到点，或明显错误
   ⚠️ 内容出自知识库、且切中了问题，**不等于完整**。只要漏掉关键要点，最多给 4 分；
      不要因为"表述通顺、来源正确"就给 5 分。

【重要】
- 评判 faithfulness 时只依据【知识库片段】，不要用你自己掌握的知识补充依据。
- 若回答明确表示"知识库中没有足够的信息"（即恰当拒答），faithfulness 应给 5，
  relevancy / correctness 按"拒答是否恰当"评判。
- 回答末尾若出现"参考来源"区块，那是系统自动附加的，不作为回答正文评判。

【知识库片段】
{context_text}

【用户问题】
{question}
{points_block}
【待评判回答】
{answer}

【输出格式】只输出一个 JSON 对象，不要输出任何多余文字：
{{"faithfulness": <1-5>, "relevancy": <1-5>, "correctness": <1-5>, "correctness_points": ["<要点1>", "<要点2>"], "reason": "<一句话理由>"}}
"""


def expected_points_of(item: dict) -> list:
    """读取评测条目里的参考要点（可选字段，向后兼容：没有就返回空列表）。"""

    points = item.get("expected_points")

    if isinstance(points, list):
        return [point for point in (str(p).strip() for p in points) if point]

    return []


# ==================================================================
# 裁判输出解析（容错）
# ==================================================================

def _extract_json_object(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("裁判输出为空")

    fenced = _FENCED_RE.search(text)
    candidate = fenced.group(1) if fenced else text

    match = _OBJECT_RE.search(candidate)

    if not match:
        raise ValueError(f"裁判输出中未找到 JSON 对象：{text[:200]!r}")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise ValueError(f"裁判输出 JSON 解析失败（{error}）：{match.group(0)[:200]!r}")


def parse_judge_output(text: str) -> dict:
    """把裁判模型输出解析成 {维度: 1~5, reason: str}；任何非法情况抛 ValueError。"""

    data = _extract_json_object(text)

    scores: dict = {}

    for dimension in DIMENSIONS:

        if dimension not in data:
            raise ValueError(f"裁判输出缺少维度 {dimension}：{data}")

        value = data[dimension]

        try:
            number = int(round(float(value)))
        except (TypeError, ValueError):
            raise ValueError(f"维度 {dimension} 的分数无法解析：{value!r}")

        if not (SCORE_MIN <= number <= SCORE_MAX):
            raise ValueError(f"维度 {dimension} 的分数越界（{number}）：应为 {SCORE_MIN}~{SCORE_MAX}")

        scores[dimension] = number

    scores["reason"] = str(data.get("reason", "")).strip()

    # 裁判列的要点（非必需字段：缺失或格式不对都不算解析失败，只是拿不到这条证据）
    points = data.get("correctness_points")
    scores["correctness_points"] = (
        [str(point).strip() for point in points if str(point).strip()]
        if isinstance(points, list)
        else []
    )

    return scores


# ==================================================================
# 指标汇总
# ==================================================================

def binarize(score: Optional[int], threshold: int = PASS_SCORE) -> Optional[int]:
    """把 1~5 分二值化（>= 阈值为 1），用于算二分类 kappa。"""

    if score is None:
        return None

    return 1 if score >= threshold else 0


def summarize_scores(rows: Iterable[dict]) -> dict:
    """汇总已评判记录的每维均值 / 通过率 / 分布。拒答或无裁判分数的记录不计入。"""

    summary: dict = {}

    for dimension in DIMENSIONS:

        values = []

        for row in rows:
            judge = row.get("judge")

            if not judge:
                continue

            value = judge.get(dimension)

            if isinstance(value, int):
                values.append(value)

        if not values:
            summary[dimension] = None
            continue

        distribution = {
            str(score): values.count(score)
            for score in range(SCORE_MIN, SCORE_MAX + 1)
        }

        summary[dimension] = {
            "n": len(values),
            "mean": round(sum(values) / len(values), 4),
            "pass_rate": round(
                sum(1 for value in values if value >= PASS_SCORE) / len(values), 4
            ),
            "distribution": distribution,
        }

    return summary


# ==================================================================
# 一致性 / 校准
# ==================================================================

def cohen_kappa(labels_a: Sequence, labels_b: Sequence) -> Optional[float]:
    """Cohen's kappa（未加权）。输入两串等长的离散标签。"""

    if not labels_a or len(labels_a) != len(labels_b):
        return None

    categories = sorted(set(labels_a) | set(labels_b))
    n = len(labels_a)

    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n

    expected = 0.0
    for category in categories:
        proportion_a = sum(1 for a in labels_a if a == category) / n
        proportion_b = sum(1 for b in labels_b if b == category) / n
        expected += proportion_a * proportion_b

    if expected >= 1.0:
        return 1.0 if observed == 1.0 else 0.0

    return round((observed - expected) / (1 - expected), 4)


def dimension_agreement(
        human_scores: Sequence[Optional[int]],
        judge_scores: Sequence[Optional[int]],
        threshold: int = PASS_SCORE,
) -> Optional[dict]:
    """两个评分序列的成对一致度（只统计两侧都有效的一对）。

    - exact        完全相同比例
    - adjacent     相差 <=1 的比例（评分带主观性，这个比 exact 稳）
    - mae          平均绝对误差
    - kappa_binary 以 PASS_SCORE 二值化后的 Cohen's kappa
    """

    pairs = [
        (human, judge)
        for human, judge in zip(human_scores, judge_scores)
        if human is not None and judge is not None
    ]

    if not pairs:
        return None

    n = len(pairs)

    exact = sum(1 for human, judge in pairs if human == judge) / n
    adjacent = sum(1 for human, judge in pairs if abs(human - judge) <= 1) / n
    mae = sum(abs(human - judge) for human, judge in pairs) / n

    kappa = cohen_kappa(
        [binarize(human, threshold) for human, _ in pairs],
        [binarize(judge, threshold) for _, judge in pairs],
    )

    return {
        "n": n,
        "exact": round(exact, 4),
        "adjacent": round(adjacent, 4),
        "mae": round(mae, 4),
        "kappa_binary": kappa,
    }


def calibration(
        human_rows: Sequence[dict],
        judge_rows: Sequence[dict],
        threshold: int = PASS_SCORE,
) -> dict:
    """按 question 文本对齐"人工评分"与"裁判评分"，逐维度算一致度。"""

    judge_by_question: dict = {}

    for row in judge_rows:
        judge_by_question.setdefault(row.get("question"), row.get("judge"))

    per_dimension: dict = {}

    for dimension in DIMENSIONS:

        human_scores: list = []
        judge_scores: list = []

        for row in human_rows:

            scores = row.get("scores") or {}
            judge = judge_by_question.get(row.get("question")) or {}

            human_scores.append(scores.get(dimension))
            judge_scores.append(judge.get(dimension))

        per_dimension[dimension] = dimension_agreement(
            human_scores, judge_scores, threshold
        )

    return per_dimension


def _pairs(human_rows, judge_rows, dimension):
    """按 question 对齐，返回 [(index, question, human, judge)]（两侧都有效的才留）。"""

    judge_by_question: dict = {}

    for row in judge_rows:
        judge_by_question.setdefault(row.get("question"), row.get("judge"))

    pairs = []

    for row in human_rows:

        human = (row.get("scores") or {}).get(dimension)
        judge = (judge_by_question.get(row.get("question")) or {}).get(dimension)

        if human is None or judge is None:
            continue

        pairs.append((row.get("index"), row.get("question"), human, judge))

    return pairs


def bias_summary(human_rows, judge_rows, dimension) -> Optional[dict]:
    """裁判偏高还是偏低（人工 - 裁判为正 = 裁判给得比人高）。"""

    pairs = _pairs(human_rows, judge_rows, dimension)

    if not pairs:
        return None

    deltas = [human - judge for _, _, human, judge in pairs]

    return {
        "n": len(deltas),
        "mean_delta": round(sum(deltas) / len(deltas), 4),
        "judge_higher": sum(1 for delta in deltas if delta < 0),
        "human_higher": sum(1 for delta in deltas if delta > 0),
        "equal": sum(1 for delta in deltas if delta == 0),
    }


def disagreement_details(human_rows, judge_rows, dimension, min_delta: int = 1) -> list:
    """逐条列出某一维上人工与裁判的分歧（|分差| >= min_delta）。

    只给"没达标"是没用的，得知道错在哪几条、往哪个方向偏，才谈得上修裁判。
    """

    details = []

    for index, question, human, judge in _pairs(human_rows, judge_rows, dimension):

        delta = human - judge

        if abs(delta) < min_delta:
            continue

        details.append({
            "index": index,
            "question": question,
            "dimension": dimension,
            "human": human,
            "judge": judge,
            "delta": delta,
        })

    return sorted(details, key=lambda row: -abs(row["delta"]))


def evaluate_gate(
        per_dimension: dict,
        min_adjacent: float = 0.8,
        max_mae: float = 0.5,
) -> dict:
    """判定裁判是否可信到可以放行（用于 judge_calibrate.py 的退出码）。

    每个维度都要满足：相邻一致率 >= min_adjacent 且 MAE <= max_mae。
    任一维度不达标即整体不通过——裁判分数不可直接采用。
    """

    failures = []
    compared = 0

    for dimension in DIMENSIONS:

        stats = per_dimension.get(dimension)

        if not stats:
            failures.append(f"{dimension}: 无可比样本")
            continue

        compared += stats["n"]

        if stats["adjacent"] < min_adjacent:
            failures.append(
                f"{dimension}: 相邻一致率 {stats['adjacent']} < {min_adjacent}"
            )

        if stats["mae"] > max_mae:
            failures.append(f"{dimension}: MAE {stats['mae']} > {max_mae}")

    return {
        "passed": not failures,
        "failures": failures,
        "compared": compared,
    }
