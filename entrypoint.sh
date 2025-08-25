#!/bin/sh

echo "✅ Making migrations..."
python manage.py makemigrations  # Removed --noinput

echo "✅ Applying database migrations..."
python manage.py migrate --noinput

echo "✅ Populating app models..."
python manage.py populate_app_models || echo "⚠️ populate_app_models failed (maybe already populated)"

echo "🚀 Starting Gunicorn server..."
exec gunicorn HMS.wsgi:application --bind 0.0.0.0:8000
