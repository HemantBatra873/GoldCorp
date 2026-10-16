# Phase 6 — Production finish + ML

## Delivered

- `ml_classifier` strategy + sklearn training pipeline (chronological split)
- ML UI: `/ml/`, `/ml/train/`
- Strategy lab: `/runs/lab/` parameter sweeps
- Read-only JSON: `/api/runs/`
- GitHub Actions CI (Postgres + Redis + pytest + ruff)
- Architecture doc
- Legacy `Denarios/` tree removed from the product repo

## Train + backtest ML

```bash
python manage.py download_klines --symbol BTCUSDT --interval 4h --limit 1000
python manage.py train_ml_model --symbol BTCUSDT --interval 4h
# then New experiment → strategy ml_classifier → select model
```

## Notes

ML metrics are research diagnostics. They do not guarantee live edge.
