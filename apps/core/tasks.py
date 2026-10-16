import logging

from celery import shared_task

logger = logging.getLogger("goldcorp.core")


@shared_task(name="apps.core.tasks.heartbeat")
def heartbeat():
    """Lightweight Beat task to confirm Celery scheduling is alive."""
    logger.info("goldcorp heartbeat ok")
    return "ok"
