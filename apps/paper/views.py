from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.paper.forms import PaperSessionForm
from apps.paper.models import PaperEvent, PaperFill, PaperPosition, PaperSession
from apps.paper.services import activate_session, get_or_create_default_session
from apps.paper.tasks import paper_entry_scan, paper_exit_scan


def _session_for_user(user) -> PaperSession:
    session = (
        PaperSession.objects.filter(owner=user).order_by("-updated_at").first()
        or PaperSession.objects.filter(owner__isnull=True).order_by("-updated_at").first()
    )
    if session is None:
        session = get_or_create_default_session(owner=user)
    elif session.owner_id is None:
        session.owner = user
        session.save(update_fields=["owner", "updated_at"])
    return session


@login_required
def paper_dashboard(request: HttpRequest) -> HttpResponse:
    session = _session_for_user(request.user)
    open_positions = PaperPosition.objects.filter(
        session=session, status=PaperPosition.Status.OPEN
    )
    fills = PaperFill.objects.filter(session=session)[:20]
    events = PaperEvent.objects.filter(session=session)[:40]
    return render(
        request,
        "paper/dashboard.html",
        {
            "session": session,
            "open_positions": open_positions,
            "fills": fills,
            "events": events,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def paper_settings(request: HttpRequest) -> HttpResponse:
    session = _session_for_user(request.user)
    if request.method == "POST":
        form = PaperSessionForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            messages.success(request, "Paper session settings saved.")
            return redirect("paper:dashboard")
    else:
        form = PaperSessionForm(instance=session)
    return render(request, "paper/settings.html", {"form": form, "session": session})


@login_required
@require_POST
def paper_toggle(request: HttpRequest) -> HttpResponse:
    session = _session_for_user(request.user)
    activate_session(session, active=not session.is_active)
    messages.info(
        request,
        f"Paper trading {'activated' if session.is_active else 'paused'}.",
    )
    return redirect("paper:dashboard")


@login_required
@require_POST
def paper_run_once(request: HttpRequest) -> HttpResponse:
    """Manually trigger entry + exit scans (uses Celery eager or async)."""
    session = _session_for_user(request.user)
    if not session.is_active:
        activate_session(session, active=True)
    paper_entry_scan.delay()
    paper_exit_scan.delay()
    messages.success(request, "Entry/exit scans dispatched to Celery.")
    return redirect("paper:dashboard")
