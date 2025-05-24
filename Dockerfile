# Dockerfile

# --- Stage 1: Builder ---
FROM python:3.11-slim-bookworm as builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV LANG C.UTF-8 LC_ALL C.UTF-8
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Создаем пользователя и группу
RUN groupadd --system appgroup && \
    useradd --system -g appgroup -d /home/appuser -s /sbin/nologin -c "Django App User" appuser
RUN mkdir -p /home/appuser && chown appuser:appgroup /home/appuser

# Устанавливаем Node.js и npm
RUN apt-get update && apt-get install -y curl gnupg --no-install-recommends \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        gettext \
        libjpeg-dev \
        zlib1g-dev \
        libtiff-dev \
        libfreetype6-dev \
        libwebp-dev \
        libopenjp2-7-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g npm@latest # Обновляем npm

WORKDIR /app

# Копируем requirements.txt и устанавливаем Python зависимости
COPY requirements.txt /app/
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файлы для Node.js зависимостей
# Убедитесь, что эти файлы существуют в корне вашего проекта
COPY package.json ./
# Копируем package-lock.json, если он существует (добавил || true чтобы не падать если его нет)
COPY package-lock.json* ./ || true 
# COPY tailwind.config.js ./
# COPY postcss.config.js ./
# Устанавливаем Node.js зависимости
RUN npm ci --only=production || npm install --only=production

# Копируем остальной код приложения
COPY . /app/

# Сборка Tailwind CSS
# Убедитесь, что TAILWIND_APP_NAME в settings.py (например, 'theme')
# и что в theme/static/src/input.css и tailwind.config.js все пути корректны
RUN echo "Building Tailwind CSS..." && \
    python manage.py tailwind build
    # Если предыдущая команда не работает из-за настроек Django на этом этапе,
    # вы можете попробовать собрать Tailwind напрямую, если знаете пути:
    # RUN npx tailwindcss -c ./tailwind.config.js -i ./theme/static/src/input.css -o ./app/${TAILWIND_APP_NAME:-theme}/static/${TAILWIND_APP_NAME:-theme}/css/dist/styles.css --minify
    # Замените ${TAILWIND_APP_NAME:-theme} на имя вашего приложения с темой

# --- Stage 2: Runtime ---
FROM python:3.11-slim-bookworm as runtime

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE=config.settings
ENV ASGI_APPLICATION=config.asgi:application
ENV LANG C.UTF-8 LC_ALL C.UTF-8
ENV PATH="/opt/venv/bin:/home/appuser/.local/bin:${PATH}"

WORKDIR /app

# Создаем пользователя и группу (такие же, как в builder stage)
RUN groupadd --system appgroup && \
    useradd --system -g appgroup -d /home/appuser -s /sbin/nologin -c "Django App User" appuser
# RUN mkdir -p /home/appuser && chown appuser:appgroup /home/appuser # Домашняя директория уже создана useradd -d

# Устанавливаем runtime системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gettext \
    postgresql-client \
    redis-tools \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Копируем virtualenv из builder stage
COPY --from=builder /opt/venv /opt/venv

# Копируем собранное приложение из builder stage
# Важно: --chown=appuser:appgroup чтобы файлы принадлежали правильному пользователю
COPY --from=builder --chown=appuser:appgroup /app /app

# Копируем entrypoint.sh и делаем его исполняемым
COPY --chown=appuser:appgroup ./entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Создаем директории для статики и медиа и устанавливаем права
# Эти пути должны соответствовать STATIC_ROOT и MEDIA_ROOT в ваших settings.py
RUN mkdir -p /app/staticfiles_collected /app/mediafiles \
    && chown -R appuser:appgroup /app/staticfiles_collected \
    && chown -R appuser:appgroup /app/mediafiles

# Переключаемся на непривилегированного пользователя
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]