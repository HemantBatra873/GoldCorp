from django.apps import AppConfig


class MlappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mlapp"
    label = "mlapp"
    verbose_name = "Machine Learning"
