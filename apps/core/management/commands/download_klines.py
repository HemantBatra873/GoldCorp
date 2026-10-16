from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Symbol
from trading.marketdata.binance import INTERVAL_MS, fetch_klines
from trading.marketdata.quality import validate_ohlcv
from trading.marketdata.candles import candles_to_frame
from trading.marketdata.store import csv_path, upsert_candles


class Command(BaseCommand):
    help = "Download Binance USD-M Futures klines into data/ohlcv (public API)."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument(
            "--interval",
            default="4h",
            choices=sorted(INTERVAL_MS),
            help="Kline interval",
        )
        parser.add_argument("--start", default=None, help="UTC start ISO8601")
        parser.add_argument("--end", default=None, help="UTC end ISO8601")
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Max candles when no start/end (single page, max 1500)",
        )

    def handle(self, *args, **options):
        symbol = options["symbol"].upper()
        interval = options["interval"]
        start = _parse_dt(options["start"]) if options["start"] else None
        end = _parse_dt(options["end"]) if options["end"] else None

        self.stdout.write(f"Fetching {symbol} {interval}...")
        try:
            candles = fetch_klines(
                symbol,
                interval,
                start=start,
                end=end,
                limit=options["limit"],
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        if not candles:
            raise CommandError("No candles returned from Binance")

        df = candles_to_frame(candles)
        report = validate_ohlcv(df, expected_freq=_freq_for(interval))
        if not report.ok:
            raise CommandError("; ".join(report.messages))

        path = csv_path(symbol, interval, directory=settings.BASE_DIR / "data" / "ohlcv")
        merged = upsert_candles(path, candles)
        Symbol.objects.update_or_create(
            symbol=symbol,
            defaults={
                "base_asset": symbol.replace("USDT", "") if symbol.endswith("USDT") else "",
                "quote_asset": "USDT" if symbol.endswith("USDT") else "",
                "is_active": True,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Saved {len(merged)} candles to {path} "
                f"({report.gap_count} gap warning(s))"
            )
        )


def _parse_dt(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _freq_for(interval: str) -> str:
    mapping = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }
    return mapping[interval]
