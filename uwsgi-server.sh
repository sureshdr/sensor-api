#!/bin/bash
VENV_PATH="/var/www/diab.drsuresh.net/sensor-api/venv"
APP_PATH="/var/www/diab.drsuresh.net/sensor-api"
PID_FILE="$APP_PATH/uwsgi.pid"

case "$1" in
  start)
    echo "Starting uWSGI for Diabetes-API..."
    cd $APP_PATH
    $VENV_PATH/bin/uwsgi --ini uwsgi.ini --pidfile $PID_FILE --daemonize $APP_PATH/logs/uwsgi.log
    ;;
  stop)
    echo "Stopping uWSGI for Diabetes-API..."
    if [ -f $PID_FILE ]; then
      kill -INT `cat $PID_FILE`
      rm $PID_FILE
    else
      echo "No PID file found for uWSGI Diabetes-API"
    fi
    ;;
  restart)
    $0 stop
    sleep 2
    $0 start
    ;;
  *)
    echo "Usage: $0 {start|stop|restart}"
    exit 1
    ;;
esac

exit 0

