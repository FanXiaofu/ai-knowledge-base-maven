# -*- coding: utf-8 -*-
"""
在当前语料上重测「BM25 分词改造」的前后对比。

背景：简历里写的「章节首位命中率 71.9% → 80.2%」是早期 27 份文档语料上
测出来的。语料扩到 172 份后需要重新测一组，本脚本负责测「改造前」
（单字切分）那一端。

做法：直接从数据库导出全部 chunk，用 Python 复现旧版 Bm25Service 的
分词规则（正则单字切分）与打分公式，对验证集里的章节标注题做排序，
统计章节首位命中率。改造后的数字取自 evaluation_results.json 的 BM25 一行。

用法：
    python evaluation/tokenizer_compare_current.py
"""

import csv
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent

K1 = 1.5
B = 0.75

# 旧版 Bm25Service 使用的分词规则
OLD_TOKEN_PATTERN = re.compile(
    r"[a-zA-Z][a-zA-Z0-9+#.-]*|[0-9]+|[\u4e00-\u9fff]"
)


def dump_chunks() -> list[dict]:
    """从 PostgreSQL 导出所有 chunk（CSV 能正确处理换行与引号）。"""
    sql = (
        "\\copy (SELECT id, content, "
        "metadata->>'section' AS section, metadata->>'source' AS source "
        "FROM vector_store WHERE content IS NOT NULL) "
        "TO STDOUT WITH (FORMAT csv, HEADER)"
    )
    out = subprocess.run(
        ["docker", "exec", "-i", "ai-knowledge-postgres",
         "psql", "-U", "ai_user", "-d", "ai_knowledge", "-c", sql],
        capture_output=True, check=True,
    )
    text = out.stdout.decode("utf-8", errors="replace")
    return list(csv.DictReader(text.splitlines()))


def tokenize_old(text: str) -> list[str]:
    """旧版：中文按单字切分。"""
    return OLD_TOKEN_PATTERN.findall((text or "").lower())


def main():
    print("导出语料 ...")
    chunks = dump_chunks()
    print(f"共 {len(chunks)} 个 chunk")

    # 预计算
    doc_tokens = []
    doc_len = []
    for c in chunks:
        toks = tokenize_old(c["content"])
        doc_tokens.append(Counter(toks))
        doc_len.append(len(toks))

    n = len(chunks)
    avg_len = sum(doc_len) / n if n else 0

    df = Counter()
    for tf in doc_tokens:
        df.update(tf.keys())

    dataset = json.load(open(HERE / "evaluation_questions.json", encoding="utf-8"))
    queries = []
    for item in dataset:
        secs = set()
        if item.get("relevant_sections"):
            secs = set(item["relevant_sections"])
        elif item.get("relevant_section"):
            secs = {item["relevant_section"]}
        if secs and item.get("relevant_source"):
            queries.append((item["query"], secs))

    print(f"带章节标注的题目：{len(queries)} 条")
    print()

    hit1 = hit3 = 0

    for query, gold_sections in queries:
        q_tokens = tokenize_old(query)

        scores = [0.0] * n
        for i in range(n):
            tf = doc_tokens[i]
            length = doc_len[i]
            if length == 0:
                continue
            score = 0.0
            # 旧实现按查询词逐个累加（重复词会累加多次），这里保持一致
            for qt in q_tokens:
                f = tf.get(qt, 0)
                if f == 0:
                    continue
                d = df.get(qt, 0)
                idf = math.log(1.0 + (n - d + 0.5) / (d + 0.5))
                score += idf * (f * (K1 + 1)) / (
                    f + K1 * (1 - B + B * length / avg_len)
                )
            scores[i] = score

        order = sorted(range(n), key=lambda i: scores[i], reverse=True)[:3]
        secs = [(chunks[i]["section"] or "") for i in order]

        if secs and secs[0] in gold_sections:
            hit1 += 1
        if any(s in gold_sections for s in secs):
            hit3 += 1

    total = len(queries)
    print("=" * 60)
    print("  在当前语料（%d chunk）上的 BM25 章节级指标" % n)
    print("=" * 60)
    print(f"  改造前（单字切分）  R@1 = {hit1 / total:.4f}   R@3 = {hit3 / total:.4f}")

    # 改造后的数字来自完整评测
    results_path = HERE / "evaluation_results.json"
    if results_path.exists():
        results = json.load(open(results_path, encoding="utf-8"))
        vals = [r["section"] for r in results.get("BM25", []) if r.get("section")]
        if vals:
            r1 = sum(v["recall@1"] for v in vals) / len(vals)
            r3 = sum(v["recall@3"] for v in vals) / len(vals)
            print(f"  改造后（HanLP）    R@1 = {r1:.4f}   R@3 = {r3:.4f}"
                  f"   （取自 evaluation_results.json，n={len(vals)}）")
            print()
            print(f"  结论：章节首位命中率 {hit1 / total:.1%} → {r1:.1%}"
                  f"（{(r1 - hit1 / total) * 100:+.1f}pp）")


if __name__ == "__main__":
    sys.exit(main())
