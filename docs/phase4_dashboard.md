# Phase 4 — Research dashboard

Authenticated experiment workbench on top of the Phase 2 engine and Phase 3 jobs.

## Pages

| Route | Purpose |
|-------|---------|
| `/accounts/login/` | Login |
| `/register/` | Register |
| `/` | Dashboard |
| `/runs/` | Filtered experiment list |
| `/runs/new/` | Queue backtest (Celery) |
| `/runs/<id>/` | Detail: equity, drawdown, risk, trades |
| `/runs/compare/` | Side-by-side metrics + charts |

## Stack

- Django templates + Bootstrap 5 CDN
- Chart.js CDN
- Ownership enforced in `apps.research.services`

## Local demo

```bash
python manage.py createsuperuser   # optional
# or register via /register/
celery -A config worker -l INFO --pool=solo
python manage.py runserver
```
