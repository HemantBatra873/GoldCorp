# Phase 5 — Paper trading

Strategy logic stays in `trading/`. Brokers live in `trading/exchange/`. Django only orchestrates sessions, events, and jobs.

## Modes

| Mode | Broker | Keys required |
|------|--------|----------------|
| `simulated` | `SimulatedBroker` (public mark price fills) | No |
| `testnet` | `BinanceFuturesClient` → `testnet.binancefuture.com` | Yes |

## Components

- Models: `PaperSession`, `PaperPosition`, `PaperFill`, `PaperEvent`
- Services: `scan_entries_for_session`, `manage_exits_for_session`
- Celery Beat: entry hourly, exit every 5m, heartbeat every 10m
- UI: `/paper/`, `/paper/settings/`

## Commands

```bash
python manage.py paper_scan --activate
celery -A config worker -l INFO --pool=solo
celery -A config beat -l INFO
```

Set in `.env` for testnet:

```
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET=True
```
