# -*- coding: utf-8 -*-
"""
BM25 分词改造前后对比评估。

只跑 BM25 和 Hybrid 两种方法（受分词影响的检索层），
与基线（单字切分时代的 evaluation_results.json）对比
Source / Section 两级指标。
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://localhost:8080/api/knowledge"
DATASET = Path(__file__).parent / "evaluation_questions.json"
BASELINE = Path(__file__).parent / "evaluation_results.json"


def request_json(endpoint, params, timeout=120):
    url = f"{BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_source(result):
    return result.get("metadata", {}).get("source")


def get_section(result):
    return result.get("metadata", {}).get("section")


def evaluate(records, method_name, endpoint):
    for idx, item in enumerate(dataset, start=1):
        expected_source = item.get("relevant_source")
        if item.get("relevant_sections"):
            sections = set(item["relevant_sections"])
        elif item.get("relevant_section"):
            sections = {item["relevant_section"]}
        else:
            sections = set()

        try:
            results = request_json(endpoint, {
                "query": item["query"],
                "topK": 5,
            })

            sources = [get_source(r) for r in results]
            section_values = [get_section(r) for r in results]

            rec = {"query": item["query"]}

            if expected_source:
                hits = [s == expected_source for s in sources]
                rec["source"] = {
                    "recall@1": 1 if hits and hits[0] else 0,
                    "recall@3": 1 if any(hits[:3]) else 0,
                }
            else:
                rec["source"] = None

            if sections:
                shits = [s in sections for s in section_values]
                rec["section"] = {
                    "recall@1": 1 if shits and shits[0] else 0,
                    "recall@3": 1 if any(shits[:3]) else 0,
                }
            else:
                rec["section"] = None

            records.append(rec)

        except Exception as e:
            records.append({"query": item["query"], "source": None, "section": None, "error": str(e)})

        if idx % 40 == 0:
            print(f"  {method_name} {idx}/{len(dataset)}")


def agg(records, key):
    vals = [r[key] for r in records if r.get(key)]
    if not vals:
        return None
    n = len(vals)
    return {
        "count": n,
        "R@1": sum(v["recall@1"] for v in vals) / n,
        "R@3": sum(v["recall@3"] for v in vals) / n,
    }


def main():
    global dataset
    dataset = json.load(open(DATASET, encoding="utf-8"))
    baseline = json.load(open(BASELINE, encoding="utf-8"))

    new_results = {}

    for name, endpoint in [("BM25", "bm25-search"), ("Hybrid", "hybrid-search")]:
        print(f"评估 {name} ...")
        t0 = time.time()
        records = []
        evaluate(records, name, endpoint)
        print(f"  {name} 完成，耗时 {time.time() - t0:.0f}s")
        new_results[name] = records

    print()
    print(f"{'方法':<10}{'指标':<10}{'改造前':>10}{'改造后':>10}{'变化':>10}")
    print("-" * 52)

    for name in ["BM25", "Hybrid"]:
        for key, label in [("source", "Source"), ("section", "Section")]:
            before = agg(baseline[name], key)
            after = agg(new_results[name], key)
            for metric in ["R@1", "R@3"]:
                b, a = before[metric], after[metric]
                mark = " ↑" if a > b else (" ↓" if a < b else " =")
                print(f"{name:<10}{label} {metric:<5}{b:>10.4f}{a:>10.4f}{mark:>8}")

    print()
    print("分组（原60题 / 新增74题）Section R@1：")
    for name in ["BM25", "Hybrid"]:
        old = agg(new_results[name][:60], "section")
        new = agg(new_results[name][60:], "section")
        base_old = agg(baseline[name][:60], "section")
        base_new = agg(baseline[name][60:], "section")
        print(f"  {name}: 原60题 {base_old['R@1']:.4f} -> {old['R@1']:.4f}   新增74题 {base_new['R@1']:.4f} -> {new['R@1']:.4f}")


if __name__ == "__main__":
    main()
