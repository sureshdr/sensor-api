import multiprocessing

bind="0.0.0.0:5001"

workers = multiprocessing.cpu_count() * 2 + 1

worker_class = "sync"

timeout = 30

graceful_timeout = 30

max_requests = 100
max_requests_jitter = 20

errorlog = "logs/gunicorn-error.log"
accesslog = "logs/gunicorn-access.log"

loglevel = "info"

proc_name = "sensor_api"

user = "suresh" 
group = "suresh"

daemon = False



