FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DATASET_PATH=/app/data/manufacturing_data.csv \
    DATABASE_PATH=/tmp/manufacturing-insight-ai/app.db \
    CORS_ORIGINS=https://min-bok.github.io,http://localhost:3000,http://127.0.0.1:3000

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY data /app/data

WORKDIR /app/backend

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]