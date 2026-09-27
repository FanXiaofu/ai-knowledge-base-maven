# -*- coding: utf-8 -*-
"""
AI 知识库问答 - 交互式提问脚本

直接运行 提问.bat 即可，或手动执行：python 提问.py

特性：
- 支持直接输入中文提问（自动按 UTF-8 编码请求，规避 Windows 控制台 GBK 编码问题）
- 连续提问，无需反复运行
- 显示每次问答耗时
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://localhost:8080"
CHAT_API = BASE_URL + "/api/chat"
CHAT_SESSION_API = BASE_URL + "/api/chat/session"
SEARCH_API = BASE_URL + "/api/knowledge/hybrid-search"
FEEDBACK_API = BASE_URL + "/api/feedback"
HEALTH_API = BASE_URL + "/actuator/health"

EXIT_WORDS = {"q", "quit", "exit", "退出", "结束"}
NEW_SESSION_WORDS = {"新会话", "新对话", "new"}
CLEAR_SESSION_WORDS = {"清空会话", "清空记忆", "clear"}
SESSION_INFO_WORDS = {"会话", "记忆", "session"}


def http_get(url, timeout=300):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def http_post_json(url, payload, timeout=30):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_delete(url, timeout=30):
    request = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_service():
    """启动前检查应用是否在运行。"""
    try:
        http_get(HEALTH_API, timeout=5)
        return True
    except Exception:
        return False


def new_session_id():
    return "ask-" + time.strftime("%Y%m%d-%H%M%S")


def ask(question, session_id=None):
    """向 /api/chat 提问，返回结构化结果（含答案、是否拒答、trace_id、实际检索问题）。"""
    params = {"question": question}
    if session_id:
        params["sessionId"] = session_id
    url = CHAT_API + "?" + urllib.parse.urlencode(params)
    return json.loads(http_get(url))


def session_info(session_id):
    return json.loads(http_get(CHAT_SESSION_API + "?" + urllib.parse.urlencode({"sessionId": session_id})))


def clear_session(session_id):
    return http_delete(CHAT_SESSION_API + "?" + urllib.parse.urlencode({"sessionId": session_id}))


def send_feedback(trace_id, rating, expected_source="", comment=""):
    """提交反馈：负反馈会进入 badcase 归因 → 评测集生长 → 回归门禁的闭环。"""
    return http_post_json(FEEDBACK_API, {
        "trace_id": trace_id,
        "rating": rating,
        "expected_source": expected_source,
        "comment": comment,
    })


def search(keyword, top_k=3):
    """只做检索，不生成回答，便于快速查看召回了哪些片段。"""
    url = SEARCH_API + "?" + urllib.parse.urlencode({
        "query": keyword,
        "topK": top_k,
    })

    docs = json.loads(http_get(url, timeout=60))

    lines = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.get("metadata", {})
        src = meta.get("source", "未知")
        section = meta.get("section") or ""
        page = meta.get("page_number")
        where = f"{src}"
        if page:
            where += f" — 第{page}页"
        if section:
            where += f" — {section}"
        lines.append(f"  [{i}] {where}")
    return "\n".join(lines) if lines else "  （无结果）"


def main():
    print("=" * 60)
    print("  AI 知识库问答")
    print("=" * 60)
    print()

    if not check_service():
        print("  [错误] 应用未运行（无法连接 http://localhost:8080）")
        print("  请先双击项目目录下的 启动.bat 启动服务。")
        print()
        return 1

    print("  服务正常。输入问题后回车即可提问。")
    print("  带会话记忆：同一会话里的追问会先补全指代（\"它\"→上一轮的话题）再检索。")
    print("  输入 检索:关键词  可只查看召回片段（更快，不调用大模型）")
    print("  输入 赞  /  踩 [期望文档名]  对上一次回答提交反馈（负反馈进入 badcase 归因）")
    print("  输入 会话 / 新会话 / 清空会话  查看、切换、清空会话记忆")
    print("  输入 q 或 退出  结束")
    print()
    print("-" * 60)

    last = None  # 上一次问答结果，供反馈引用 trace_id
    session_id = new_session_id()
    print(f"  当前会话：{session_id}")

    while True:
        try:
            question = input("\n请输入问题 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return 0

        if not question:
            continue

        if question.lower() in EXIT_WORDS:
            print("已退出。")
            return 0

        # 会话记忆：查看 / 新建 / 清空
        if question in SESSION_INFO_WORDS:
            try:
                info = session_info(session_id)
                print(f"  会话 {info.get('session_id')}：{info.get('turns')}/{info.get('max_turns')} 轮"
                      f"（Redis {'可用' if info.get('redis_available') else '不可用'}，"
                      f"TTL {info.get('ttl_seconds')}s）")
                for row in info.get("history") or []:
                    sources = "、".join(row.get("sources") or []) or "无来源"
                    print(f"    · {row.get('question')}　（来源：{sources}）")
            except Exception as e:
                print(f"  [错误] 会话信息读取失败：{e}")
            continue

        if question in NEW_SESSION_WORDS:
            session_id = new_session_id()
            print(f"  已切换到新会话：{session_id}（上一会话的记忆仍在 Redis 里，TTL 到期自动清理）")
            continue

        if question in CLEAR_SESSION_WORDS:
            try:
                result = clear_session(session_id)
                print(f"  会话 {session_id} 已清空：{result.get('cleared')}")
            except Exception as e:
                print(f"  [错误] 清空失败：{e}")
            continue

        # 反馈模式：对上一次回答点赞/点踩
        if question.startswith(("赞", "踩")):
            if not last:
                print("  还没有可反馈的回答，请先提问。")
                continue

            rating = "up" if question.startswith("赞") else "down"
            expected = question[1:].strip()
            try:
                result = send_feedback(last.get("trace_id", ""), rating, expected)
                print(f"  反馈已记录（id={result.get('feedback_id')}，rating={rating}）")
                if expected:
                    print(f"  期望来源：{expected}")
            except Exception as e:
                print(f"  [错误] 反馈提交失败：{e}")
            continue

        # 检索模式：不调用大模型，秒级返回
        if question.startswith("检索:") or question.startswith("检索："):
            keyword = question.split(":", 1)[-1].split("：", 1)[-1].strip()
            if not keyword:
                print("  请提供检索关键词，例如：检索:Redis 缓存穿透")
                continue
            print()
            try:
                start = time.time()
                print(search(keyword))
                print(f"\n  （检索耗时 {time.time() - start:.1f}s）")
            except Exception as e:
                print(f"  [错误] 检索失败：{e}")
            continue

        # 问答模式
        print("\n  正在检索并生成回答（首次约 30~70 秒，请稍候）...")
        try:
            start = time.time()
            result = ask(question, session_id)
            elapsed = time.time() - start
            last = result

            print()
            print("-" * 60)
            print(result.get("answer", ""))
            print("-" * 60)

            if result.get("rewritten"):
                print(f"  🧠 已按会话记忆补全指代，实际检索：{result.get('retrieval_query')}")

            score = result.get("top1_score")
            score_text = f"{score:.4f}" if isinstance(score, (int, float)) else "-"
            flag = "拒答" if result.get("refused") else "已作答"
            print(
                f"  （耗时 {elapsed:.1f}s | {flag} | 精排Top1={score_text} "
                f"| 阈值={result.get('threshold')} | 会话={session_id} | trace={result.get('trace_id')}）"
            )

        except urllib.error.HTTPError as e:
            print(f"\n  [错误] 服务返回 HTTP {e.code}：{e.reason}")
        except urllib.error.URLError as e:
            print(f"\n  [错误] 无法连接服务：{e.reason}")
            print("  请确认 启动.bat 的窗口还开着（关掉窗口服务就停了）")
        except Exception as e:
            print(f"\n  [错误] {e}")


if __name__ == "__main__":
    sys.exit(main())
