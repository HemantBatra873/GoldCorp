from __future__ import annotations

import json
from datetime import timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.models import Symbol
from apps.research.exceptions import InvalidRunState, OwnershipError, ResearchError
from apps.mlapp.models import MLModel, MLModelStatus
from apps.research.forms import BacktestCreateForm, CompareForm, RunFilterForm, StrategyLabForm
from apps.research.lab import enqueue_param_sweep
from apps.research.models import BacktestRun, RunStatus, Trade
from apps.research.services import (
    cancel_backtest_run,
    compare_runs,
    create_and_enqueue_backtest,
    get_run,
    runs_for_user,
)


def _aware(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    qs = runs_for_user(request.user)
    recent = qs[:8]
    stats = qs.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=RunStatus.COMPLETED)),
        failed=Count("id", filter=Q(status=RunStatus.FAILED)),
        running=Count("id", filter=Q(status__in=[RunStatus.QUEUED, RunStatus.RUNNING])),
        pnl=Sum("total_pnl", filter=Q(status=RunStatus.COMPLETED)),
    )
    symbols = Symbol.objects.filter(is_active=True).count()
    return render(
        request,
        "research/dashboard.html",
        {
            "recent_runs": recent,
            "stats": stats,
            "symbol_count": symbols,
        },
    )


@login_required
def run_list(request: HttpRequest) -> HttpResponse:
    form = RunFilterForm(request.GET or None)
    qs = runs_for_user(request.user)
    if form.is_valid():
        if form.cleaned_data.get("status"):
            qs = qs.filter(status=form.cleaned_data["status"])
        if form.cleaned_data.get("strategy_id"):
            qs = qs.filter(strategy_id__icontains=form.cleaned_data["strategy_id"])
        if form.cleaned_data.get("symbol"):
            qs = qs.filter(symbol__symbol__icontains=form.cleaned_data["symbol"].upper())

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "research/run_list.html",
        {"form": form, "page": page, "runs": page.object_list},
    )


def _strategy_params_from_form(data: dict) -> dict:
    if data["strategy_id"] == "ml_classifier":
        model = MLModel.objects.get(pk=int(data["ml_model_id"]), status=MLModelStatus.READY)
        return {
            "model_path": model.artifact_path,
            "threshold": float(data.get("ml_threshold") or 0.58),
            "warm_up": 60,
        }
    return {"open_rsi": data["open_rsi"]}


