# -*- coding: utf-8 -*-
"""
自进化闭环第 1 步：badcase 归因 → 评测集生长。

    qa_trace + qa_feedback ──► 归因（attribution.py）──► 带金标的用例进评测集
                                                    └──► 无金标的进人工标注队列

数据来源二选一：
    python evolution/evolve.py --api http://localhost:8080 --limit 500   # 从运行中的应用导出
    python evolution/evolve.py --export evolution/data/export.json       # 用已导出的 JSON（可离线）

默认 **dry-run**，只打印归因分布与将要新增的用例；加 --write 才写回
evaluation/evolved_cases.json、evaluation/pending_labels.json、evaluation/evolution_report.md。
评测集是评测口径的根，不允许被脚本悄悄改动。
"""

import argparse
import json
import sys
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from attribution import ACTIONS, LAYERS, attribute, build_case, recommend_threshold

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_DIR = ROOT / "evaluation"


def paths(eval_dir: Path) -> dict:
    """评测集相关文件的路径（--eval-dir 可重定向，便于沙箱试跑）。"""
    return {
        "base": eval_dir / "evaluation_questions.json",
        "evolved": eval_dir / "evolved_cases.json",
        "pending": eval_dir / "pending_labels.json",
        "report": eval_dir / "evolution_report.md",
    }


