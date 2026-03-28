# Деплой бота «Весеннее настроение» на сервер

Пошаговая инструкция по запуску бота в Docker на VPS (Ubuntu/Debian или другой Linux с Docker).

---

## 1. Требования к серверу

- **ОС:** Linux (Ubuntu 22.04, Debian 11/12 и т.п.)
- **Docker** и **Docker Compose** (v2)
- **Доступ:** SSH по ключу или паролю
- Открытые порты для SSH (22); для бота порты не нужны (работа в режиме polling).

---

## 2. Установка Docker на сервер (если ещё не установлен)

Подключитесь по SSH и выполните:

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Выйдите из SSH и зайдите снова, чтобы применилась группа `docker`. Проверка:

```bash
docker --version
docker compose version
```

---

## 3. Подготовка проекта на сервере

### 3.1. Копирование файлов

С локального компьютера скопируйте проект на сервер (из каталога с ботом):

```bash
# С вашего ПК (замените user и your-server на свои данные)
scp -r . user@your-server:/home/user/springpost
```

Или клонируйте репозиторий на сервер (если код в Git):

```bash
ssh user@your-server
git clone <url-репозитория> springpost
cd springpost
```

### 3.2. Какие файлы должны быть на сервере

Минимальный набор:

```
springpost/
├── .env          # создаёте вручную, см. ниже
├── bot.py
├── config.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── deploy.sh     # скрипт обновления (chmod +x deploy.sh)
├── handlers/
├── services/
└── utils/
```

Файл `.env` на сервер **не копируйте** с рабочей машины по соображениям безопасности — создайте его на сервере и заполните там же.

---

## 4. Создание файла .env на сервере

На сервере в каталоге проекта:

```bash
cd /home/user/springpost
nano .env
```

Вставьте (подставьте свои значения):

```env
# Telegram (токен от @BotFather)
BOT_TOKEN=ваш_токен_бота

# ProxyAPI.ru (ключ из https://console.proxyapi.ru)
PROXI_API_KEY=ваш_ключ
PROXI_BASE_URL=https://openai.api.proxyapi.ru

# Yandex Cloud Foundation Models (текст + улучшение промпта картинки)
YANDEX_API_KEY=ваш_api_ключ
YANDEX_FOLDER_ID=b1gxxxxxxxxxxxxxxxxxxxx

# Админы (Telegram user id через запятую) — лимиты не действуют, доступ к /stats и др.
# ADMIN_USER_IDS=123456789

# По желанию: LOG_LEVEL=DEBUG, LOG_JSON=true, DATA_DIR=/app/data
```

Сохраните (в nano: `Ctrl+O`, Enter, `Ctrl+X`). Проверьте права:

```bash
chmod 600 .env
```

---

## 5. Сборка и запуск в Docker

В каталоге проекта на сервере:

```bash
cd /home/user/springpost
docker compose build
docker compose up -d
```

Проверка, что контейнер запущен:

```bash
docker compose ps
docker compose logs -f
```

В логах должно быть сообщение вроде: `Starting bot (polling)`. Выход из логов: `Ctrl+C`.

---

## 6. Управление ботом на сервере

| Действие              | Команда |
|-----------------------|--------|
| Запустить             | `docker compose up -d` |
| Остановить            | `docker compose down` |
| Перезапустить         | `docker compose restart` |
| Смотреть логи         | `docker compose logs -f` |
| Обновить код и перезапустить | `git pull` (если используете Git), затем `docker compose build --no-cache && docker compose up -d` |

---

## 7. Автоперезапуск при перезагрузке сервера

**Да, бот будет автоматически запускаться после перезагрузки сервера.**

Цепочка такая:

1. В `docker-compose.yml` указано **`restart: unless-stopped`** — Docker перезапускает контейнер при падении и поднимает его после старта самого Docker.
2. После перезагрузки сервера systemd запускает службу **Docker**.
3. Docker поднимает все контейнеры с политикой `restart: unless-stopped`, в том числе бота.

