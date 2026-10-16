# Phase 1 — Legacy audit & keep / rewrite / retire

GoldCorp is a **new** codebase. The legacy `Denarios/` tree was used as a reference through Phase 5 and **removed in Phase 6**.

## Target architecture (locked)

| Layer | Responsibility | Depends on Django? |
|-------|----------------|--------------------|
| `apps.*` | Auth, admin, HTTP, persistence, Celery tasks | Yes |
| Application services (Phase 3) | Create runs, ownership, persist results | Yes |
| `trading.*` | Strategies, backtester, execution sim, risk, market-data contracts | **No** |
| Infrastructure | Postgres, Redis/Celery, Binance adapters | Adapters only |

## Denarios inventory

### Rewrite into GoldCorp (valuable logic)

| Legacy path | Extract | GoldCorp destination |
|-------------|---------|----------------------|
| `app/models.py` (Symbol, positions, Optimum_parameter concepts) | Domain ideas only | `apps.core.Symbol`, `apps.research.BacktestRun`, later trade models |
| `bots/A_A_9/functions/Agripina.py` | Entry signal + sizing patterns | `trading.strategies` + services |
| `bots/A_A_9/functions/Anastasia.py` | TP/SL / trailing / same-bar conflict | `trading.risk` + `trading.execution` |
| `bots/A_A_9/functions/Take_position.py` | Signed Binance Futures REST | `trading.execution` exchange adapter (Phase 5) |
| `bots/A_A_9/functions/CryptoAnalyzer.py` | Klines + indicator columns | `trading.marketdata` + indicators |
| `bots/simulations/Crypto_simulation/A_A_90.py` (and helpers) | One strategy + sim loop ideas | `trading.backtest` + one strategy |
| `bots/simulations/.../Add_indicators/*` | Feature engineering | `trading.marketdata` / indicators |
| `bots/simulations/.../DB_habndle.py` | Fee / close bookkeeping ideas | `trading.risk` + research persistence |
| `app/views.py` analisis aggregations | Metric ideas only | Research dashboard (Phase 4) |

### Retire / delete (do not port)

| Path | Reason |
|------|--------|
| `bots/notUsed/**` | Dead copies |
| `bots/simulations/**/Old/**` | Strategy graveyard |
| `bots/simulations/snipets/**` (most) | Ad-hoc plots; rebuild with Chart.js later |
| `forex/`, `bots_forex/` | Empty / unfinished |
| `MLbots/*` | Toy scripts with look-ahead leakage; rebuild properly in Phase 6 |
| Hard-coded secrets / SMTP passwords | Security debt — never copy |
| Incomplete `analisis` UI / Paralegapp nav | Replaced by GoldCorp UI |

### Status after Phase 1

- New project runs independently of Denarios imports.
- `Denarios/` remains on disk for Phase 2 extraction only.
- Delete `Denarios/` once the first strategy + execution rules are validated.

## Phase 1 deliverables checklist

- [x] Package layout: `config/`, `apps/`, `trading/`
- [x] PostgreSQL + Redis + Celery (Docker Compose)
- [x] Split settings (`local` / `production`)
- [x] Health endpoint
- [x] `Symbol` + `BacktestRun` lifecycle model
- [x] pytest smoke tests
- [x] `.env.example`, structured logging
- [x] Postgres + Redis via Compose verified (host ports 5434 / 6380)
- [x] Migrations applied; pytest smoke tests passing
- [x] `/health/` returns ok against Postgres
