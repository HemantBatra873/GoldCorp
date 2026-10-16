from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.mlapp.forms import MLTrainForm
from apps.mlapp.models import MLModel
from apps.mlapp.services import create_ml_job, enqueue_ml_training


@login_required
def ml_list(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q

    models = (
        MLModel.objects.select_related("symbol")
        .filter(Q(owner=request.user) | Q(owner__isnull=True))
        .order_by("-created_at")[:50]
    )
    return render(request, "mlapp/list.html", {"models": models})


@login_required
@require_http_methods(["GET", "POST"])
def ml_train(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = MLTrainForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            model = create_ml_job(
                symbol=data["symbol"],
                timeframe=data["timeframe"],
                name=data.get("name") or "",
                owner=request.user,
                train_ratio=data["train_ratio"],
            )
            enqueue_ml_training(model)
            messages.success(request, f"ML training job #{model.pk} queued.")
            return redirect("mlapp:detail", model_id=model.pk)
    else:
        form = MLTrainForm()
    return render(request, "mlapp/train.html", {"form": form})


@login_required
def ml_detail(request: HttpRequest, model_id: int) -> HttpResponse:
    model = get_object_or_404(MLModel.objects.select_related("symbol"), pk=model_id)
    return render(request, "mlapp/detail.html", {"model": model})
