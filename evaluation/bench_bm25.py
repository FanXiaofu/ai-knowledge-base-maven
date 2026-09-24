# -*- coding: utf-8 -*-
"""
BM25 检索性能基准测试。

对同一批查询测量 /bm25-search 与 /hybrid-search 的响应延迟，
用于对比「全表扫描」与「内存倒排索引」两种实现。

用法：python evaluation/bench_bm25.py [查询条数]
"""

import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://localhost:8080/api/knowledge"
DATASET = Path(__file__).parent / "evaluation_questions.json"


def timed_get(endpoint, params, timeout=120):
    url = f"{BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    start = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        resp.read()
    return (time.perf_counter() - start) * 1000


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    data = json.load(open(DATASET, encoding="utf-8"))
    queries = [item["query"] for item in data[:limit]]

    print("=" * 66)
    print(f"  BM25 性能基准（{len(queries)} 条查询）")
    print("=" * 66)
    print()

    results = {}

    for endpoint in ["bm25-search", "hybrid-search"]:
        # 预热一次，避免首查询的分类器初始化影响结果
        timed_get(endpoint, {"query": queries[0], "topK": 5})

        latencies = [
            timed_get(endpoint, {"query": q, "topK": 5})
            for q in queries
        ]

        results[endpoint] = latencies

        latencies_sorted = sorted(latencies)

        print(f"{endpoint}")
        print(f"   平均   : {statistics.mean(latencies):>8.1f} ms")
        print(f"   中位数 : {statistics.median(latencies):>8.1f} ms")
        print(f"   最小   : {latencies_sorted[0]:>8.1f} ms")
        print(f"   最大   : {latencies_sorted[-1]:>8.1f} ms")
        print(f"   P95    : {latencies_sorted[int(len(latencies_sorted) * 0.95) - 1]:>8.1f} ms")
        print()

    out = Path(__file__).parent / "bm25_benchmark.json"
    out.write_text(
        json.dumps(
            {k: {"avg_ms": statistics.mean(v),
                 "median_ms": statistics.median(v),
                 "min_ms": min(v), "max_ms": max(v)}
             for k, v in results.items()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"结果已写入：{out}")


if __name__ == "__main__":
    main()
