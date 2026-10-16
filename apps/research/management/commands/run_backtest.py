from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.exceptions import ResearchError
from apps.research.services import create_and_enqueue_backtest, persist_backtest_result
from trading.backtest.engine import Backtester, execution_config_from_dict
from trading.marketdata.store import csv_path, load_candles
from trading.strategies.registry import available_strategies, create_strategy


class Command(BaseCommand):
    help = (
        "Run a backtest via the pure trading engine and persist results. "
        "Use --async to enqueue on Celery instead of blocking. "
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
        parser.add_argument("--no-persist", action="store_true")
        parser.add_argument("--open-rsi", type=float, default=5.0)
        parser.add_argument(
            "--async",
            dest="async_enqueue",
            action="store_true",
            help="Enqueue on Celery (non-blocking). Prefer: enqueue_backtest",
        )

    def handle(self, *args, **options):
        if options["async_enqueue"]:
            if options["no_persist"]:
                raise CommandError("--async cannot be combined with --no-persist")
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
            except (ResearchError, KeyError, TypeError) as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(
                self.style.SUCCESS(
                    f"Enqueued BacktestRun id={run.pk} task_id={run.celery_task_id}"
                )
            )
            return

        symbol = options["symbol"].upper()
        interval = options["interval"]
        path = csv_path(symbol, interval, directory=settings.BASE_DIR / "data" / "ohlcv")
        if not path.exists():
            raise CommandError(
                f"No data at {path}. Run: python manage.py download_klines --symbol {symbol}"
            )

        try:
            candles = load_candles(path)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        start = _parse_dt(options["start"]) if options["start"] else None
        end = _parse_dt(options["end"]) if options["end"] else None

        try:
            strategy = create_strategy(
                options["strategy"],
                open_rsi=options["open_rsi"],
            )
        except KeyError as exc:
            raise CommandError(str(exc)) from exc

        execution = execution_config_from_dict(
            {
                "fee_rate": options["fee_rate"],
                "slippage_rate": options["slippage_rate"],
                "tp_sl_ratio": options["tp_sl_ratio"],
                "sl_limit": options["sl_limit"],
                "position_notional": options["notional"],
                "enable_trailing": not options["no_trailing"],
            }
        )

        result = Backtester(strategy, execution).run(
            candles,
            symbol=symbol,
            timeframe=interval,
            start=start,
            end=end,
        )

        metrics = result.metrics
        self.stdout.write(
            f"{result.strategy_id}@{result.strategy_version} {symbol} {interval}\n"
            f"config_hash={result.config_hash[:12]}... engine={result.engine_version}\n"
            f"trades={metrics.total_trades} pnl={metrics.total_pnl:.4f} "
            f"win_rate={metrics.win_rate} max_dd={metrics.max_drawdown}"
        )
        for note in result.notes:
            self.stdout.write(self.style.WARNING(note))

        if options["no_persist"]:
            self.stdout.write("Skipped DB persistence (--no-persist)")
            return

        run = persist_backtest_result(result, name=options["name"])
        self.stdout.write(self.style.SUCCESS(f"Persisted BacktestRun id={run.pk}"))


def _parse_dt(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts
