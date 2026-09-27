# -*- coding: utf-8 -*-
"""
生成质量评测的 IO 层：与运行中的应用、本地 Ollama 裁判通信。

与 evaluation/evaluate.py 共用同一套检索接口口径（同一个 /api/knowledge/rerank-test、
同一套 Document 字段解析），避免出现"两套算法、两套字段"的分叉。

为什么裁判要自己再取一次上下文：
    /api/chat 的问答轨迹（qa_trace.hits）只落了来源与章节、**没有落正文**
    （见 RagChatService.buildRetrievalSnapshot → describe()，只存 source/section/
    page_number/document_id）。裁判判 faithfulness 必须看到正文，所以这里用
    与主链路完全相同的问题与 (candidateK, rerankTopK) 复现一次检索；
    检索是确定性的，复现结果与生成时送入模型的片段一致。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_JUDGE_MODEL = "qwen2.5:7b-instruct"

JUDGE_SYSTEM_PROMPT = "你是严格、客观的 RAG 质量评审员，只输出要求的 JSON，不输出多余文字。"


def _get_json(url: str, timeout: int = 600):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _as_list(payload) -> list:
    """兼容接口返回：直接数组 / {"results": [...]} / {"data": [...]}（同 evaluate.py）。"""

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("results", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]

    return []


def _document_content(document: dict) -> str:
    """取 Spring AI Document 的正文。

    实测（spring-ai-commons 2.0.0）Document.getText() 上的 JSON 字段是 content，
    这里再兜底 text / page_content，避免版本差异导致裁判拿不到正文。
    """

    for key in ("content", "text", "page_content"):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return ""


def fetch_answer(
        base_url: str,
        question: str,
        session_id: Optional[str] = None,
        timeout: int = 600,
) -> dict:
    """调 /api/chat 拿回答与检索现场。不带 sessionId 即单轮，避免记忆干扰评测。"""

    params = {"question": question}

    if session_id:
        params["sessionId"] = session_id

    url = f"{base_url.rstrip('/')}/api/chat?" + urllib.parse.urlencode(params)

    return _get_json(url, timeout=timeout)


def policy_of(
        answer_body: dict,
        default_candidate_k: int = 5,
        default_rerank_top_k: int = 3,
) -> tuple:
    """从 /api/chat 返回里取本次生效的 (候选数, 精排数)，缺省回落到默认策略。"""

    policy = answer_body.get("policy") or {}

    candidate_k = policy.get("top_k") or default_candidate_k
    rerank_top_k = policy.get("rerank_top_k") or default_rerank_top_k

    return int(candidate_k), int(rerank_top_k)


def fetch_contexts(
        base_url: str,
        query: str,
        candidate_k: int,
        rerank_top_k: int,
        timeout: int = 180,
) -> list:
    """复现检索，取回进入上下文的片段（正文 + 来源 + 章节）。"""

    params = {
        "query": query,
        "candidateK": candidate_k,
        "rerankTopK": rerank_top_k,
    }

    url = f"{base_url.rstrip('/')}/api/knowledge/rerank-test?" + urllib.parse.urlencode(params)

    documents = _as_list(_get_json(url, timeout=timeout))

    contexts = []

    for document in documents:

        metadata = document.get("metadata") or {}

        contexts.append({
            "source": metadata.get("source"),
            "section": metadata.get("section"),
            "page_number": metadata.get("page_number"),
            "reranker_score": metadata.get("reranker_score"),
            "content": _document_content(document),
        })

    return contexts


def ollama_judge(
        prompt: str,
        model: str = DEFAULT_JUDGE_MODEL,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        timeout: int = 600,
) -> str:
    """调用本地 Ollama 做裁判，返回原始文本（由 judge_core 负责解析）。

    用 format=json 约束输出；temperature=0 + 固定 seed 尽量保证可复算。
    """

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "seed": 42,
        },
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return (payload.get("message") or {}).get("content", "")
