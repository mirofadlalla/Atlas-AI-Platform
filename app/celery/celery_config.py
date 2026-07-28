from celery import Celery
from kombu import Exchange, Queue
import os

celery_app = Celery(
    "atlas_ai", 
    broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "rpc://"),  # RabbitMQ backend
)

# Prodcer -> Exchange -> Queue -> Worker 

default_exchange = Exchange("atlas_ai_exchange" , type="direct")

# define queus
celery_app.conf.task_queues = (
    Queue("ingest_data_queue" , default_exchange , routing_key="ingest"),
    Queue("eval_data_queue" , default_exchange , routing_key="eval"),
    Queue("logging_queue" , default_exchange , routing_key="logging"),
    Queue("queue_dead" , default_exchange , routing_key="dead"),
)

celery_app.conf.task_default_queue = "logging_queue"
celery_app.conf.task_default_exchange = "atlas_ai_exchange"
celery_app.conf.task_default_routing_key = "logging"

# define when task cames which queue and routes should go 
celery_app.conf.task_routes = {
    "app.services.rag_services.ingest_rag_service.ingest_file_task": {
        "queue": "ingest_data_queue",
        "routing_key": "ingest",
    },
    "app.services.rag_services.eval_pipline.evaluate_task": {
        "queue": "eval_data_queue",
        "routing_key": "eval",
    },
    "app.services.rag_services.eval_pipline.generate_eval_dataset_task": {
        "queue": "eval_data_queue",
        "routing_key": "eval",
    },
    "app.services.rag_services.query_logging_service.log_query_run_and_cost": {
        "queue": "logging_queue",
        "routing_key": "logging",
    },
}

# =========================
# SERIALIZATION
# =========================
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    
    # =========================
    # WORKER POOL SETTINGS
    # =========================
    worker_pool="threads",  # Use threads instead of prefork for better Windows compatibility
    worker_max_tasks_per_child=10,  # Restart worker after 10 tasks to free memory
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_disable_rate_limits=False,

    # =========================
    # TIME LIMITS
    # =========================
    task_soft_time_limit=550,  # 9 min 10 sec
    task_time_limit=600,       # 10 min

    # =========================
    # RETRIES & ACKS
    # =========================
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_max_retries=3,

    # =========================
    # TRACKING
    # =========================
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.services"])