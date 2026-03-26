from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "rayna_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Auto-discover task modules
celery.autodiscover_tasks(["app.tasks"])

# Beat schedule — add periodic jobs here
celery.conf.beat_schedule = {
    # Example:
    # "daily-product-sync": {
    #     "task": "app.tasks.sync.sync_all_products",
    #     "schedule": crontab(hour=3, minute=0),
    # },
}
