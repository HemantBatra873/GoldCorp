"""Celery tasks for research workloads."""

from __future__ import annotations

import logging

from celery import shared_task

from apps.research.exceptions import BacktestDataError, InvalidRunState
from apps.research.models import BacktestRun, RunStatus
from apps.research.services import execute_backtest_run, mark_run_failed

logger = logging.getLogger("goldcorp.research")


@shared_task(
    bind=True,
    name="apps.research.tasks.execute_backtest_run_task",
    max_retries=2,
    default_retry_delay=10,
    acks_late=True,
)
def execute_backtest_run_task(self, run_id: int) -> dict:
    """
    Worker entrypoint: run the trading engine for a BacktestRun.

    Long jobs stay off the web process. Retries only for unexpected failures;
    data/config errors fail the run immediately.
    """
    logger.info("backtest task start run_id=%s task_id=%s", run_id, self.request.id)
    try:
        run = BacktestRun.objects.filter(pk=run_id).first()
        if run is None:
            logger.error("backtest run %s missing", run_id)
            return {"run_id": run_id, "status": "missing"}

        if run.status == RunStatus.CANCELLED:
            return {"run_id": run_id, "status": RunStatus.CANCELLED}

        # Keep task id on the row for revoke/cancel UX
        if self.request.id and run.celery_task_id != self.request.id:
            BacktestRun.objects.filter(pk=run_id).update(celery_task_id=self.request.id)

        completed = execute_backtest_run(run_id)
        return {
            "run_id": completed.pk,
            "status": completed.status,
            "total_trades": completed.total_trades,
            "total_pnl": str(completed.total_pnl),
            "config_hash": completed.config_hash,
        }
    except BacktestDataError as exc:
        mark_run_failed(run_id, str(exc))
        logger.warning("backtest data error run_id=%s: %s", run_id, exc)
        return {"run_id": run_id, "status": RunStatus.FAILED, "error": str(exc)}
    except InvalidRunState as exc:
        logger.warning("backtest invalid state run_id=%s: %s", run_id, exc)
        return {"run_id": run_id, "status": "skipped", "error": str(exc)}
    except Exception as exc:
        logger.exception("backtest failed run_id=%s", run_id)
        if self.request.retries >= self.max_retries:
            mark_run_failed(run_id, f"{type(exc).__name__}: {exc}")
            return {"run_id": run_id, "status": RunStatus.FAILED, "error": str(exc)}
        raise self.retry(exc=exc)