@login_required
@require_http_methods(["GET", "POST"])
def run_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = BacktestCreateForm(request.POST, user=request.user)
        if form.is_valid():
            data = form.cleaned_data
            try:
                run = create_and_enqueue_backtest(
                    symbol=data["symbol"].upper(),
                    strategy_id=data["strategy_id"],
                    timeframe=data["timeframe"],
                    name=data.get("name") or "",
                    owner=request.user,
                    strategy_params=_strategy_params_from_form(data),
                    execution={
                        "fee_rate": data["fee_rate"],
                        "slippage_rate": data["slippage_rate"],
                        "tp_sl_ratio": data["tp_sl_ratio"],
                        "sl_limit": data["sl_limit"],
                        "position_notional": data["notional"],
                        "enable_trailing": bool(data.get("enable_trailing")),
                    },
                    data_start=_aware(data.get("data_start")),
                    data_end=_aware(data.get("data_end")),
                )
                messages.success(
                    request,
                    f"Experiment #{run.pk} queued. Status updates as the worker finishes.",
                )
                return redirect("research:run_detail", run_id=run.pk)
            except (ResearchError, KeyError, TypeError, FileNotFoundError, MLModel.DoesNotExist) as exc:
                messages.error(request, str(exc))
    else:
        form = BacktestCreateForm(user=request.user)

    return render(request, "research/run_create.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def strategy_lab(request: HttpRequest) -> HttpResponse:
    run_ids: list[int] = []
    if request.method == "POST":
        form = StrategyLabForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                run_ids = enqueue_param_sweep(
                    symbol=data["symbol"].upper(),
                    strategy_id=data["strategy_id"],
                    timeframe=data["timeframe"],
                    owner=request.user,
                    strategy_grid={"open_rsi": data["open_rsi_values"]},
                    execution_grid={"tp_sl_ratio": data["tp_sl_ratio_values"]},
                    name_prefix=data["name_prefix"],
                )
                messages.success(
                    request,
                    f"Queued {len(run_ids)} lab experiments: {', '.join('#'+str(i) for i in run_ids)}",
                )
                query = "&".join(f"ids={i}" for i in run_ids)
                return redirect(f"{reverse('research:run_compare')}?{query}")
            except (ResearchError, KeyError, TypeError, ValueError) as exc:
                messages.error(request, str(exc))
    else:
        form = StrategyLabForm()
    return render(request, "research/strategy_lab.html", {"form": form, "run_ids": run_ids})


@login_required
def api_runs(request: HttpRequest) -> JsonResponse:
    """Read-only JSON list of the user's experiments."""
    qs = runs_for_user(request.user)[:100]
    payload = [
        {
            "id": r.pk,
            "name": r.name,
            "status": r.status,
            "strategy_id": r.strategy_id,
            "symbol": r.symbol.symbol if r.symbol_id else None,
            "timeframe": r.timeframe,
            "total_trades": r.total_trades,
            "total_pnl": float(r.total_pnl),
            "max_drawdown": float(r.max_drawdown) if r.max_drawdown is not None else None,
            "config_hash": r.config_hash,
        }
        for r in qs
    ]
    return JsonResponse(payload, safe=False)


@login_required
def run_detail(request: HttpRequest, run_id: int) -> HttpResponse:
    try:
        run = get_run(run_id, user=request.user)
    except OwnershipError:
        return HttpResponseForbidden("You do not have access to this run.")
    except BacktestRun.DoesNotExist:
        return redirect("research:run_list")

    trades = list(run.trades.all()[:200])
    equity_points = list(run.equity_points.order_by("sequence"))

    equity_labels = []
    equity_values = []
    drawdown_values = []
    peak = None
    for point in equity_points:
        label = (
            point.timestamp.strftime("%Y-%m-%d %H:%M")
            if point.timestamp
            else f"#{point.sequence}"
        )
        equity = float(point.equity)
        equity_labels.append(label)
        equity_values.append(equity)
        peak = equity if peak is None else max(peak, equity)
        dd = ((peak - equity) / peak) if peak else 0.0
        drawdown_values.append(round(dd * 100, 4))

    win_trades = sum(1 for t in trades if t.profit > 0)
    loss_trades = sum(1 for t in trades if t.profit < 0)
    avg_win = (
        sum(float(t.profit) for t in trades if t.profit > 0) / win_trades
        if win_trades
        else None
    )
    avg_loss = (
        sum(float(t.profit) for t in trades if t.profit < 0) / loss_trades
        if loss_trades
        else None
    )

    close_breakdown = {}
    for t in trades:
        close_breakdown[t.close_method] = close_breakdown.get(t.close_method, 0) + 1

    return render(
        request,
        "research/run_detail.html",
        {
            "run": run,
            "trades": trades,
            "equity_labels_json": json.dumps(equity_labels),
            "equity_values_json": json.dumps(equity_values),
            "drawdown_values_json": json.dumps(drawdown_values),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "close_breakdown": close_breakdown,
            "request_config": (run.config or {}).get("request") or {},
        },
    )


@login_required
@require_POST
def run_cancel(request: HttpRequest, run_id: int) -> HttpResponse:
    run = get_object_or_404(BacktestRun, pk=run_id)
    try:
        cancel_backtest_run(run, user=request.user)
        messages.info(request, f"Run #{run_id} cancelled.")
    except OwnershipError:
        return HttpResponseForbidden("You do not have access to this run.")
    except InvalidRunState as exc:
        messages.warning(request, str(exc))
    return redirect("research:run_detail", run_id=run_id)


@login_required
@require_http_methods(["GET", "POST"])
def run_compare(request: HttpRequest) -> HttpResponse:
    rows = []
    form = CompareForm(request.POST or request.GET or None)
    selected_ids = request.GET.getlist("ids")
    if selected_ids and not (request.POST or request.GET.get("run_ids")):
        form = CompareForm({"run_ids": ",".join(selected_ids)})

    if form.is_valid():
        try:
            rows = compare_runs(form.cleaned_data["run_ids"], user=request.user)
        except OwnershipError:
            messages.error(request, "You do not have access to one or more runs.")
        except BacktestRun.DoesNotExist:
            messages.error(request, "One or more run ids were not found.")

    chart_labels = [f"#{r['id']}" for r in rows]
    chart_pnl = [r["total_pnl"] for r in rows]
    chart_dd = [r["max_drawdown"] or 0 for r in rows]

    return render(
        request,
        "research/compare.html",
        {
            "form": form,
            "rows": rows,
            "chart_labels_json": json.dumps(chart_labels),
            "chart_pnl_json": json.dumps(chart_pnl),
            "chart_dd_json": json.dumps(chart_dd),
        },
    )
