# GoldCorp Quant Lab

Cryptocurrency research platform: backtest strategies, analyze risk, compare experiments, and paper-trade — built with Django, PostgreSQL, Redis, and Celery.

> Phase 6 complete: CI, strategy lab, and ML classifier strategy.

## Stack

| Component | Tech |
|-----------|------|
| Web | Django 5.1+, Gunicorn, WhiteNoise |
| Database | PostgreSQL 16 |
| Jobs | Celery + Redis + django-celery-beat |
| Quant | pandas, numpy, `ta` |
| ML (later) | scikit-learn |

## Project layout

```text
config/          Django settings, URLs, Celery app
apps/core/       Shared models (Symbol), health check
apps/research/   BacktestRun lifecycle / experiments
trading/         Pure Python trading domain (no Django)
tests/           pytest
docs/            Architecture & phase notes
Denarios/        Temporary legacy reference — will be removed
```

## Quick start (Docker)

```bash
cp .env.example .env
# set a real SECRET_KEY in .env

docker compose up --build
```

- App: http://localhost:8000/health/
- Admin: http://localhost:8000/admin/ (create a superuser first)

```bash
docker compose exec web python manage.py createsuperuser
```

## Local Python (DB/Redis still via Docker)

```bash
docker compose up -d db redis
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
# Postgres on localhost:5434, Redis on localhost:6380 (see .env)
python manage.py migrate
python manage.py runserver
# On Windows use solo pool; in Docker/Linux prefork is fine
celery -A config worker -l INFO --pool=solo
celery -A config beat -l INFO
pytest
```



## Phase roadmap

1. **Foundation** — Docker, Postgres, Redis, Celery, models, tests  
2. **Trading engine** — independent backtester + `rsi_macd_stoch`  
3. **Jobs & persistence** — Celery backtest runs + lifecycle  
4. **Research dashboard** — auth, charts, compare experiments  
5. **Paper trading** — simulated + Binance Testnet  
6. **Production + ML** (current) — CI, strategy lab, sklearn plugin  

See `docs/ARCHITECTURE.md` and `docs/phase6_production_ml.md`.

### Quick commands

```bash
python manage.py download_klines --symbol BTCUSDT --interval 4h --limit 1000
python manage.py train_ml_model --symbol BTCUSDT
celery -A config worker -l INFO --pool=solo
python manage.py runserver
# http://127.0.0.1:8000/  ·  /runs/lab/  ·  /ml/  ·  /paper/
pytest
```
