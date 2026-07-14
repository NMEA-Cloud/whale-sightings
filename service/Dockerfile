FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Defaults match the paths docker-compose.yml mounts certs/ to; override via
# environment if a developer generated the cert elsewhere.
ENV TLS_CERT_FILE=/certs/localhost.pem
ENV TLS_KEY_FILE=/certs/localhost-key.pem

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-certfile "$TLS_CERT_FILE" --ssl-keyfile "$TLS_KEY_FILE"
