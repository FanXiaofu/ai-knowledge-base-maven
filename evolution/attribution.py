# -*- coding: utf-8 -*-
"""
badcase 归因：把"用户说这条回答不对"定位到具体失败层。

只用确定性信号（问答轨迹里的检索现场 + 反馈字段），不引入 LLM 判断——
归因结论会决定"该改召回、改精排、改阈值还是改生成"，判错层就等于改错地方。

归因依赖三类证据：
1. 召回候选（精排前）里有没有金标文档；
2. 精排结果（进入上下文）里有没有金标文档；
3. 是否拒答 + 回答里的引用编号是否越界/缺失。

没有金标信息的负反馈不猜，进人工标注队列。
"""

import re

# 失败层定义（layer -> 人类可读说明）
LAYERS = {
    "ok": "正反馈，无需处理",
    "retrieval_miss": "召回未命中：候选集里就没有金标文档",
    "ranking_error": "精排/排序：金标进了候选但没进上下文",
    "threshold_error": "阈值误伤：金标在上下文里却仍被拒答（阈值偏高）",
    "generation_issue": "生成层：证据在上下文里，回答仍不符合预期",
    "citation_issue": "引用层：整篇无引用或引用编号越界",
    "refusal_needs_label": "疑似误拒：负反馈但未提供金标，需人工标注",
    "needs_label": "负反馈但未提供金标，需人工标注",
}

# 归因结论 -> 修复动作（写进报告，让"发现问题"直接对应"该做什么"）
ACTIONS = {
    "retrieval_miss": "补召回：检查切分粒度/混合检索权重，把该问题加入评测集",
    "ranking_error": "改精排：检查候选数 rerank_top_k 与精排模型，把该问题加入评测集",
    "threshold_error": "重标定阈值：该样本是边界样本，纳入阈值扫描",
    "generation_issue": "改生成：检查 prompt 约束与上下文组织方式",
    "citation_issue": "改引用：检查引用编号生成与越界校验",
    "refusal_needs_label": "人工标注期望来源后重新归因",
    "needs_label": "人工标注期望来源后重新归因",
    "ok": "无需动作",
}

_CITE_RE = re.compile(r"\[(\d{1,2}(?:\s*[,，]\s*\d{1,2})*)\]")


def citation_stats(answer: str, n_sources: int = 0) -> dict:
    """
    回答的引用统计（确定性）。

    与 deep-research 项目同款口径：支持 [2, 6] 这类复合引用，
    避免把复合引用误判成"无引用"。
    """
    body = (answer or "").split("参考来源")[0]
    cited = []
    for match in _CITE_RE.finditer(body):
        for part in re.split(r"[,，]\s*", match.group(1)):
            if part.strip().isdigit():
                cited.append(int(part.strip()))

    out_of_range = [n for n in cited if n < 1 or (n_sources and n > n_sources)]

    return {
        "n_citations": len(cited),
        "n_out_of_range": len(out_of_range),
        "citation_valid": bool(cited) and not out_of_range,
    }


def _sources(items) -> list:
    return [str(item.get("source") or "") for item in (items or [])]


