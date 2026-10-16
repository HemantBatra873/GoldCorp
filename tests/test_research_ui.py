"""Phase 4 — dashboard auth and ownership-aware views."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.research.models import BacktestRun, RunStatus
from apps.research.services import create_backtest_run


User = get_user_model()


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("research:dashboard"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_register_login_dashboard(client):
    response = client.post(
        reverse("core:register"),
        {
            "username": "trader1",
            "email": "t@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("research:dashboard")
    follow = client.get(reverse("research:dashboard"))
    assert follow.status_code == 200
    assert b"Research workbench" in follow.content


@pytest.mark.django_db
def test_run_detail_blocks_other_user(client):
    owner = User.objects.create_user("owner", password="StrongPass123!")
    other = User.objects.create_user("intruder", password="StrongPass123!")
    run = create_backtest_run(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        owner=owner,
    )
    client.login(username="intruder", password="StrongPass123!")
    response = client.get(reverse("research:run_detail", args=[run.pk]))
    assert response.status_code == 403


@pytest.mark.django_db
def test_run_list_shows_owned_and_unowned(client):
    user = User.objects.create_user("viewer", password="StrongPass123!")
    owned = create_backtest_run(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        owner=user,
        name="mine",
    )
    orphan = create_backtest_run(
        symbol="ETHUSDT",
        strategy_id="rsi_macd_stoch",
        owner=None,
        name="cli",
    )
    other = User.objects.create_user("someone", password="StrongPass123!")
    hidden = create_backtest_run(
        symbol="SOLUSDT",
        strategy_id="rsi_macd_stoch",
        owner=other,
        name="secret",
    )
    client.login(username="viewer", password="StrongPass123!")
    response = client.get(reverse("research:run_list"))
    assert response.status_code == 200
    body = response.content.decode()
    assert f"#{owned.pk}" in body
    assert f"#{orphan.pk}" in body
    assert f"#{hidden.pk}" not in body


@pytest.mark.django_db
def test_compare_page_loads(client):
    user = User.objects.create_user("cmp", password="StrongPass123!")
    a = create_backtest_run(symbol="BTCUSDT", strategy_id="rsi_macd_stoch", owner=user)
    b = create_backtest_run(symbol="BTCUSDT", strategy_id="rsi_macd_stoch", owner=user)
    BacktestRun.objects.filter(pk__in=[a.pk, b.pk]).update(status=RunStatus.COMPLETED)
    client.login(username="cmp", password="StrongPass123!")
    response = client.get(reverse("research:run_compare"), {"run_ids": f"{a.pk},{b.pk}"})
    assert response.status_code == 200
    assert b"Compare experiments" in response.content
