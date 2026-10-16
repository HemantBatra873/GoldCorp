import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger("goldcorp.core")


@require_GET
def health(request):
    """Liveness/readiness style health check for Docker and deploy platforms."""
    db_ok = False
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        logger.exception("health check: database unavailable")

    status_code = 200 if db_ok else 503
    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "service": "goldcorp",
        },
        status=status_code,
    )
