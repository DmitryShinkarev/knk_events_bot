# Event Voting Bot

Telegram-бот для организации голосования за мероприятия с поддержкой уведомлений, подписки, статистики и удобного интерфейса.

## Возможности
- Создание мероприятий с датой (только ближайшие 30 дней)
- Голосование: "Иду ✅", "Не иду ❌", "Думаю 🤔"
- Просмотр статистики и списков участников
- Удаление мероприятия (создателем или админом)
- Уведомления о новых мероприятиях только для подписчиков
- Команды-меню Telegram (отображаются при вводе "/")

## Команды бота
- `/start` — Приветствие и краткая инструкция
- `/help` — Подробная справка
- `/create` — Создать новое мероприятие
- `/events` — Список активных мероприятий
- `/subscribe` — Подписаться на уведомления о новых мероприятиях
- `/unsubscribe` — Отписаться от уведомлений

## Быстрый старт (локально)
```bash
cd event_voting_bot
python3 -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt

# Создайте .env с вашим токеном
 echo "BOT_TOKEN=ваш_токен_бота" > .env

python bot.py
```

## Тесты и линтеры
```bash
pytest
flake8 event_voting_bot/
isort --check event_voting_bot/
black --check event_voting_bot/
```

## Docker
```bash
docker build -t event-voting-bot .
docker run -d --env-file .env --name event-voting-bot event-voting-bot
```

## CI/CD
- Автоматический деплой через GitHub Actions при push в main (см. deploy.md)

## Требования
- Python 3.11+
- Docker (для деплоя)
- Telegram-бот токен (через @BotFather)

## Лицензия
MIT 