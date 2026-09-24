from FlagEmbedding import FlagReranker
import torch


MODEL_NAME = "BAAI/bge-reranker-v2-m3"


print("========== Environment ==========")
print("PyTorch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

print("\n========== Loading Model ==========")

reranker = FlagReranker(
    MODEL_NAME,
    use_fp16=True
)

print("Model loaded successfully.")

print("\n========== Test Reranking ==========")

query = "Redis分布式锁怎么实现？"

passages = [
    "Redis可以使用SET命令结合NX和EX参数实现分布式锁，从而保证同一时刻只有一个客户端能够获得锁。",
    "RabbitMQ可以通过消息确认机制、持久化以及生产者确认等机制提高消息可靠性。",
    "MySQL索引可以减少数据库查询过程中需要扫描的数据量，从而提高查询效率。"
]

scores = reranker.compute_score(
    [[query, passage] for passage in passages],
    normalize=True
)

for i, (passage, score) in enumerate(zip(passages, scores), start=1):
    print(f"\nPassage {i}")
    print("Score:", score)
    print("Content:", passage)