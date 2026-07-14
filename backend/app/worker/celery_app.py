from celery import Celery

from app.config import settings

celery_app = Celery(
    "arachnin",
    broker=settings.broker_url,
    backend=settings.result_backend_url,
    include=["app.worker.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    worker_enable_remote_control=False,
    worker_cancel_long_running_tasks_on_connection_loss=True,
)
