# Бот хорошего настроения (ProxyAPI.ru + GigaChat)
FROM python:3.11-slim

WORKDIR /app

# Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY config.py bot.py ./
COPY handlers/ ./handlers/
COPY services/ ./services/
COPY utils/ ./utils/

# Запуск (polling, без webhook)
CMD ["python", "-u", "bot.py"]
