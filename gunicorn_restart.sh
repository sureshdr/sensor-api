#!/bin/bash

APPDIR=/var/www/diab.drsuresh.net/web/sensor-api

echo "Restarting Gunicorn for Diab-API..."
$APPDIR/gunicorn_stop.sh
sleep 2
$APPDIR/gunicorn_start.sh
echo "Gunicorn for Diab=API restarted"
