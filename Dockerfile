FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PATH="/home/djangoapp/.local/bin:${PATH}"

RUN groupadd -r djangoapp && useradd -r -g djangoapp -d /home/djangoapp -s /sbin/nologin -c "Django App User" djangoapp
RUN mkdir /home/djangoapp && chown djangoapp:djangoapp /home/djangoapp

RUN apt-get update \
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN python manage.py collectstatic --noinput --clear

RUN mkdir -p /app/mediafiles && chown -R djangoapp:djangoapp /app/mediafiles

RUN chown -R djangoapp:djangoapp /app

USER djangoapp

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]