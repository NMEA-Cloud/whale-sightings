# Self-contained build context — unlike client-mqtt/client-long-poll/client-ws, this
# service has no shared/ dependency to reach outside its own directory.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Every top-level module, so a new one can't be silently left out of the image (tests/ is
# excluded by .dockerignore).
COPY *.py ./

CMD ["python", "-u", "main.py"]
