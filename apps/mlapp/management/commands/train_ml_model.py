from django.core.management.base import BaseCommand, CommandError

from apps.mlapp.services import create_ml_job, enqueue_ml_training, train_ml_model


class Command(BaseCommand):
    help = "Train an ML direction model from local OHLCV CSV (sync or --async)."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--interval", default="4h")
        parser.add_argument("--name", default="")
        parser.add_argument("--train-ratio", type=float, default=0.7)
        parser.add_argument("--async", dest="async_enqueue", action="store_true")

    def handle(self, *args, **options):
        model = create_ml_job(
            symbol=options["symbol"],
            timeframe=options["interval"],
            name=options["name"],
            train_ratio=options["train_ratio"],
        )
        if options["async_enqueue"]:
            enqueue_ml_training(model)
            self.stdout.write(self.style.SUCCESS(f"Queued MLModel id={model.pk}"))
            return
        try:
            model = train_ml_model(model.pk)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Ready MLModel id={model.pk} accuracy={model.metrics.get('accuracy')} "
                f"path={model.artifact_path}"
            )
        )
