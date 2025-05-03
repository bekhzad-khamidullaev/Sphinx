#!/bin/sh
# Exit immediately if a command exits with a non-zero status.
set -e

# Function to check PostgreSQL readiness
wait_for_db() {
    # Check if required DB variables are set
    if [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_DB" ]; then
        echo "Warning: Database connection variables (DB_HOST, DB_PORT, POSTGRES_USER, POSTGRES_DB) are not fully set. Skipping DB wait check."
        sleep 5 # Short sleep as fallback
        return 0
    fi

    echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."

    # Prefer pg_isready if available (requires postgresql-client package in Docker image)
    if command -v pg_isready > /dev/null 2>&1; then
        # Loop until pg_isready exits with status 0 (success)
        # Use PGPASSWORD if password is required for connection check (often not needed for pg_isready check itself)
        while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q; do
          >&2 echo "Postgres is unavailable - sleeping"
          sleep 1
        done
    # Fallback to netcat if pg_isready is not available (requires netcat-openbsd or similar)
    elif command -v nc > /dev/null 2>&1; then
         while ! nc -z $DB_HOST $DB_PORT; do
           echo "Waiting for DB via netcat ($DB_HOST:$DB_PORT)..."
           sleep 1
         done
    else
        echo "Warning: Neither 'pg_isready' nor 'nc' command found. Cannot check DB status. Sleeping briefly..."
        sleepOkay, here are the final versions of the core deployment files (`Dockerfile`, `.dockerignore`, `entrypoint.sh`, `docker-compose.prod.yml`, and `nginx/nginx.conf`), incorporating best practices and the necessary changes for a production deployment using Gunicorn/Uvicorn, Nginx, PostgreSQL, Redis (optional but recommended), and Certbot.

**Remember to:**

1.  Replace placeholders like `your_domain.com`, `your_email@example.com`, `YourStrongP0stgr3sPassw0rd`, and other secrets in `.env` and `nginx.conf`.
2.  Ensure your Django `settings.py` correctly reads these variables from the environment (using `django-environ` as shown previously is recommended).
3.  Adjust the Python version (e.g., `3.11-slim`) in the `Dockerfile` if necessary.
4.  Uncomment Redis/Celery sections if you are using them.
5.  Install `postgresql-client` in the runtime stage of the `Dockerfile` for the `pg_isready` healthcheck.

---

**1. `Dockerfile` (Multi-stage Production Version)**

```dockerfile
# Dockerfile

# --- Stage 1: Builder ---
# Use an official Python runtime matching your development environment
FROM python:3.11-slim-bullseye as builder

# Prevent Python from writing pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Add user's local bin to PATH for packages installed with --user
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Create non-root user and group first
RUN addgroup --system appgroup && adduser --system --ingroup appgroup --no-create-home appuser

# Set work directory
WORKDIR /app

# Install system build dependencies
# Required for psycopg2, potential C extensions in other packages, gettext for i18n
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gettext \
    # Add other build dependencies if needed (e.g., libjpeg-dev zlib1g-dev libwebp-dev)
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
# Switch to the app user BEFORE installing packages with --user flag
USER appuser
RUN pip install --no-cache-dir --upgrade pip

# Install Python dependencies
# Copy requirements first to leverage Docker cache
COPY --chown=appuser:appgroup requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.11-slim-bullseye as runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE=config.settings # Adjust 'config' if needed
ENV ASGI_APPLICATION=config.asgi:application # Adjust 'config' if needed
ENV PATH="/home/appuser/.local/bin:${PATH}" # Ensure user's bin is in PATH

# Set work directory
WORKDIR /app

# Install only runtime system dependencies
# libpq5: PostgreSQL client library
# gettext: Runtime i18n support
# postgresql-client: Includes pg_isready for healthcheck (recommended over netcat)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gettext \
    postgresql-client \
    # Add runtime libs for Pillow etc. if needed (e.g., libjpeg62-turbo libwebp7)
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN addgroup --system appgroup && adduser --system --ingroup appgroup -- 5 # Fallback sleep
    fi
    echo "PostgreSQL started on $DB_HOST:$DB_PORT"
}

# Function to check Redis readiness (Optional)
wait_for_redis() {
    # Check if REDIS_HOST/PORT are set in the environment
    if [ -z "$REDIS_HOST" ] || [ -z "$REDIS_PORT" ]; then
        echo "Redis host/port not configured, skipping wait."
        return 0
    fi

    echo "Waiting for Redis at $REDIS_HOST:$REDIS_PORT..."
    # Prefer redis-cli if available (requires redis-tools package)
    if command -v redis-cli > /dev/null 2>&1; then
        # Loop until ping returns PONG
        until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping | grep -q 'PONG'; do
          >&2 echo "Redis is unavailable - sleeping"
          sleep 1
        done
    # Fallback to netcat
    elif command -v nc > /dev/null 2>&1; then
        while ! nc -z $REDIS_HOST $REDIS_PORT; do
          echo "Waiting for Redis via netcat ($REDIS_HOST:$REDIS_PORT)..."
          sleep 1
        done
    else
         echo "Warning: Neither 'redis-cli' nor 'nc' command found. Cannot check Redis status. Sleeping briefly..."
         sleep 3
    fi
    echo "Redis started on $REDIS_HOST:$REDIS_PORT"
}


# Wait for primary services
wait_for_db
wait_for_redis # Call this if Redis service is enabled in compose file

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Compile translation messages (optional, uncomment if needed)
# echo "Compiling translation messages..."
# python manage.py compilemessages --locale=ru --locale=en --locale=uz # Specify locales

# Start the main process (passed as CMD in Dockerfile or command in docker-compose)
# "$@" executes the command passed to the entrypoint (e.g., gunicorn ...)
echo "Starting server process: $@"
exec "$@"