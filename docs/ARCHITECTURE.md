# GoldCorp architecture

```text
Browser / CLI
    │
    ▼
Django apps (auth, research UI, paper UI, ml UI, admin)
    │
    ├── Application services (ownership, enqueue, persist)
    │
    ├── Celery workers (backtests, paper scans, ML train)
    │
    └── trading/  ← pure Python, no Django
          ├── strategies/   (rsi_macd_stoch, ml_classifier)
          ├── backtest/     (engine, metrics, reproducibility)
          ├── execution/    (simulator)
          ├── risk/         (fees, TP/SL, same-bar exits)
          ├── marketdata/   (Binance public, CSV, quality)
          ├── exchange/     (SimulatedBroker, BinanceFuturesClient)
          └── ml/           (features, train, joblib bundles)
```

## Correctness contracts

- Signals evaluated on closed bar `i`; fills at open of `i+1`
- Indicator/ML features at `i` use only rows `≤ i`
- ML labels may use `close[i+1]` **only during training**
- Every backtest stores `config` + `config_hash` + `engine_version`

## Free stack

PostgreSQL, Redis, Celery, Django, pandas, `ta`, scikit-learn, Chart.js CDN, Binance public/testnet APIs.
