# Офіційний легкий образ Python
FROM python:3.12-slim

# Встановлюємо ffmpeg, nodejs (для вирішення JS-челенджів та підписів YouTube/Instagram) та curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копіюємо файл залежностей та встановлюємо їх
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо вихідний код проєкту
COPY . .

# Створюємо директорії для тимчасових файлів та бази даних
RUN mkdir -p temp data

# Запуск бота
CMD ["python", "main.py"]