def attribute(record: dict, boundary_margin: float = 0.05) -> dict:
    """
    对一条"轨迹 + 反馈"记录做归因。

    record 需要包含：
      question / refused / top1_score / threshold_used / answer
      hits: {"candidates": [...], "reranked": [...]}
      feedback: {"rating": "up|down", "expected_source": ..., "expected_section": ...}

    返回：{"layer", "action", "evidence", "boundary", "gold", "gold_in_candidates",
           "gold_in_context", "citation": {...}}
    """
    feedback = record.get("feedback") or {}
    rating = str(feedback.get("rating") or "").strip().lower()

    hits = record.get("hits") or {}
    candidates = _sources(hits.get("candidates"))
    context = _sources(hits.get("reranked"))

    gold = str(feedback.get("expected_source") or "").strip()

    citation = citation_stats(record.get("answer") or "", len(context))

    refused = bool(record.get("refused"))
    top1 = record.get("top1_score")
    threshold = record.get("threshold_used")

    boundary = (
        isinstance(top1, (int, float))
        and isinstance(threshold, (int, float))
        and abs(float(top1) - float(threshold)) <= boundary_margin
    )

    if rating == "up":
        layer = "ok"
        evidence = "用户确认回答可用"
    elif gold:
        if gold not in candidates:
            layer = "retrieval_miss"
            evidence = f"金标 {gold} 不在召回候选（{len(candidates)} 条）中"
        elif gold not in context:
            layer = "ranking_error"
            evidence = f"金标 {gold} 进了候选但没进上下文（上下文 {context}）"
        elif refused:
            layer = "threshold_error"
            evidence = f"金标 {gold} 在上下文里，Top1={top1} 低于阈值 {threshold} 被拒答"
        elif not citation["citation_valid"]:
            layer = "citation_issue"
            evidence = f"证据在上下文里，但引用异常（{citation}）"
        else:
            layer = "generation_issue"
            evidence = f"金标 {gold} 在上下文里，Top1={top1}，回答仍不合格"
    else:
        if refused:
            layer = "refusal_needs_label"
            evidence = f"用户认为不该拒答（Top1={top1}，阈值={threshold}，边界={boundary}）"
        elif not citation["citation_valid"]:
            layer = "citation_issue"
            evidence = f"未提供金标，但引用异常（{citation}）"
        else:
            layer = "needs_label"
            evidence = "未提供金标，无法定位失败层"

    return {
        "layer": layer,
        "action": ACTIONS.get(layer, ""),
        "evidence": evidence,
        "boundary": boundary,
        "gold": gold,
        "gold_in_candidates": gold in candidates if gold else None,
        "gold_in_context": gold in context if gold else None,
        "citation": citation,
    }


def build_case(record: dict, attribution: dict) -> dict:
    """
    由一条带金标的 badcase 生成评测用例（与 evaluation_questions.json 同结构）。

    金标不是猜出来的：只有用户显式给了 expected_source 才生成用例，
    否则进待标注队列（见 evolve.py）。
    """
    feedback = record.get("feedback") or {}

    case = {
        "query": record.get("question", ""),
        "relevant_source": attribution["gold"],
    }

    expected_section = str(feedback.get("expected_section") or "").strip()
    if expected_section:
        case["relevant_section"] = expected_section

    case["origin"] = {
        "trace_id": record.get("trace_id", ""),
        "layer": attribution["layer"],
        "rating": feedback.get("rating", ""),
        "created_at": record.get("created_at", ""),
        "comment": feedback.get("comment", ""),
    }

    return case


def recommend_threshold(records: list, thresholds=None, min_samples: int = 10) -> dict:
    """
    用线上反馈重新标定拒答阈值。

    只取两类语义明确的样本（其余排除，不硬凑）：
    - 应该回答：给了金标，且金标确实进了上下文（证据在，系统理应作答）；
    - 应该拒答：给了金标，但金标连候选集都没进（知识库里确实没有）。

    指标口径与 evaluation/evaluate.py 的阈值扫描一致（P/R/F1/FAR/FRR），
    选优规则同样为：F1 → FAR → FRR。
    """
    thresholds = thresholds or [round(0.50 + i * 0.05, 2) for i in range(9)]

    labeled = []

    for record in records:
        feedback = record.get("feedback") or {}
        gold = str(feedback.get("expected_source") or "").strip()
        if not gold:
            continue

        hits = record.get("hits") or {}
        candidates = _sources(hits.get("candidates"))
        context = _sources(hits.get("reranked"))
        score = record.get("top1_score")

        if not isinstance(score, (int, float)):
            continue

        if gold in context:
            should_accept = True
        elif gold not in candidates:
            should_accept = False
        else:
            continue  # 金标在候选但被挤出上下文：属于排序问题，不该用它调阈值

        labeled.append({"score": float(score), "should_accept": should_accept})

    sweep = []
    for threshold in thresholds:
        tp = fp = tn = fn = 0
        for item in labeled:
            accepted = item["score"] >= threshold
            if item["should_accept"]:
                tp += int(accepted)
                fn += int(not accepted)
            else:
                fp += int(accepted)
                tn += int(not accepted)

        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        far = fp / (fp + tn) if fp + tn else 0.0
        frr = fn / (tp + fn) if tp + fn else 0.0

        sweep.append({
            "threshold": threshold,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "far": round(far, 4),
            "frr": round(frr, 4),
        })

    best = max(sweep, key=lambda row: (row["f1"], -row["far"], -row["frr"])) if sweep else None

    return {
        "n_labeled": len(labeled),
        "n_records": len(records),
        "reliable": len(labeled) >= min_samples,
        "sweep": sweep,
        "recommended": best,
    }
