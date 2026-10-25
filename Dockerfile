# MoodMuse — OpenAI (images / text / STT); legacy ProxyAPI + YandexGPT providers still selectable
FROM python:3.11-slim

WORKDIR /app

ENV DATA_DIR=/app/data
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py bot.py ./
COPY handlers/ ./handlers/
COPY services/ ./services/
COPY utils/ ./utils/
COPY assets/ ./assets/

CMD ["python", "-u", "bot.py"]
