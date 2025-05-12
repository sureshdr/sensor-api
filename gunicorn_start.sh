#!/bin/bash

NAME="sensor_app"
APPDIR=/var/www/diab.drsuresh.net/web/sensor-api
SOCKFILE=$APPDIR/gunicorn.sock
USER=www-data  # The user Nginx runs as (typically www-data)
GROUP=www-data  # The group Nginx runs as (typically www-data)
NUM_WORKERS=3  # Recommended: 2 * CPUs + 1
TIMEOUT=120

echo "Starting Gunicorn - Diab-API..."
# Activate the virtual environment
cd $APPDIR
source venv/bin/activate

# Create the socket directory if it doesn't exist
mkdir -p $(dirname $SOCKFILE)

# Start Gunicorn
exec venv/bin/gunicorn app:app \
  --name $NAME \
  --workers $NUM_WORKERS \
  --timeout $TIMEOUT \
  --bind=unix:$SOCKFILE \
  --log-level=debug \
  --log-file=$APPDIR/logs/gunicorn.log \
  --pid=$APPDIR/gunicorn.pid \
  --daemon

echo "Gunicorn - Diab-API started!"
