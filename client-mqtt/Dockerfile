# Build context is the repo root (see docker-compose.yml) so this can also reach shared/,
# a sibling directory Docker won't let a Dockerfile COPY from otherwise.
FROM python:3.12-slim

WORKDIR /app

COPY client-mqtt/ ./
COPY shared/sightings-shared.js ./

RUN chmod +x docker-entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["./docker-entrypoint.sh"]
