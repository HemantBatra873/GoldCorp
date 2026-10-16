from django.core.management.base import BaseCommand, CommandError

from apps.research.exceptions import InvalidRunState, OwnershipError, ResearchError
from apps.research.models import BacktestRun
from apps.research.services import cancel_backtest_run


class Command(BaseCommand):
    help = "Cancel a queued or running BacktestRun."

    def add_arguments(self, parser):
        parser.add_argument("run_id", type=int)

    def handle(self, *args, **options):
        try:
            run = BacktestRun.objects.get(pk=options["run_id"])
        except BacktestRun.DoesNotExist as exc:
            raise CommandError(f"Run {options['run_id']} not found") from exc

        try:
            run = cancel_backtest_run(run)
        except (InvalidRunState, OwnershipError, ResearchError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Run #{run.pk} status={run.status}"))