**Проверка, что Docker включён в автозагрузку:**

```bash
sudo systemctl is-enabled docker
```

Должно быть **`enabled`**. Если нет:

```bash
sudo systemctl enable docker
```

**Как проверить автоперезапуск:** перезагрузите сервер (`sudo reboot`), через 1–2 минуты зайдите по SSH и выполните `docker compose ps` в каталоге проекта — контейнер `springpost` должен быть в состоянии `Up`.

---

## 8. Обновление кода: вручную и автоматически

### 8.1. Ручное обновление после изменений

На сервере в каталоге проекта:

```bash
cd /home/user/springpost
git pull
docker compose build --no-cache
docker compose up -d
```

Или используйте скрипт **`deploy.sh`** (один раз сделайте его исполняемым: `chmod +x deploy.sh`):

```bash
cd /home/user/springpost
./deploy.sh
```

Скрипт сам сделает `git pull` и при наличии новых коммитов пересоберёт образ и перезапустит контейнер.

Только перезапуск без обновления кода (например, после правки `.env`):

```bash
docker compose up -d --force-recreate
```

Или: `./deploy.sh --restart` (если используете скрипт).

### 8.2. Автообновление с локальной машины (через Git + cron)

Чтобы изменения кода на сервере подтягивались автоматически после вашего `git push`:

1. **Деплой через Git.** На сервере проект должен быть клонирован из репозитория (`git clone ...`), и вы с локальной машины пушите изменения в этот репозиторий (GitHub, GitLab и т.п.).

2. **Скрипт `deploy.sh` на сервере.** В каталоге проекта выполните один раз:
   ```bash
   chmod +x deploy.sh
   ```

3. **Cron на сервере.** Раз в 5–10 минут запускать проверку обновлений и при необходимости пересборку:
   ```bash
   crontab -e
   ```
   Добавьте строку (подставьте свой путь и пользователя):
   ```cron
   */5 * * * * cd /home/user/springpost && ./deploy.sh >> /home/user/springpost/deploy.log 2>&1
   ```
   Тогда каждые 5 минут сервер будет делать `git pull`; при появлении новых коммитов скрипт пересоберёт образ и перезапустит бота.

**Схема работы:** вы правите код локально → делаете `git push` → в течение нескольких минут cron на сервере запускает `deploy.sh` → скрипт подтягивает изменения и перезапускает контейнер.

Логи запусков скрипта можно смотреть в `deploy.log` в каталоге проекта.

---

## 9. Безопасность

- Храните `.env` только на сервере, не коммитьте в Git и не копируйте в открытый доступ.
- Для SSH используйте ключи, отключите вход по паролю при возможности.
- Ограничьте доступ к серверу firewall (например, `ufw`): оставьте открытыми только SSH и при необходимости другие нужные порты. Для самого бота порты не требуются.

---

## 10. Проверка, что Yandex-переменные попали в контейнер

После заполнения `.env` в **том же каталоге**, что и `docker-compose.yml`:

```bash
cd /путь/к/проекту
docker compose config | grep YANDEX_
```

Должны отображаться `YANDEX_API_KEY` и `YANDEX_FOLDER_ID` в блоке `environment` сервиса `bot`. Если их нет — строк нет в `.env`, они закомментированы, или правится не тот файл. После правок:

```bash
docker compose up -d --force-recreate
```

Проверка длин без вывода секретов:

```bash
docker compose exec bot sh -c 'echo "YANDEX_API_KEY len=${#YANDEX_API_KEY} YANDEX_FOLDER_ID len=${#YANDEX_FOLDER_ID}"'
```

---

## 11. Проверка работы бота

1. В Telegram найдите бота по username и отправьте `/start`.
2. Пройдите сценарий: **для кого** → описание картинки → праздник/повод → стиль картинки → стиль текста → проверьте открытку.
3. При ошибках смотрите логи: `docker compose logs -f`.

Готово. Бот работает в фоне и перезапускается при падении или перезагрузке сервера.
