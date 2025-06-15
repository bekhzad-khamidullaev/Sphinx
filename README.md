# ServiceDesk API

This project provides a REST API built with Django and DRF.

## Quick start

```bash
pip install -r requirements.txt
python manage.py migrate

python manage.py createsuperuser  # optional
python manage.py runserver
```

- Obtain a token via `POST /api/token/` with username and password.
- Refresh token via `POST /api/token/refresh/`.
- Register new user via `POST /api/register/`.

Access Swagger UI at `/swagger/`.

## Troubleshooting migrations

If `python manage.py migrate` fails with an error like `duplicate column name`, it may indicate that a migration was applied manually or outside of Django's migration history. You can mark the migration as already applied using the `--fake` option. For example:

```bash
python manage.py migrate room 0002 --fake
```

Repeat for any other app showing the same error, then run `python manage.py migrate` again.