def load_export(path: str | None, api: str | None, limit: int) -> dict:
    if path:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    url = f"{api.rstrip('/')}/api/evolution/export?limit={limit}"
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_hits(value) -> dict:
    """hits 字段可能是 JSON 字符串（数据库导出）或已解析的对象。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def merge_records(export: dict) -> list:
    """按 trace_id 合并轨迹与反馈（同一轨迹多条反馈时取最新一条）。"""
    traces = export.get("traces") or []
    feedback_rows = export.get("feedback") or []

    latest = {}
    for row in feedback_rows:
        trace_id = row.get("trace_id")
        if not trace_id:
            continue
        current = latest.get(trace_id)
        if current is None or int(row.get("id") or 0) >= int(current.get("id") or 0):
            latest[trace_id] = row

    records = []
    for trace in traces:
        trace_id = trace.get("trace_id")
        record = dict(trace)
        record["hits"] = parse_hits(trace.get("hits"))
        record["feedback"] = latest.get(trace_id)
        records.append(record)

    return records


def analyze(records: list) -> dict:
    """归因所有带反馈的记录，产出用例与待标注队列。"""
    analyzed = []
    cases = []
    pending = []
    layer_counter = Counter()

    for record in records:
        if not record.get("feedback"):
            continue

        result = attribute(record)
        layer_counter[result["layer"]] += 1

        row = {
            "trace_id": record.get("trace_id"),
            "question": record.get("question"),
            "rating": (record.get("feedback") or {}).get("rating"),
            "refused": record.get("refused"),
            "top1_score": record.get("top1_score"),
            "threshold_used": record.get("threshold_used"),
            "layer": result["layer"],
            "action": result["action"],
            "evidence": result["evidence"],
            "boundary": result["boundary"],
            "created_at": record.get("created_at"),
        }
        analyzed.append(row)

        if result["layer"] == "ok":
            continue

        if result["gold"]:
            cases.append(build_case(record, result))
        else:
            pending.append({
                "trace_id": record.get("trace_id"),
                "question": record.get("question"),
                "refused": record.get("refused"),
                "top1_score": record.get("top1_score"),
                "threshold_used": record.get("threshold_used"),
                "suspect_layer": result["layer"],
                "evidence": result["evidence"],
                "need": "请人工填写 expected_source（可附 expected_section）后重新运行 evolve.py",
            })

    return {
        "analyzed": analyzed,
        "cases": cases,
        "pending": pending,
        "layer_counter": layer_counter,
        "threshold": recommend_threshold(records),
    }


def existing_queries(eval_dir: Path) -> tuple:
    base_path = paths(eval_dir)["base"]
    evolved_path = paths(eval_dir)["evolved"]

    base = json.loads(base_path.read_text(encoding="utf-8")) if base_path.exists() else []
    evolved = json.loads(evolved_path.read_text(encoding="utf-8")) if evolved_path.exists() else []

    return {item.get("query", "").strip() for item in base}, evolved


def dedupe_cases(cases: list, eval_dir: Path | None = None) -> tuple:
    """去重：与基础评测集重复的、本轮内部重复的都只保留一次。"""
    eval_dir = eval_dir or DEFAULT_EVAL_DIR
    base_queries, evolved = existing_queries(eval_dir)
    evolved_queries = {item.get("query", "").strip() for item in evolved}

    fresh, duplicated = [], []

    for case in cases:
        query = case["query"].strip()
        if query in base_queries or query in evolved_queries:
            duplicated.append(case)
            continue
        evolved_queries.add(query)
        fresh.append(case)

    return fresh, duplicated, evolved


def write_outputs(fresh: list, pending: list, evolved: list, analysis: dict,
                  eval_dir: Path | None = None) -> dict:
    eval_dir = eval_dir or DEFAULT_EVAL_DIR
    eval_dir.mkdir(parents=True, exist_ok=True)
    targets = paths(eval_dir)

    merged = evolved + fresh
    targets["evolved"].write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    targets["pending"].write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    targets["report"].write_text(
        render_report(analysis, fresh, pending, len(merged)), encoding="utf-8"
    )

    return {
        "evolved_total": len(merged),
        "pending_total": len(pending),
        "evolved_path": targets["evolved"],
        "pending_path": targets["pending"],
        "report_path": targets["report"],
    }


def render_report(analysis: dict, fresh: list, pending: list, evolved_total: int) -> str:
    layer_counter = analysis["layer_counter"]
    threshold = analysis["threshold"]

    lines = [
        "# 自进化闭环报告（badcase 归因 → 评测集生长）",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 带反馈的轨迹：{len(analysis['analyzed'])} 条（其中负反馈 {sum(v for k, v in layer_counter.items() if k != 'ok')} 条）",
        f"- 评测集累计新增用例：{evolved_total} 条（本轮新增 {len(fresh)} 条）",
        f"- 待人工标注：{len(pending)} 条",
        "",
        "## 失败层分布",
        "",
        "| 失败层 | 条数 | 说明 | 对应动作 |",
        "|---|---|---|---|",
    ]

    for layer, count in layer_counter.most_common():
        lines.append(
            f"| {layer} | {count} | {LAYERS.get(layer, '')} | {ACTIONS.get(layer, '')} |"
        )

    lines += [
        "",
        "## 阈值重标定（线上反馈口径）",
        "",
        f"- 可用于标定的样本：{threshold['n_labeled']} / {threshold['n_records']} 条"
        f"（{'样本量足够' if threshold['reliable'] else '样本量偏少，仅作参考，勿直接改线上阈值'}）",
        "- 口径：给了金标且金标进了上下文 → 应该作答；给了金标但连候选都没进 → 应该拒答；其余样本排除",
        "",
    ]

    if threshold["recommended"]:
        best = threshold["recommended"]
        lines += [
            "| 阈值 | Precision | Recall | F1 | FAR | FRR | TP/FP/TN/FN |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in threshold["sweep"]:
            mark = " ←推荐" if row["threshold"] == best["threshold"] else ""
            lines.append(
                f"| {row['threshold']}{mark} | {row['precision']} | {row['recall']} | {row['f1']} "
                f"| {row['far']} | {row['frr']} | {row['tp']}/{row['fp']}/{row['tn']}/{row['fn']} |"
            )
        lines += [
            "",
            f"推荐阈值：**{best['threshold']}**（F1={best['f1']}、FAR={best['far']}）",
            "生效方式：运行 `python evolution/auto_tune.py --write` 在标注验证集上复算并写入策略文件，",
            "或直接调用 `POST /api/chat/policy/reload` 重载。",
        ]

    if fresh:
        lines += ["", "## 本轮新增用例", "", "| 问题 | 金标来源 | 失败层 |", "|---|---|---|"]
        for case in fresh:
            lines.append(
                f"| {case['query']} | {case['relevant_source']} | {case['origin']['layer']} |"
            )

    if pending:
        lines += ["", "## 待人工标注", "", "| 问题 | 疑似失败层 | 证据 |", "|---|---|---|"]
        for row in pending:
            lines.append(f"| {row['question']} | {row['suspect_layer']} | {row['evidence']} |")

    lines += [
        "",
        "> 只有带金标的负反馈才会自动转成评测用例；没有金标的进待标注队列。",
        "> 评测集是口径的根，脚本不猜标签。",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="badcase 归因与评测集生长")
    parser.add_argument("--api", help="从运行中的应用导出（如 http://localhost:8080）")
    parser.add_argument("--export", help="使用已导出的 JSON 文件")
    parser.add_argument("--limit", type=int, default=500, help="导出/读取的轨迹条数上限")
    parser.add_argument("--eval-dir", default=str(DEFAULT_EVAL_DIR),
                        help="评测集所在目录（默认 evaluation/，可指向沙箱目录试跑）")
    parser.add_argument("--write", action="store_true", help="写回评测集与报告（默认只打印）")
    args = parser.parse_args()

    if not args.api and not args.export:
        parser.error("需要 --api 或 --export 之一")

    eval_dir = Path(args.eval_dir)

    export = load_export(args.export, args.api, args.limit)
    records = merge_records(export)
    analysis = analyze(records)
    fresh, duplicated, evolved = dedupe_cases(analysis["cases"], eval_dir)

    print(f"轨迹 {len(records)} 条，带反馈 {len(analysis['analyzed'])} 条")
    print("\n失败层分布：")
    for layer, count in analysis["layer_counter"].most_common():
        print(f"  {count:>3}  {layer:<22} {LAYERS.get(layer, '')}")

    print(f"\n可自动转用例（带金标）：{len(analysis['cases'])} 条"
          f"；去重后新增 {len(fresh)} 条（与评测集重复 {len(duplicated)} 条）")
    print(f"待人工标注：{len(analysis['pending'])} 条")

    threshold = analysis["threshold"]
    print(
        f"\n阈值标定样本：{threshold['n_labeled']} 条"
        f"（{'可用' if threshold['reliable'] else '偏少，仅供参考'}）"
    )
    if threshold["recommended"]:
        best = threshold["recommended"]
        print(
            f"  推荐阈值 {best['threshold']}：P={best['precision']} R={best['recall']} "
            f"F1={best['f1']} FAR={best['far']}"
        )

    if fresh:
        print("\n本轮新增用例预览：")
        for case in fresh[:10]:
            print(f"  - {case['query'][:40]:<42} 金标={case['relevant_source']} "
                  f"层={case['origin']['layer']}")

    if args.write:
        result = write_outputs(fresh, analysis["pending"], evolved, analysis, eval_dir)
        print(
            f"\n已写入：{result['evolved_path']}（累计 {result['evolved_total']} 条）、"
            f"{result['pending_path']}（{result['pending_total']} 条）、"
            f"{result['report_path']}"
        )
    else:
        print("\n（dry-run：加 --write 才会写回评测集与报告）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
