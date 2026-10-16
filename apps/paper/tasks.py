"""Celery tasks for paper trading entry/exit loops."""

from __future__ import annotations

import logging

from celery import shared_task

from apps.paper.models import PaperSession
from apps.paper.services import heartbeat, manage_exits_for_session, scan_entries_for_session

logger = logging.getLogger("goldcorp.paper")


@shared_task(name="apps.paper.tasks.paper_heartbeat")
def paper_heartbeat() -> dict:
    active = list(PaperSession.objects.filter(is_active=True))
    for session in active:
        heartbeat(session)
    return {"sessions": len(active)}


@shared_task(name="apps.paper.tasks.paper_entry_scan")
def paper_entry_scan() -> dict:
    results = []
    for session in PaperSession.objects.filter(is_active=True):
        try:
            results.append({"session_id": session.pk, **scan_entries_for_session(session)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("paper_entry_scan failed session=%s", session.pk)
            results.append({"session_id": session.pk, "error": str(exc)})
    return {"results": results}


@shared_task(name="apps.paper.tasks.paper_exit_scan")
def paper_exit_scan() -> dict:
    results = []
    for session in PaperSession.objects.filter(is_active=True):
        try:
            results.append({"session_id": session.pk, **manage_exits_for_session(session)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("paper_exit_scan failed session=%s", session.pk)
            results.append({"session_id": session.pk, "error": str(exc)})
    return {"results": results}
