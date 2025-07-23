# Деплой и CI/CD

## Автоматический деплой через GitHub Actions

В проекте настроен workflow `.github/workflows/deploy.yml`, который автоматически деплоит бота на сервер при каждом push в ветку `main`.

### Как это работает
1. Проверка кода и установка зависимостей
2. Запуск юнит-тестов
3. Копирование файлов на сервер через SCP
4. Перезапуск контейнера через SSH (docker build/run)

### Необходимые секреты (GitHub → Settings → Secrets and variables → Actions):
- `SERVER_HOST` — адрес сервера
- `SERVER_USER` — пользователь для SSH
- `SERVER_SSH_KEY` — приватный ключ для SSH
- `SERVER_PORT` — порт SSH
- `BOT_TOKEN` — токен Telegram-бота

### Пример ручного деплоя через Docker
```bash
docker build -t event-voting-bot .
docker run -d --env-file .env --name event-voting-bot event-voting-bot
```

### Переменные окружения для продакшена
- `BOT_TOKEN` — токен Telegram-бота
- `DB_TYPE=postgres` и параметры PostgreSQL (если используется Postgres)

### Структура workflow (deploy.yml)
- Установка Python 3.11
- Установка зависимостей
- Запуск тестов
- Копирование файлов на сервер
- Перезапуск контейнера через docker

---

Для любых изменений в коде просто пушьте в main — деплой произойдёт автоматически. 