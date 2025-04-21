# Использовать официальный образ Python
FROM python:3.11-slim

# Установить переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Установить рабочую директорию
WORKDIR /app

# Установить системные зависимости (если нужны, например, для Pillow или PostgreSQL)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     libpq-dev \
#  && rm -rf /var/lib/apt/lists/*

# Установить pipenv (если используете) или обновить pip
# RUN pip install --upgrade pip pipenv
# Копировать Pipfile и Pipfile.lock (если используете pipenv)
# COPY Pipfile Pipfile.lock ./
# RUN pipenv install --system --deploy --ignore-pipfile
# ИЛИ Установить зависимости через requirements.txt (стандартный способ)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копировать точку входа (скрипт для миграций и запуска)
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Копировать весь проект в рабочую директорию
COPY . .

# Собрать статические файлы Django
# Пользователь www-data (стандартный для nginx/apache) должен иметь доступ к этим файлам
# Создадим пользователя appuser для запуска Gunicorn/бота
RUN addgroup --system app && adduser --system --ingroup app appuser

# Создаем директории для статики и медиа и назначаем права
# STATIC_ROOT и MEDIA_ROOT должны совпадать с путями в settings.py
RUN mkdir -p /Sphinx/staticfiles /Sphinx/mediafiles && \
    chown -R appuser:app /Sphinx/staticfiles /Sphinx/mediafiles

# Собираем статику от имени root, т.к. у appuser может не быть прав на запись везде
RUN python manage.py collectstatic --noinput

# Меняем пользователя на непривилегированного
USER appuser

# Точка входа будет выполнять миграции и затем запускать команду (CMD)
ENTRYPOINT ["/entrypoint.sh"]

# Команда по умолчанию (может быть переопределена в docker-compose)
# CMD ["gunicorn", "your_project_name.wsgi:application", "--bind", "0.0.0.0:8000"]
# Вместо your_project_name подставьте имя вашего Django проекта (где находится wsgi.py)