"""Celery application factory for Server 1 background jobs."""

import os

from celery import Celery


def create_celery_app() -> Celery:
    """Create the worker app without importing business tasks prematurely."""

    broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis_server1:6379/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis_server1:6379/1")
    worker = Celery("barcodes-workers", broker=broker_url, backend=result_backend)
    worker.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )
    return worker


app = create_celery_app()
