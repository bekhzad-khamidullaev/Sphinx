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
