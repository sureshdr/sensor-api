#!/bin/bash

APPDIR=/var/www/diab.drsuresh.net/web/sensor-api
PID_FILE=$APPDIR/gunicorn.pid

if [ -f $PID_FILE ]; then
    echo "Stopping Gunicorn for Diab-API..."
    kill -TERM $(cat $PID_FILE)
    rm -f $PID_FILE
    echo "Gunicorn for Diab-API stopped"
else
    echo "Gunicorn for Diab-API is not running (no PID file)"
fi
