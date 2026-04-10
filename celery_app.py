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

# Beat schedule
celery.conf.beat_schedule = {
    "weekly-discovery-sweep": {
        "task": "app.tasks.scraping_tasks.weekly_discovery_sweep",
        "schedule": crontab(hour=2, minute=0, day_of_week="monday"),
    },
}
