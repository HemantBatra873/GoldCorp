# Phase 2 — Trading engine

## Architecture

```text
Strategy.on_bar(df, i)     # reads rows <= i only
        ↓ Signal
fill at open of bar i+1    # ExecutionSimulator
        ↓ OpenPosition
each later bar: TP/SL/trail
        ↓ ClosedTrade
metrics + config_hash
```

## Guarantees

| Concern | Rule |
|---------|------|
| Look-ahead | Signals use closed bar `i`; fills use next open |
| Same-bar TP+SL | Larger excursion beyond level wins (Anastasia heuristic) |
| Costs | Fee per side (default 0.045%) + optional slippage |
| Reproducibility | `config` JSON + `config_hash` + `engine_version` on every result |
| Django isolation | `trading/` imports no Django |

## Strategy shipped

- `rsi_macd_stoch` — StochRSI regime + MACD slope + RSI confirmation (from Agripina)

## Commands

- `download_klines` — public Binance Futures klines → `data/ohlcv/`
- `run_backtest` — engine → Postgres (`BacktestRun`, `Trade`, `EquityPoint`)
