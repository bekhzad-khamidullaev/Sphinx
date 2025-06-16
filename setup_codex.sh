#!/usr/bin/env bash
# Script to set up the Sphinx project for use in a Codex environment
# It installs Python and Node dependencies and applies migrations.
set -e

# Create Python virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# Upgrade pip and install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Node dependencies if npm is available
if command -v npm >/dev/null 2>&1; then
    npm install
fi

# Run Django migrations
python manage.py migrate

echo "Setup complete."
