from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "finiq_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.services.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "sweep-pending-documents-every-5-min": {
        "task": "app.services.tasks.sweep_pending_documents",
        "schedule": 300.0,
    }
}

# Automatically discover tasks in specified packages
celery_app.autodiscover_tasks(["app.services"])
