from django.core.management.base import BaseCommand, CommandError

from apps.research.exceptions import OwnershipError
from apps.research.models import BacktestRun
from apps.research.services import compare_runs


class Command(BaseCommand):
    help = "Compare metrics for two or more BacktestRun ids."

    def add_arguments(self, parser):
        parser.add_argument("run_ids", nargs="+", type=int)

    def handle(self, *args, **options):
        ids = options["run_ids"]
        if len(ids) < 2:
            raise CommandError("Provide at least two run ids")
        try:
            rows = compare_runs(ids)
        except BacktestRun.DoesNotExist as exc:
            raise CommandError(str(exc)) from exc
        except OwnershipError as exc:
            raise CommandError(str(exc)) from exc

        headers = [
            "id",
            "status",
            "strategy_id",
            "symbol",
            "trades",
            "pnl",
            "max_dd",
            "pf",
            "win_rate",
        ]
        self.stdout.write("  ".join(f"{h:>10}" for h in headers))
        for row in rows:
            self.stdout.write(
                "  ".join(
                    [
                        f"{row['id']:>10}",
                        f"{row['status']:>10}",
                        f"{row['strategy_id']:>10}",
                        f"{str(row['symbol']):>10}",
                        f"{row['total_trades']:>10}",
                        f"{row['total_pnl']:>10.4f}",
                        f"{(row['max_drawdown'] if row['max_drawdown'] is not None else 0):>10.4f}",
                        f"{(row['profit_factor'] if row['profit_factor'] is not None else 0):>10.4f}",
                        f"{(row['win_rate'] if row['win_rate'] is not None else 0):>10.4f}",
                    ]
                )
            )
