# 1. Базовый образ: берем официальный легкий Linux с предустановленным Python 3.11
FROM python:3.11-slim

# 2. Устанавливаем системные библиотеки, необходимые для работы Pillow с форматом WebP
RUN apt-get update && apt-get install -y --no-install-recommends \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Указываем рабочую папку внутри контейнера, где будет жить наш код
WORKDIR /app

# 4. Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем весь остальной код и папки из нашего компьютера в контейнер
COPY . .

# 6. Принудительно создаем папки для кэша и оригиналов внутри контейнера
RUN mkdir -p hotel_images image_cache

# 7. Открываем порт 8000, который будет слушать наше приложение
EXPOSE 8000

# 8. Команда для запуска сервера (0.0.0.0 позволяет принимать запросы извне контейнера)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
