FROM python:3.11-slim

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование зависимостей
COPY ../requirements.txt ./

# Установка Python-зависимостей
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копирование исходного кода
COPY . .

# Указание переменных окружения (опционально)
ENV PYTHONUNBUFFERED=1

# Команда запуска
CMD ["python", "bot.py"] 