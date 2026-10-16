from django.urls import path

from apps.mlapp import views

app_name = "mlapp"

urlpatterns = [
    path("ml/", views.ml_list, name="list"),
    path("ml/train/", views.ml_train, name="train"),
    path("ml/<int:model_id>/", views.ml_detail, name="detail"),
]
