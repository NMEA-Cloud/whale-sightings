# Self-contained build context — unlike client-mqtt/client-long-poll/client-ws, this
# service has no shared/ dependency to reach outside its own directory.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py route.py config.py ./

CMD ["python", "-u", "main.py"]
