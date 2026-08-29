"""Best-effort queue dispatch backed by durable accepted batch rows."""

import logging
from uuid import UUID

from apps.workers.celery_app import app as celery_app

logger = logging.getLogger(__name__)


def enqueue_import_batch(batch_id: UUID) -> None:
    """Dispatch processing; recovery can safely replay this if Redis is unavailable."""

    try:
        celery_app.send_task("barcodes.process_import_batch", args=[str(batch_id)])
    except Exception:
        logger.exception(
            "Could not enqueue accepted batch; recovery must replay it",
            extra={"event_name": "ingest.enqueue_failed"},
        )
