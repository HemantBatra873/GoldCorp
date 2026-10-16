from django.core.management.base import BaseCommand

from apps.research.models import BacktestRun


class Command(BaseCommand):
    help = "List recent backtest runs and their lifecycle status."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--status", default=None)

    def handle(self, *args, **options):
        qs = BacktestRun.objects.select_related("symbol").order_by("-created_at")
        if options["status"]:
            qs = qs.filter(status=options["status"])
        qs = qs[: options["limit"]]

        if not qs:
            self.stdout.write("No backtest runs found.")
            return

        for run in qs:
            symbol = run.symbol.symbol if run.symbol_id else "-"
            self.stdout.write(
                f"#{run.pk:>4}  {run.status:<10}  {run.strategy_id:<18}  "
                f"{symbol:<12}  trades={run.total_trades:<4}  "
                f"pnl={run.total_pnl}  hash={run.config_hash[:8] or '-'}"
            )
