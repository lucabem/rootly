FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

COPY rag/requirements.txt /tmp/rag-req.txt
COPY backend/requirements.txt /tmp/backend-req.txt
RUN pip install --no-cache-dir -r /tmp/rag-req.txt -r /tmp/backend-req.txt

COPY rag/ /app/rag/
COPY backend/ /app/backend/

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
