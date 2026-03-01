#!/bin/bash
# Обновление и перезапуск бота на сервере.
# Запуск из каталога проекта: cd /home/user/springpost && ./deploy.sh
# Только перезапуск: ./deploy.sh --restart

set -e
cd "$(dirname "$0")"

if [ "$1" = "--restart" ]; then
  echo "[deploy] Перезапуск контейнера..."
  docker compose up -d
  exit 0
fi

# Если проект в Git — подтягиваем обновления и при наличии изменений пересобираем
if [ -d .git ]; then
  echo "[deploy] Проверка обновлений (git pull)..."
  BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "none")
  git pull 2>/dev/null || true
  AFTER=$(git rev-parse HEAD 2>/dev/null || echo "none")
  if [ -n "$BEFORE" ] && [ -n "$AFTER" ] && [ "$BEFORE" != "$AFTER" ]; then
    echo "[deploy] Есть новые коммиты. Сборка образа и перезапуск..."
    docker compose build --no-cache
    docker compose up -d
    echo "[deploy] Готово."
    exit 0
  fi
fi

# Нет Git или изменений не было — просто перезапуск (подхватит текущий образ)
echo "[deploy] Перезапуск контейнера..."
docker compose up -d
