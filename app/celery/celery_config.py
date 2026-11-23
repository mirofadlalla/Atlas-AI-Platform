from celery import Celery
from kombu import Exchange, Queue
import os

celery_app = Celery(
    "atlas_ai",
    broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "rpc://"),  # RabbitMQ backend
)

# Producer -> Exchange -> Queue -> Worker

default_exchange = Exchange("atlas_ai_exchange", type="direct")

# define queues
celery_app.conf.task_queues = (
    Queue("ingest_data_queue", default_exchange, routing_key="ingest"),
    Queue("eval_data_queue", default_exchange, routing_key="eval"),
    Queue("logging_queue", default_exchange, routing_key="logging"),
    Queue("queue_dead", default_exchange, routing_key="dead"),
)

# define default queue and routing key
celery_app.conf.task_default_queue = "logging_queue"
celery_app.conf.task_default_exchange = "atlas_ai_exchange"
celery_app.conf.task_default_routing_key = "logging"

# define when task cames which queue and routes should go
celery_app.conf.task_routes = {
    "app.services.rag_services.ingest_rag_service.ingest_file_task": { # لما task اسمها ingest_file_task تتبعت، ودّيها للـ queue دي.
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
    "app.services.semantic_memory_service.extract_semantic_memory": {
        "queue": "logging_queue",
        "routing_key": "logging",
    },
    "app.services.semantic_memory_service.prune_low_importance_semantic_memories": {
        "queue": "logging_queue",
        "routing_key": "logging",
    },
    "app.services.episodic_memory_service.write_episode": {
        "queue": "logging_queue",
        "routing_key": "logging",
    },
    "app.services.email_service.send_email_task": {
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
    task_time_limit=600,  # 10 min
    # =========================
    # RETRIES & ACKS
    # أفكر لحظة. آه، الفكرة كده بس محتاجة تصحيح بسيط. الـ task مش بتبقى في الـ queue بعد ما تتسلم للـ worker، بتبقى unacknowledged عنده. لو الـ worker مات الـ RabbitMQ يكتشف إن الكونكشن اتقطع وساعتها يعمل لها redelivery لworker تاني، وده اللي بيساعد عليه task_reject_on_worker_lost=True. ومن غير acks_late=True الرسالة ممكن تتشال من الـ queue بدري قبل ما التنفيذ يخلص، وده خطر لأنه ممكن يسبب فقدان شغل فعلي.

    # الخلاصة: الإعدادتين دول بيخلّوا الإعادة ممكنة وبيحسّنوا الاعتمادية، بس الاعتمادية الكاملة برضو مسؤوليتك أنت.
    #      # =========================
    task_acks_late=True, # Acknowledge tasks after they have been executed, not just received because if the worker crashes before executing the task, it will be re-queued and executed by another worker.
    task_reject_on_worker_lost=True, # If a worker crashes while executing a task, the task will be re-queued and executed by another worker.
    task_default_retry_delay=30,
    task_max_retries=3,
    # =========================
    # TRACKING
    # =========================
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)
'''
    timezone="UTC" => all the backend infrastructure will work in UTC timezone, and the frontend will convert to the user's timezone. This is important because we have different components in different regions:
    EC2 → Egypt
    Worker → Germany
    Database → another region

    بدل مشاكل:

    15:00 Egypt
    14:00 UTC
    16:00 ...

    تخلي كل الـ backend infrastructure يتعامل بـ:

    UTC

    والـ frontend يحول للـ user's timezone.
'''

celery_app.autodiscover_tasks(["app.services"])
# Explicitly register all task modules so Celery workers discover and register them
celery_app.conf.imports = (
    "app.services.semantic_memory_service",
    "app.services.episodic_memory_service",
    "app.services.rag_services.query_logging_service",
    "app.services.rag_services.eval_pipline",
    "app.services.rag_services.ingest_rag_service",
    "app.services.email_service",
)

# scheduled task like every 24 hours do that
celery_app.conf.beat_schedule = {
    "prune-low-importance-semantic-memories-nightly": {
        "task": "app.services.semantic_memory_service.prune_low_importance_semantic_memories",
        "schedule": 24 * 60 * 60,
    }
}
