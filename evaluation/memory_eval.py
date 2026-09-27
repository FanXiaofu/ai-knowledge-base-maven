# -*- coding: utf-8 -*-
"""
会话记忆评测：同一条指代追问，"有记忆"与"无记忆"的检索命中对比。

    python evaluation/memory_eval.py --limit 4          # 先跑 4 条（每条 3 次真实问答调用）
    python evaluation/memory_eval.py --limit 8          # 全量 8 条

每个用例三次真实调用（不造假历史——只有真实链路才能同时验证"记忆写进去了、取出来了、改写用上了、检索受益了"）：

    1. 开场问题（不带会话）        → 建立指代对象，回答写入会话记忆
    2. 追问 + 会话（有记忆臂）      → 先做指代消解再检索，记录实际检索问题
    3. 同一追问、不带会话（无记忆臂）→ 按原问题检索

两次追问的检索现场从 /api/evolution/export 取回（轨迹里存了召回候选与精排结果），
据此判断金标文档是否进了候选/上下文。

指标口径：
    改写补全      改写后的问题里是否出现了具体实体（expect_rewrite_any 命中其一）
                  —— 这是"补出了实体"的最低检查，不是语义正确性判断；
                  报告同时打印改写前后对照，供人工核对（语义正确性机器判定不了）。
    召回命中      金标文档是否出现在召回候选里（检索层）
    上下文命中    金标文档是否进入了送进模型的片段（精排层，决定能不能答对）

成本提示：每条用例 3 次问答，本地 7B 模型约 30~70 秒/次，--limit 4 大约十几分钟。
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / "multiturn_questions.json"
REPORT = HERE / "memory_eval_report.md"

BASE_URL = "http://localhost:8080"


def http_get(url, timeout=600):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_delete(url, timeout=30):
    request = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ask(question, session_id=None):
    params = {"question": question}
    if session_id:
        params["sessionId"] = session_id
    url = f"{BASE_URL}/api/chat?" + urllib.parse.urlencode(params)
    return http_get(url)


def fetch_trace(trace_id):
    """从闭环导出接口取回某条轨迹（含检索现场）。"""
    url = f"{BASE_URL}/api/evolution/export?limit=200"
    payload = http_get(url, timeout=60)
    for trace in payload.get("traces") or []:
        if trace.get("trace_id") == trace_id:
            hits = trace.get("hits")
            if isinstance(hits, str):
                try:
                    hits = json.loads(hits)
                except json.JSONDecodeError:
                    hits = {}
            return hits or {}
    return {}


def sources_of(items):
    return [str(item.get("source") or "") for item in (items or [])]


def retrieval_facts(trace_id, gold_source):
    """返回这条轨迹的检索事实：候选命中 / 上下文命中。"""
    hits = fetch_trace(trace_id)
    candidates = sources_of(hits.get("candidates"))
    reranked = sources_of(hits.get("reranked"))
    return {
        "candidates": candidates,
        "reranked": reranked,
        "recall_hit": gold_source in candidates,
        "context_hit": gold_source in reranked,
        "retrieval_query": hits.get("retrieval_query"),
        "memory_turns": hits.get("memory_turns"),
    }


def rewrite_resolved(query, keywords):
    """改写是否补出了具体实体（命中任一关键词即可）。"""
    if not query:
        return False
    lowered = query.lower()
    return any(str(keyword).lower() in lowered for keyword in (keywords or []))


def run_case(case, index, total, keep_sessions=False):
    session_id = f"mem-eval-{case['id']}-{int(time.time())}"
    gold = case["followup_source"]
    row = {"id": case["id"], "note": case.get("note", ""), "followup": case["followup"], "gold": gold}

    print(f"[{index}/{total}] {case['id']} 开场：{case['opening'][:30]} ...", flush=True)
    opening = ask(case["opening"], session_id)
    row["opening_ok"] = not opening.get("refused")

    print(f"           有记忆追问：{case['followup']} ...", flush=True)
    with_memory = ask(case["followup"], session_id)
    row["with_refused"] = with_memory.get("refused")
    row["with_query"] = with_memory.get("retrieval_query")
    row["with_top1"] = with_memory.get("top1_score")
    row["rewritten"] = with_memory.get("rewritten")
    row["rewrite_ok"] = bool(with_memory.get("rewritten")) and rewrite_resolved(
        with_memory.get("retrieval_query"), case.get("expect_rewrite_any")
    )
    row.update({f"with_{k}": v for k, v in retrieval_facts(with_memory.get("trace_id"), gold).items()})

    print(f"           无记忆追问（同一问题，不带会话）...", flush=True)
    without_memory = ask(case["followup"], None)
    row["without_refused"] = without_memory.get("refused")
    row["without_top1"] = without_memory.get("top1_score")
    row.update({f"without_{k}": v for k, v in retrieval_facts(without_memory.get("trace_id"), gold).items()})

    if not keep_sessions:
        try:
            http_delete(f"{BASE_URL}/api/chat/session?" + urllib.parse.urlencode({"sessionId": session_id}))
        except Exception:
            pass

    return row


def summarize(rows):
    def rate(key):
        values = [1 if row.get(key) else 0 for row in rows]
        return round(sum(values) / len(values), 3) if values else None

    return {
        "cases": len(rows),
        "rewrite_ok": rate("rewrite_ok"),
        "memory_used": rate("with_memory_turns"),
        "with_recall": rate("with_recall_hit"),
        "with_context": rate("with_context_hit"),
        "without_recall": rate("without_recall_hit"),
        "without_context": rate("without_context_hit"),
        "with_refused": rate("with_refused"),
        "without_refused": rate("without_refused"),
    }


def render(rows, means):
    lines = [
        "# 会话记忆评测报告",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 用例：{means['cases']} 条（每条 3 次真实问答：开场 → 有记忆追问 → 无记忆追问）",
        "- 口径：召回命中=金标进候选；上下文命中=金标进精排后送进模型的片段",
        "",
        "## 汇总",
        "",
        "| 指标 | 有记忆 | 无记忆 |",
        "|---|---|---|",
        f"| 召回命中率 | {means['with_recall']} | {means['without_recall']} |",
        f"| 上下文命中率 | {means['with_context']} | {means['without_context']} |",
        f"| 拒答率 | {means['with_refused']} | {means['without_refused']} |",
        "",
        f"指代改写补出实体比例：{means['rewrite_ok']}",
        f"检索时确实带上了历史（memory_turns > 0）的比例：{means['memory_used']}",
        "",
        "## 逐题明细",
        "",
        "| 题目 | 追问 | 改写后（实际检索） | 有记忆 召回/上下文 | 无记忆 召回/上下文 |",
        "|---|---|---|---|---|",
    ]

    for row in rows:
        lines.append(
            f"| {row['id']} | {row['followup']} | {row.get('with_query') or '-'} "
            f"| {'✓' if row.get('with_recall_hit') else '✗'} / {'✓' if row.get('with_context_hit') else '✗'} "
            f"| {'✓' if row.get('without_recall_hit') else '✗'} / {'✓' if row.get('without_context_hit') else '✗'} |"
        )

    lines += [
        "",
        "## 改写前后对照（供人工核对语义正确性）",
        "",
        "> 脚本只做「是否补出具体实体」的确定性检查；改写是否真的解析对了指代，需要人看下面的对照。",
        "",
        "| 原追问 | 改写后 |",
        "|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['followup']} | {row.get('with_query') or '-'} |")

    lines += [
        "",
        "> 无记忆臂就是引入会话记忆之前的行为：追问里的指代没有被补全，检索只能靠原句碰运气。",
        "> 若两臂差异不明显，多半是指代词恰好也是强关键词（例如追问里本来就有 Redis），此时该用例区分度低。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="会话记忆评测（有记忆 vs 无记忆）")
    parser.add_argument("--limit", type=int, default=4, help="用例条数（默认 4，全量 8）")
    parser.add_argument("--keep-sessions", action="store_true", help="保留评测用的会话记忆（默认跑完清空）")
    parser.add_argument("--report", default=str(REPORT), help="报告输出路径")
    args = parser.parse_args()

    cases = json.loads(DATASET.read_text(encoding="utf-8"))[: args.limit]

    print(f"== 会话记忆评测：{len(cases)} 条用例 × 3 次问答调用 ==", flush=True)

    rows = []
    for index, case in enumerate(cases, start=1):
        try:
            rows.append(run_case(case, index, len(cases), args.keep_sessions))
        except Exception as exc:
            print(f"   ✗ 失败：{type(exc).__name__}: {exc}", flush=True)
            rows.append({"id": case["id"], "followup": case["followup"], "error": str(exc)})

    usable = [row for row in rows if not row.get("error")]
    if not usable:
        print("[错误] 没有可用的用例结果（应用是否在运行？）")
        return 2

    means = summarize(usable)

    print()
    header = f"{'题目':<8}{'改写补全':<10}{'有记忆(召回/上下文)':<22}{'无记忆(召回/上下文)':<22}"
    print(header)
    print("-" * len(header))
    for row in usable:
        print(
            f"{row['id']:<8}{str(row.get('rewrite_ok')):<10}"
            f"{('✓' if row.get('with_recall_hit') else '✗') + ' / ' + ('✓' if row.get('with_context_hit') else '✗'):<22}"
            f"{('✓' if row.get('without_recall_hit') else '✗') + ' / ' + ('✓' if row.get('without_context_hit') else '✗'):<22}"
        )

    print()
    print(f"召回命中率：有记忆 {means['with_recall']} vs 无记忆 {means['without_recall']}")
    print(f"上下文命中率：有记忆 {means['with_context']} vs 无记忆 {means['without_context']}")
    print(f"指代改写补出实体比例：{means['rewrite_ok']}")

    report_path = Path(args.report)
    report_path.write_text(render(usable, means), encoding="utf-8")
    print(f"\n报告：{report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
