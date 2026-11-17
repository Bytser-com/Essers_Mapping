FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    INCOMING_DIR=/tmp/source

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -u 1000 -m -s /bin/sh appuser && \
    mkdir -p /tmp/source /app/output && \
    chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
