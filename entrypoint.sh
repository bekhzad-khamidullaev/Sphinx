#!/bin/sh
set -e

wait_for_db() {
    if [ -z "$SQL_HOST" ] || [ -z "$SQL_PORT" ] || [ -z "$SQL_USER" ] || [ -z "$SQL_DATABASE" ]; then
        echo "Warning: Database connection variables not fully set. Skipping DB wait check."
        sleep 5
        return 0
    fi
    echo "Waiting for PostgreSQL at $SQL_HOST:$SQL_PORT..."
    if command -v pg_isready > /dev/null 2>&1; then
        while ! pg_isready -h "$SQL_HOST" -p "$SQL_PORT" -U "$SQL_USER" -d "$SQL_DATABASE" -q; do
          >&2 echo "Postgres is unavailable - sleeping"
          sleep 1
        done
    elif command -v nc > /dev/null 2>&1; then
         while ! nc -z "$SQL_HOST" "$SQL_PORT"; do
           echo "Waiting for DB via netcat ($SQL_HOST:$SQL_PORT)..."
           sleep 1
         done
    else
        echo "Warning: Neither 'pg_isready' nor 'nc' found. Cannot check DB status. Sleeping..."
        sleep 10
    fi
    echo "PostgreSQL started on $SQL_HOST:$SQL_PORT"
}

wait_for_redis() {
    if [ -n "$REDIS_URL" ]; then
        REDIS_HOST_PARSED=$(echo "$REDIS_URL" | sed -n 's_redis://\([^:/]*\).*_\1_p')
        REDIS_PORT_PARSED=$(echo "$REDIS_URL" | sed -n 's_redis://[^:/]*:\?\([^/]*\).*_\1_p')
        if [ -z "$REDIS_PORT_PARSED" ]; then REDIS_PORT_PARSED=6379; fi

        if [ -z "$REDIS_HOST_PARSED" ]; then
             echo "Warning: Could not parse Redis host from REDIS_URL. Skipping Redis wait."
             sleep 3; return 0
        fi
    else
        echo "Redis URL not configured, skipping wait."
        return 0
    fi
    echo "Waiting for Redis at $REDIS_HOST_PARSED:$REDIS_PORT_PARSED..."
    if command -v redis-cli > /dev/null 2>&1; then
        until redis-cli -h "$REDIS_HOST_PARSED" -p "$REDIS_PORT_PARSED" ping | grep -q 'PONG'; do
          >&2 echo "Redis is unavailable - sleeping"
          sleep 1
        done
    elif command -v nc > /dev/null 2>&1; then
        while ! nc -z "$REDIS_HOST_PARSED" "$REDIS_PORT_PARSED"; do
          echo "Waiting for Redis via netcat ($REDIS_HOST_PARSED:$REDIS_PORT_PARSED)..."
          sleep 1
        done
    else
         echo "Warning: Neither 'redis-cli' nor 'nc' found. Sleeping briefly..."
         sleep 5
    fi
    echo "Redis started on $REDIS_HOST_PARSED:$REDIS_PORT_PARSED"
}

wait_for_db
wait_for_redis

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Compiling translation messages..."
python manage.py compilemessages --locale=ru --locale=en --locale=uz || echo "Compilemessages failed or no messages to compile."

if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_EMAIL" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "Checking/creating superuser '$DJANGO_SUPERUSER_USERNAME'..."
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print('Superuser \"$DJANGO_SUPERUSER_USERNAME\" created.')
else:
    print('Superuser \"$DJANGO_SUPERUSER_USERNAME\" already exists.')
"
else
    echo "Superuser creation skipped (DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, or DJANGO_SUPERUSER_PASSWORD not set)."
fi

echo "Starting server process: $@"
exec "$@"