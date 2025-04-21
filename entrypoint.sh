#!/bin/sh

# Выход при любой ошибке
set -e

echo "Waiting for database..."
# Простая проверка доступности хоста и порта БД (замените на более надежную, если нужно)
# Это для PostgreSQL, адаптируйте для MySQL
# nc -z -v -w30 $SQL_HOST $SQL_PORT # nc может быть не установлен

# Простой sleep, менее надежно, но часто достаточно для старта
# Увеличьте время, если БД стартует долго
sleep 10

echo "Applying database migrations..."
python manage.py migrate --noinput

# echo "Creating superuser if not exists..." # Опционально
# python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists() or User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')"

echo "Database migrations applied."

# Запуск команды, переданной в CMD Dockerfile или в docker-compose
exec "$@"