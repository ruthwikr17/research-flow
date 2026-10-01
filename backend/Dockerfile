FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Create the data directory for persistent quota/usage state (quota_monitor + search_service).
RUN mkdir -p /app/data
# Bake the embedding model into the image so container cold starts do not download it.
RUN python -c "from fastembed import TextEmbedding; list(TextEmbedding(model_name='BAAI/bge-small-en-v1.5').embed(['test']))"
EXPOSE 8000
# 1 worker: Render free tier is 512 MB RAM; multiple workers fight each other for memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

