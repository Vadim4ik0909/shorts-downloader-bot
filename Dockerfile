# Офіційний легкий образ Python
FROM python:3.12-slim

# Встановлюємо ffmpeg, nodejs, curl, unzip та deno (для розшифрування JS челенджів YouTube)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    curl \
    unzip \
    && curl -fsSL https://deno.land/install.sh | sh \
    && mv /root/.deno/bin/deno /usr/local/bin/ \
    && apt-get purge -y unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копіюємо файл залежностей та встановлюємо їх
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -U yt-dlp

# Копіюємо вихідний код проєкту
COPY . .

# Створюємо директорії для тимчасових файлів та бази даних
RUN mkdir -p temp data

# Запуск бота
CMD ["python", "main.py"]
