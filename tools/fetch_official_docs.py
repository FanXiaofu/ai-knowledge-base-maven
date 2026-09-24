# -*- coding: utf-8 -*-
"""
官方技术文档抓取脚本

从已验证可达的官方文档站点抓取精选章节，保存为 HTML 到 knowledge-official/，
供知识库入库使用（由 HtmlKnowledgeLoader 解析）。

特点：
- 精选 URL 清单（每篇都指定可读的中文文件名，直接作为入库后的"来源"名）
- 限速 1.2 秒/请求，浏览器 User-Agent
- 已存在的文件跳过，可重复运行（断点续传）
- 失败项集中报告

运行：python tools/fetch_official_docs.py
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "knowledge-official"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

DELAY_SECONDS = 1.2

# 正文低于该字符数的页面视为"索引页"，会尝试补充其子页
INDEX_PAGE_THRESHOLD = 3000

# 每个索引页最多补充的子页数量
MAX_SUB_PAGES_PER_INDEX = 8

# (完整 URL, 保存的文件名标签)
PAGES = [
    # ==================== Spring Boot 官方参考文档 ====================
    ("https://docs.spring.io/spring-boot/4.1/reference/features/spring-application.html",
     "SpringBoot官方文档-SpringApplication启动"),
    ("https://docs.spring.io/spring-boot/4.1/reference/features/external-config.html",
     "SpringBoot官方文档-外部化配置"),
    ("https://docs.spring.io/spring-boot/4.1/reference/features/profiles.html",
     "SpringBoot官方文档-配置Profiles"),
    ("https://docs.spring.io/spring-boot/4.1/reference/features/logging.html",
     "SpringBoot官方文档-日志管理"),
    ("https://docs.spring.io/spring-boot/4.1/reference/features/aop.html",
     "SpringBoot官方文档-AOP支持"),
    ("https://docs.spring.io/spring-boot/4.1/reference/features/json.html",
     "SpringBoot官方文档-JSON处理"),
    ("https://docs.spring.io/spring-boot/4.1/reference/features/task-execution-and-scheduling.html",
     "SpringBoot官方文档-任务执行与调度"),
    ("https://docs.spring.io/spring-boot/4.1/reference/features/developing-auto-configuration.html",
     "SpringBoot官方文档-自动配置原理"),
    ("https://docs.spring.io/spring-boot/4.1/reference/io/validation.html",
     "SpringBoot官方文档-参数校验"),
    ("https://docs.spring.io/spring-boot/4.1/reference/io/caching.html",
     "SpringBoot官方文档-缓存抽象"),
    ("https://docs.spring.io/spring-boot/4.1/reference/io/rest-client.html",
     "SpringBoot官方文档-REST客户端"),
    ("https://docs.spring.io/spring-boot/4.1/reference/data/sql.html",
     "SpringBoot官方文档-数据库访问"),
    ("https://docs.spring.io/spring-boot/4.1/reference/data/nosql.html",
     "SpringBoot官方文档-NoSQL访问"),
    ("https://docs.spring.io/spring-boot/4.1/reference/messaging/amqp.html",
     "SpringBoot官方文档-RabbitMQ集成"),
    ("https://docs.spring.io/spring-boot/4.1/reference/messaging/kafka.html",
     "SpringBoot官方文档-Kafka集成"),
    ("https://docs.spring.io/spring-boot/4.1/reference/web/servlet.html",
     "SpringBoot官方文档-WebServlet应用"),
    ("https://docs.spring.io/spring-boot/4.1/reference/web/graceful-shutdown.html",
     "SpringBoot官方文档-优雅停机"),
    ("https://docs.spring.io/spring-boot/4.1/reference/actuator/endpoints.html",
     "SpringBoot官方文档-Actuator端点"),
    ("https://docs.spring.io/spring-boot/4.1/reference/actuator/metrics.html",
     "SpringBoot官方文档-指标监控"),
    ("https://docs.spring.io/spring-boot/4.1/reference/actuator/tracing.html",
     "SpringBoot官方文档-链路追踪"),
    ("https://docs.spring.io/spring-boot/4.1/reference/packaging/container-images/dockerfiles.html",
     "SpringBoot官方文档-容器镜像构建"),
    ("https://docs.spring.io/spring-boot/4.1/reference/web/spring-security.html",
     "SpringBoot官方文档-安全与认证"),
    ("https://docs.spring.io/spring-boot/4.1/reference/messaging/websockets.html",
     "SpringBoot官方文档-WebSocket支持"),
    ("https://docs.spring.io/spring-boot/4.1/reference/io/quartz.html",
     "SpringBoot官方文档-Quartz定时任务"),
    ("https://docs.spring.io/spring-boot/4.1/reference/io/spring-batch.html",
     "SpringBoot官方文档-批处理"),
    ("https://docs.spring.io/spring-boot/4.1/reference/actuator/observability.html",
     "SpringBoot官方文档-可观测性"),

    # ==================== Spring Framework 官方参考文档 ====================
    ("https://docs.spring.io/spring-framework/reference/core/beans.html",
     "Spring框架官方文档-IoC容器"),
    ("https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html",
     "Spring框架官方文档-注解配置"),
    ("https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html",
     "Spring框架官方文档-BeanFactory"),
    ("https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html",
     "Spring框架官方文档-Bean作用域"),
    ("https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html",
     "Spring框架官方文档-依赖注入细节"),
    ("https://docs.spring.io/spring-framework/reference/core/aop.html",
     "Spring框架官方文档-AOP面向切面"),
    ("https://docs.spring.io/spring-framework/reference/core/resources.html",
     "Spring框架官方文档-资源管理"),
    ("https://docs.spring.io/spring-framework/reference/core/validation.html",
     "Spring框架官方文档-数据校验"),
    ("https://docs.spring.io/spring-framework/reference/core/expressions.html",
     "Spring框架官方文档-SpEL表达式"),
    ("https://docs.spring.io/spring-framework/reference/data-access/transaction.html",
     "Spring框架官方文档-事务管理"),
    ("https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html",
     "Spring框架官方文档-声明式事务"),
    ("https://docs.spring.io/spring-framework/reference/data-access/jdbc.html",
     "Spring框架官方文档-JDBC访问"),
    ("https://docs.spring.io/spring-framework/reference/web/webmvc.html",
     "Spring框架官方文档-SpringMVC"),
    ("https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html",
     "Spring框架官方文档-控制器实现"),
    ("https://docs.spring.io/spring-framework/reference/testing/unit.html",
     "Spring框架官方文档-单元测试"),
    ("https://docs.spring.io/spring-framework/reference/integration/rest-clients.html",
     "Spring框架官方文档-REST客户端"),

    # ============ MySQL 中文教程（dev.mysql.com 官方站对本机 IP 返回 403，改用中文教程源）============
    ("https://www.runoob.com/mysql/mysql-index.html",
     "MySQL中文教程-索引"),
    ("https://www.runoob.com/mysql/mysql-transaction.html",
     "MySQL中文教程-事务"),
    ("https://www.runoob.com/mysql/mysql-data-types.html",
     "MySQL中文教程-数据类型"),
    ("https://www.runoob.com/mysql/mysql-join.html",
     "MySQL中文教程-连接查询"),
    ("https://www.runoob.com/mysql/mysql-sql-injection.html",
     "MySQL中文教程-SQL注入防护"),
    ("https://www.runoob.com/mysql/mysql-administration.html",
     "MySQL中文教程-数据库管理"),
    ("https://www.runoob.com/mysql/mysql-functions.html",
     "MySQL中文教程-常用函数"),
    ("https://www.runoob.com/mysql/mysql-alter.html",
     "MySQL中文教程-修改表结构"),
    ("https://www.runoob.com/mysql/mysql-handling-duplicates.html",
     "MySQL中文教程-重复数据处理"),
    ("https://www.runoob.com/mysql/mysql-create-tables.html",
     "MySQL中文教程-创建数据表"),
    ("https://www.runoob.com/mysql/mysql-operator.html",
     "MySQL中文教程-运算符"),
    ("https://www.runoob.com/mysql/mysql-regexp.html",
     "MySQL中文教程-正则表达式"),

    # ==================== RabbitMQ 官方文档 ====================
    ("https://www.rabbitmq.com/docs/queues",
     "RabbitMQ官方文档-队列"),
    ("https://www.rabbitmq.com/docs/exchanges",
     "RabbitMQ官方文档-交换机"),
    ("https://www.rabbitmq.com/docs/dlx",
     "RabbitMQ官方文档-死信队列"),
    ("https://www.rabbitmq.com/docs/ttl",
     "RabbitMQ官方文档-消息过期时间"),
    ("https://www.rabbitmq.com/docs/confirms",
     "RabbitMQ官方文档-发布者确认"),
    ("https://www.rabbitmq.com/docs/consumers",
     "RabbitMQ官方文档-消费者"),
    ("https://www.rabbitmq.com/docs/clustering",
     "RabbitMQ官方文档-集群"),
    ("https://www.rabbitmq.com/docs/memory",
     "RabbitMQ官方文档-内存管理"),

    # ==================== Redis 中文文档 ====================
    ("https://redis.com.cn/topics/data-types-intro.html",
     "Redis中文文档-数据类型"),
    ("https://redis.com.cn/topics/persistence.html",
     "Redis中文文档-持久化"),
    ("https://redis.com.cn/topics/replication.html",
     "Redis中文文档-主从复制"),
    ("https://redis.com.cn/topics/sentinel.html",
     "Redis中文文档-哨兵"),
    ("https://redis.com.cn/topics/cluster-spec.html",
     "Redis中文文档-集群规范"),
    ("https://redis.com.cn/topics/cluster-tutorial.html",
     "Redis中文文档-集群教程"),
    ("https://redis.com.cn/topics/distlock.html",
     "Redis中文文档-分布式锁"),
    ("https://redis.com.cn/topics/transactions.html",
     "Redis中文文档-事务"),
    ("https://redis.com.cn/topics/pubsub.html",
     "Redis中文文档-发布订阅"),
    ("https://redis.com.cn/topics/lru-cache.html",
     "Redis中文文档-内存淘汰策略"),
    ("https://redis.com.cn/topics/redis-cache-problems.html",
     "Redis中文文档-缓存问题"),
    ("https://redis.com.cn/topics/pipelining.html",
     "Redis中文文档-管道"),
    ("https://redis.com.cn/topics/redis-best-practices.html",
     "Redis中文文档-最佳实践"),
    ("https://redis.com.cn/topics/memory-optimization.html",
     "Redis中文文档-内存优化"),
]


def fetch(url, target):
    """下载单个页面，返回 (状态, 描述)。"""
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })

    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        return "FAIL", f"HTTP {e.code}"
    except Exception as e:
        return "FAIL", str(e)[:60]

    html = raw.decode("utf-8", errors="replace")

    if len(html) < 2000:
        return "FAIL", f"内容过短({len(html)}字节)"

    # 保存时即写入 base 标签：
    # 页面里的图片等资源是相对路径，
    # 脱离原站后无法解析，写入 base 后可还原为绝对地址。
    import re

    if "<base " not in html.lower():
        base_tag = f'<base href="{url}">'
        if re.search(r"<head[^>]*>", html, re.I):
            html = re.sub(r"(<head[^>]*>)", r"\1" + base_tag, html, count=1, flags=re.I)
        else:
            html = base_tag + html

    target.write_text(html, encoding="utf-8")
    return "OK", f"{len(html) // 1024}KB"


def inject_base_href():
    """
    为已下载的页面注入 <base href="原始URL">。

    保存下来的 HTML 里，图片等资源是相对路径，
    脱离原站后就解析不到了。
    写入 base 标签后，解析器可以把相对路径还原成原站绝对地址，
    从而使配图能够被抽取和下载。
    """
    import re

    fixed = 0

    for url, label in PAGES:
        target = OUT_DIR / f"{label}.html"

        if not target.exists():
            continue

        html = target.read_text(encoding="utf-8", errors="replace")

        if "<base " in html.lower():
            continue

        base_tag = f'<base href="{url}">'

        if re.search(r"<head[^>]*>", html, re.I):
            html = re.sub(
                r"(<head[^>]*>)",
                r"\1" + base_tag,
                html,
                count=1,
                flags=re.I,
            )
        else:
            html = base_tag + html

        target.write_text(html, encoding="utf-8")
        fixed += 1

    return fixed


def extract_content_length(html):
    """粗略估算正文长度，用于识别"索引页"。"""
    from bs4 import BeautifulSoup

    skip = {"script", "style", "noscript", "template", "form", "button",
            "select", "option", "svg", "nav", "header", "footer", "aside"}
    hints = ["nav", "menu", "sidebar", "side-bar", "toc", "breadcrumb",
             "footer", "header", "toolbar", "pagination", "pager"]

    def navish(el):
        marker = ((el.get("id") or "") + " " + " ".join(el.get("class") or [])).lower()
        return any(h in marker for h in hints)

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return 0

    articles = soup.find_all("article")
    root = max(articles, key=lambda e: len(e.get_text())) if articles else (soup.find("main") or soup.body)
    if not root:
        return 0

    total = 0
    for el in root.find_all(True):
        if el.name in skip or navish(el):
            continue
        if el.name in ("p", "li", "pre", "h1", "h2", "h3", "h4", "h5", "h6"):
            text = el.get_text(" ", strip=True)
            if text:
                total += len(text)
    return total


def find_sub_pages(html, base_url, limit):
    """
    发现某个索引页的直接子页面。

    技术文档站（如 Spring Framework 参考手册）是分层结构：
    core/beans.html 这类页面只放简介，
    真正的内容在 core/beans/*.html 下。
    """
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urlparse

    parsed = urlparse(base_url)

    if not parsed.path.endswith(".html"):
        return []

    # 子页前缀：core/beans.html -> core/beans/
    prefix = parsed.path[:-5] + "/"

    seen = set()
    results = []

    soup = BeautifulSoup(html, "lxml")

    for anchor in soup.find_all("a", href=True):

        target = urljoin(base_url, anchor["href"])
        tp = urlparse(target)

        if tp.netloc != parsed.netloc:
            continue

        if not tp.path.startswith(prefix):
            continue

        relative = tp.path[len(prefix):]

        # 只取直接子页，不递归更深层级
        if not relative.endswith(".html") or "/" in relative:
            continue

        clean = target.split("#")[0]

        if clean in seen:
            continue

        seen.add(clean)

        title = anchor.get_text(" ", strip=True)[:30] or relative[:-5]

        results.append((clean, title))

        if len(results) >= limit:
            break

    return results


def expand_index_pages():
    """
    对"薄"的索引页自动补充其直接子页。

    判定标准：正文字符数低于阈值（索引页通常只有一段简介）。
    每个索引页最多补充 MAX_SUB_PAGES_PER_INDEX 个子页，
    避免语料规模失控。
    """
    from urllib.parse import urlparse

    added = 0

    for url, label in PAGES:

        source = OUT_DIR / f"{label}.html"

        if not source.exists():
            continue

        html = source.read_text(encoding="utf-8", errors="replace")

        if extract_content_length(html) >= INDEX_PAGE_THRESHOLD:
            continue

        children = find_sub_pages(html, url, MAX_SUB_PAGES_PER_INDEX)

        if not children:
            continue

        print(f"\n索引页扩展：{label}（正文偏短，发现 {len(children)} 个子页）")

        for child_url, child_title in children:

            child_label = f"{label}-{child_title}"
            child_label = "".join(
                c for c in child_label
                if c not in '\\/:*?"<>|'
            )[:80]

            target = OUT_DIR / f"{child_label}.html"

            if target.exists() and target.stat().st_size > 2000:
                continue

            status, detail = fetch(child_url, target)

            if status == "OK":
                added += 1
                print(f"   + {detail:>8}  {child_label}")
            else:
                print(f"   - 失败({detail})  {child_label}")

            time.sleep(DELAY_SECONDS)

    return added


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"  官方文档抓取：共 {len(PAGES)} 篇 → {OUT_DIR}")
    print("=" * 78)
    print()

    ok_count = 0
    skip_count = 0
    failures = []

    for index, (url, label) in enumerate(PAGES, start=1):
        target = OUT_DIR / f"{label}.html"

        if target.exists() and target.stat().st_size > 2000:
            print(f"[{index:02d}/{len(PAGES)}] 跳过（已存在）  {label}")
            skip_count += 1
            continue

        status, detail = fetch(url, target)

        if status == "OK":
            ok_count += 1
            print(f"[{index:02d}/{len(PAGES)}] 成功 {detail:>8}  {label}")
        else:
            failures.append((label, url, detail))
            print(f"[{index:02d}/{len(PAGES)}] 失败 {detail:>8}  {label}")

        time.sleep(DELAY_SECONDS)

    print()
    print("=" * 78)
    print(f"  完成：成功 {ok_count}，跳过 {skip_count}，失败 {len(failures)}")
    print("=" * 78)

    if failures:
        print()
        print("失败明细：")
        for label, url, detail in failures:
            print(f"  - {label}\n    {url}\n    原因: {detail}")

    manifest = {
        "total": len(PAGES),
        "success": ok_count,
        "skipped": skip_count,
        "failed": len(failures),
        "files": [
            {"label": label, "url": url}
            for url, label in PAGES
            if (OUT_DIR / f"{label}.html").exists()
        ],
    }

    manifest_path = OUT_DIR / "_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"清单已写入：{manifest_path}")

    fixed = inject_base_href()
    print(f"已为 {fixed} 个页面注入 base 标签（使相对路径图片可解析）")

    print()
    print("=" * 78)
    print("  检查索引页并补充子页")
    print("=" * 78)

    added = expand_index_pages()
    print(f"\n索引页扩展共补充 {added} 篇")


if __name__ == "__main__":
    main()
