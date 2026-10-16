from __future__ import annotations

from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.research.exceptions import InvalidRunState, ResearchError
from apps.research.services import create_and_enqueue_backtest
from trading.strategies.registry import available_strategies


class Command(BaseCommand):
    help = (
        "Create a BacktestRun and enqueue it on Celery (does not block). "
        f"Strategies: {', '.join(available_strategies())}"
    )

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--strategy", default="rsi_macd_stoch")
        parser.add_argument("--interval", default="4h")
        parser.add_argument("--start", default=None)
        parser.add_argument("--end", default=None)
        parser.add_argument("--name", default="")
        parser.add_argument("--fee-rate", type=float, default=0.00045)
        parser.add_argument("--slippage-rate", type=float, default=0.0)
        parser.add_argument("--tp-sl-ratio", type=float, default=1.5)
        parser.add_argument("--sl-limit", type=float, default=0.10)
        parser.add_argument("--notional", type=float, default=100.0)
        parser.add_argument("--no-trailing", action="store_true")
        parser.add_argument("--open-rsi", type=float, default=5.0)

    def handle(self, *args, **options):
        start = _parse_dt(options["start"]) if options["start"] else None
        end = _parse_dt(options["end"]) if options["end"] else None
        try:
            run = create_and_enqueue_backtest(
                symbol=options["symbol"],
                strategy_id=options["strategy"],
                timeframe=options["interval"],
                name=options["name"],
                strategy_params={"open_rsi": options["open_rsi"]},
                execution={
                    "fee_rate": options["fee_rate"],
                    "slippage_rate": options["slippage_rate"],
                    "tp_sl_ratio": options["tp_sl_ratio"],
                    "sl_limit": options["sl_limit"],
                    "position_notional": options["notional"],
                    "enable_trailing": not options["no_trailing"],
                },
                data_start=start,
                data_end=end,
            )
        except (ResearchError, KeyError, TypeError, InvalidRunState) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Enqueued BacktestRun id={run.pk} status={run.status} "
                f"task_id={run.celery_task_id or '(eager/local)'}"
            )
        )
        self.stdout.write("Ensure a Celery worker is running, then: python manage.py list_backtests")


def _parse_dt(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts
