# Используем официальный образ Python, соответствующий вашей версии (например, 3.11)
FROM python:3.11-slim-bookworm # Указал bookworm для актуальности

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PATH="/home/djangoapp/.local/bin:${PATH}" # Для pip install --user, если понадобится

# Создаем пользователя и группу до установки зависимостей, чтобы избежать проблем с правами
RUN groupadd -r djangoapp && useradd -r -g djangoapp -d /home/djangoapp -s /sbin/nologin -c "Django App User" djangoapp
RUN mkdir /home/djangoapp && chown djangoapp:djangoapp /home/djangoapp

# Обновляем пакеты и устанавливаем системные зависимости
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \        # Для PostgreSQL
        gettext \          # Для переводов Django
        libjpeg-dev \      # Для Pillow
        zlib1g-dev \
        libtiff-dev \
        libfreetype6-dev \
        libwebp-dev \
        libopenjp2-7-dev \
        # curl \           # Может понадобиться для healthchecks или других утилит
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем только requirements.txt для кэширования установки зависимостей
COPY requirements.txt /app/

# Устанавливаем зависимости Python
# --no-cache-dir уменьшает размер образа
# Используем virtualenv внутри образа для изоляции, хотя для slim образов это менее критично
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта в рабочую директорию
# .dockerignore должен быть настроен, чтобы не копировать лишнее
COPY . /app/

# Собираем статические файлы Django
# STATIC_ROOT должен быть настроен в settings.py (например, /app/staticfiles_collected)
# Эта команда выполняется от имени root, чтобы иметь права на запись в STATIC_ROOT
# Затем меняем владельца, если нужно, чтобы djangoapp мог их читать (обычно не нужно для collectstatic)
RUN python manage.py collectstatic --noinput --clear
# Если вы хотите, чтобы nginx читал статику от имени djangoapp (редко):
# RUN chown -R djangoapp:djangoapp /app/staticfiles_collected 

# Создаем директорию для медиа файлов, если она будет внутри контейнера и управляться Django
# Обычно медиа монтируется как volume, но директория должна существовать
RUN mkdir -p /app/mediafiles && chown -R djangoapp:djangoapp /app/mediafiles

# Устанавливаем владельца всего кода приложения для пользователя djangoapp
RUN chown -R djangoapp:djangoapp /app

# Переключаемся на непривилегированного пользователя
USER djangoapp

# Открываем порт, на котором будет работать ASGI-сервер (Daphne)
EXPOSE 8000

# Команда для запуска приложения при старте контейнера
# config.asgi:application - это путь к вашему ASGI-приложению
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]