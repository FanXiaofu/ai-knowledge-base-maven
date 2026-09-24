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
SEARCH_API = BASE_URL + "/api/knowledge/hybrid-search"
HEALTH_API = BASE_URL + "/actuator/health"

EXIT_WORDS = {"q", "quit", "exit", "退出", "结束"}


def http_get(url, timeout=300):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def check_service():
    """启动前检查应用是否在运行。"""
    try:
        http_get(HEALTH_API, timeout=5)
        return True
    except Exception:
        return False


def ask(question):
    """向 /api/chat 提问，返回答案文本。"""
    url = CHAT_API + "?" + urllib.parse.urlencode({"question": question})
    return http_get(url)


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
    print("  输入 检索:关键词  可只查看召回片段（更快，不调用大模型）")
    print("  输入 q 或 退出  结束")
    print()
    print("-" * 60)

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
            answer = ask(question)
            elapsed = time.time() - start

            print()
            print("-" * 60)
            print(answer)
            print("-" * 60)
            print(f"  （耗时 {elapsed:.1f}s）")

        except urllib.error.HTTPError as e:
            print(f"\n  [错误] 服务返回 HTTP {e.code}：{e.reason}")
        except urllib.error.URLError as e:
            print(f"\n  [错误] 无法连接服务：{e.reason}")
            print("  请确认 启动.bat 的窗口还开着（关掉窗口服务就停了）")
        except Exception as e:
            print(f"\n  [错误] {e}")


if __name__ == "__main__":
    sys.exit(main())
