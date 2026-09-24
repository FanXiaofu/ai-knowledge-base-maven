# -*- coding: utf-8 -*-
"""
验证集标签健全性检查：

对每条 In-KB 题目调用 /api/knowledge/hybrid-search（topK=5），
检查金标 source 是否出现在 Top5，输出未命中的题目。
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://localhost:8080/api/knowledge/hybrid-search"
DATASET = Path(__file__).parent / "evaluation_questions.json"


def hybrid_search(query, top_k=5):
    url = BASE + "?" + urllib.parse.urlencode({"query": query, "topK": top_k})
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    data = json.load(open(DATASET, encoding="utf-8"))
    in_kb = [i for i in data if i.get("relevant_source")]

    misses = []

    for idx, item in enumerate(in_kb, start=1):
        try:
            results = hybrid_search(item["query"])
        except Exception as e:
            misses.append((idx, item["query"], item["relevant_source"], f"请求失败: {e}"))
            continue

        sources = [
            r.get("metadata", {}).get("source")
            for r in results
        ]

        if item["relevant_source"] not in sources:
            misses.append((idx, item["query"], item["relevant_source"], f"Top5={sources[:3]}"))

        if idx % 20 == 0:
            print(f"已检查 {idx}/{len(in_kb)} ...")

    print()
    print(f"共 {len(in_kb)} 条 In-KB，Top5 命中 {len(in_kb) - len(misses)} 条")

    if misses:
        print(f"\n未命中 {len(misses)} 条：")
        for idx, query, gold, detail in misses:
            print(f"  [{idx}] {query}  金标={gold}  {detail}")
    else:
        print("全部命中，标签无问题。")


if __name__ == "__main__":
    main()
