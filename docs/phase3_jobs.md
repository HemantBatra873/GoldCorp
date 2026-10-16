# Phase 3 — Jobs & run lifecycle

Backtests must not block HTTP. Phase 3 wires the Phase 2 engine to Celery.

## Lifecycle

```text
queued → running → completed
                 → failed
queued|running → cancelled
failed → queued (re-enqueue)
```

## Services (`apps.research.services`)

| Function | Role |
|----------|------|
| `create_backtest_run` | Persist immutable `config.request` as `queued` |
| `enqueue_backtest_run` | Celery `execute_backtest_run_task.delay` |
| `create_and_enqueue_backtest` | Create + enqueue |
| `execute_backtest_run` | Sync engine execution (worker / tests) |
| `cancel_backtest_run` | Cancel + optional Celery revoke |
| `assert_can_access` / `get_run` | Ownership checks |
| `compare_runs` | Side-by-side metrics |

## Commands

```bash
python manage.py enqueue_backtest --symbol BTCUSDT --strategy rsi_macd_stoch
python manage.py list_backtests
python manage.py compare_backtests 1 2
python manage.py cancel_backtest 3
python manage.py run_backtest --symbol BTCUSDT --async
```

Worker (Windows):

```bash
celery -A config worker -l INFO --pool=solo
```

## Task

`apps.research.tasks.execute_backtest_run_task` — retries unexpected errors (max 2); data errors fail the run immediately.
