FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY reranker_service.py .

EXPOSE 8001

CMD ["uvicorn", "reranker_service:app", "--host", "0.0.0.0", "--port", "8001"]
