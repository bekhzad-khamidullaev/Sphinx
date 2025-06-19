#!/bin/bash
set -e

# Update system and install packages
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential libpq-dev nginx git

# Create project directory
sudo mkdir -p /opt/sphinx
sudo rsync -a --exclude 'deploy' ./ /opt/sphinx/

cd /opt/sphinx
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files and apply migrations
python manage.py migrate
python manage.py collectstatic --noinput

sudo cp deploy/ubuntu24/gunicorn.service /etc/systemd/system/gunicorn.service
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn

sudo cp deploy/ubuntu24/nginx.conf /etc/nginx/sites-available/sphinx.conf
sudo ln -sf /etc/nginx/sites-available/sphinx.conf /etc/nginx/sites-enabled/

sudo systemctl restart nginx
