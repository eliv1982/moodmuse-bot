# SpringPost — ProxyAPI (images/STT) + YandexGPT (text / prompt refine)
FROM python:3.11-slim

WORKDIR /app

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py bot.py ./
COPY handlers/ ./handlers/
COPY services/ ./services/
COPY utils/ ./utils/

CMD ["python", "-u", "bot.py"]
