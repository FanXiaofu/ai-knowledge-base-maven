from typing import List

from fastapi import FastAPI
from pydantic import BaseModel
from FlagEmbedding import FlagReranker


MODEL_NAME = "BAAI/bge-reranker-v2-m3"


print("========== Loading Reranker Model ==========")

reranker = FlagReranker(
    MODEL_NAME,
    use_fp16=True
)

print("Reranker model loaded successfully.")


app = FastAPI(
    title="AI Knowledge Base Reranker",
    version="1.0.0"
)


class RerankDocument(BaseModel):
    id: str
    content: str


class RerankRequest(BaseModel):
    query: str
    documents: List[RerankDocument]
    top_k: int = 3


class RerankResult(BaseModel):
    id: str
    score: float
    content: str


class RerankResponse(BaseModel):
    results: List[RerankResult]


@app.get("/health")
def health():
    return {
        "status": "UP",
        "model": MODEL_NAME
    }


@app.post("/rerank", response_model=RerankResponse)
def rerank(request: RerankRequest):

    if not request.documents:
        return RerankResponse(results=[])

    pairs = [
        [request.query, document.content]
        for document in request.documents
    ]

    scores = reranker.compute_score(
        pairs,
        normalize=True
    )

    if not isinstance(scores, list):
        scores = [scores]

    results = []

    for document, score in zip(request.documents, scores):
        results.append(
            RerankResult(
                id=document.id,
                score=float(score),
                content=document.content
            )
        )

    results.sort(
        key=lambda item: item.score,
        reverse=True
    )

    top_k = max(1, min(request.top_k, len(results)))

    return RerankResponse(
        results=results[:top_k]
    )