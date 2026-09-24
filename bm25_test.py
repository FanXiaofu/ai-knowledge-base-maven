import math
import re
import psycopg2
from collections import Counter


# =========================
# 1. PostgreSQL 配置
# =========================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "ai_knowledge",
    "user": "ai_user",
    "password": "ai_password",
}


# =========================
# 2. 文本 Tokenization
# =========================

def tokenize(text):
    """
    面向技术知识库的简单 Tokenizer：

    1. 英文、数字、技术名称：
       Redis / HashMap / RabbitMQ / B+Tree / ACID

    2. 连续中文：
       按中文单字切分，保证中文也能够参与 BM25。

    例如：

    Redis分布式锁怎么实现

    ->
    redis
    分
    布
    式
    锁
    怎
    么
    实
    现
    """

    text = text.lower()

    # 英文、数字、技术组合词
    english_tokens = re.findall(
        r"[a-zA-Z][a-zA-Z0-9+#.-]*|\d+(?:\.\d+)?",
        text
    )

    # 中文单字
    chinese_tokens = re.findall(
        r"[\u4e00-\u9fff]",
        text
    )

    # 保持文本中的大致顺序：
    # 重新扫描文本
    pattern = re.compile(
        r"[a-zA-Z][a-zA-Z0-9+#.-]*|\d+(?:\.\d+)?|[\u4e00-\u9fff]"
    )

    return pattern.findall(text)


# =========================
# 3. 从 PostgreSQL 读取知识库
# =========================

def load_documents():
    conn = psycopg2.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, content
                FROM vector_store
                ORDER BY id
            """)

            rows = cursor.fetchall()

            return [
                {
                    "id": str(row[0]),
                    "content": row[1]
                }
                for row in rows
            ]

    finally:
        conn.close()


# =========================
# 4. BM25
# =========================

class BM25:

    def __init__(self, documents, k1=1.5, b=0.75):

        self.documents = documents
        self.k1 = k1
        self.b = b

        self.tokenized_documents = [
            tokenize(doc["content"])
            for doc in documents
        ]

        self.doc_lengths = [
            len(tokens)
            for tokens in self.tokenized_documents
        ]

        self.avg_doc_length = (
            sum(self.doc_lengths)
            / len(self.doc_lengths)
            if self.doc_lengths
            else 0
        )

        self.document_frequency = Counter()

        for tokens in self.tokenized_documents:
            unique_tokens = set(tokens)

            for token in unique_tokens:
                self.document_frequency[token] += 1

        self.document_count = len(documents)

    def idf(self, token):

        df = self.document_frequency.get(token, 0)

        if df == 0:
            return 0.0

        return math.log(
            1
            + (
                (self.document_count - df + 0.5)
                / (df + 0.5)
            )
        )

    def score(self, query, doc_index):

        query_tokens = tokenize(query)

        document_tokens = self.tokenized_documents[doc_index]

        term_frequency = Counter(document_tokens)

        doc_length = self.doc_lengths[doc_index]

        score = 0.0

        for token in query_tokens:

            tf = term_frequency.get(token, 0)

            if tf == 0:
                continue

            idf = self.idf(token)

            denominator = (
                tf
                + self.k1
                * (
                    1
                    - self.b
                    + self.b
                    * doc_length
                    / self.avg_doc_length
                )
            )

            score += (
                idf
                * (
                    tf
                    * (self.k1 + 1)
                    / denominator
                )
            )

        return score

    def search(self, query, top_k=5):

        results = []

        for i, doc in enumerate(self.documents):

            score = self.score(query, i)

            results.append({
                "id": doc["id"],
                "score": score,
                "content": doc["content"]
            })

        results.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return results[:top_k]


# =========================
# 5. 测试
# =========================

if __name__ == "__main__":

    documents = load_documents()

    print("=" * 80)
    print(f"Loaded documents: {len(documents)}")
    print("=" * 80)

    bm25 = BM25(documents)

    test_queries = [
        "Redis",
        "HashMap",
        "RabbitMQ",
        "MySQL索引",
        "Redis分布式锁怎么实现",
        "Redis缓存击穿怎么解决",
        "RabbitMQ消息可靠性怎么保证",
        "Java虚拟机的垃圾回收器有哪些",
        "Spring IoC是什么",
        "Docker容器是什么",
    ]

    for query in test_queries:

        print()
        print("=" * 80)
        print(f"Query: {query}")
        print("=" * 80)

        results = bm25.search(query, top_k=5)

        for rank, result in enumerate(results, start=1):

            # 从 Markdown 标题中简单提取文档名称
            match = re.search(
                r"#\s+(.+?)\s*知识库",
                result["content"]
            )

            source = (
                match.group(1)
                if match
                else "Unknown"
            )

            print(
                f"{rank}. "
                f"{source:<10} "
                f"score={result['score']:.4f}"
            )