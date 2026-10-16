"""
StochRSI + MACD + RSI confluence strategy.

Ported from Denarios Agripina entry logic, adapted to ascending candles:
at index i we use bars i (current closed) and i-1 (previous) for MACD slope,
matching the original "completed bars" intent without reversing the frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.strategies.base import BaseStrategy, StrategyInfo
from trading.types import OpenPosition, Side, Signal


@dataclass
class _OppState:
    side: Side | None = None
    stoch: bool = False
    macd: bool = False
    rsi: bool = False

    def clear(self) -> None:
        self.side = None
        self.stoch = False
        self.macd = False
        self.rsi = False


class RsiMacdStochStrategy(BaseStrategy):
    STRATEGY_ID = "rsi_macd_stoch"
    VERSION = "1.0.0"

    def __init__(
        self,
        *,
        stoch_buy: float = 0.20,
        stoch_sell: float = 0.80,
        open_rsi: float = 5.0,
        warm_up: int = 60,
    ):
        self.stoch_buy = stoch_buy
        self.stoch_sell = stoch_sell
        self.open_rsi = open_rsi
        self.warm_up = warm_up
        self._state = _OppState()

    @property
    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self.STRATEGY_ID,
            version=self.VERSION,
            description="StochRSI trigger + MACD slope + RSI confirmation",
        )

    def default_params(self) -> dict[str, Any]:
        return {
            "stoch_buy": self.stoch_buy,
            "stoch_sell": self.stoch_sell,
            "open_rsi": self.open_rsi,
            "warm_up": self.warm_up,
        }

    def reset(self) -> None:
        self._state.clear()

    def on_bar(
        self,
        df: pd.DataFrame,
        index: int,
        position: OpenPosition | None,
    ) -> Signal | None:
        if position is not None:
            return None
        if index < max(self.warm_up, 1):
            return None

        row = df.iloc[index]
        prev = df.iloc[index - 1]
        if pd.isna(row["stoch_k"]) or pd.isna(row["macd_hist"]) or pd.isna(row["rsi"]):
            return None
        if pd.isna(prev["macd_hist"]):
            return None

        sk = float(row["stoch_k"])
        sd = float(row["stoch_d"])
        macd = float(row["macd_hist"])
        macd_prev = float(prev["macd_hist"])
        rsi = float(row["rsi"])
        rsi_buy = 50.0 + self.open_rsi
        rsi_sell = 50.0 - self.open_rsi

        st = self._state

        # StochRSI regime
        if sk >= self.stoch_sell and sd >= self.stoch_sell:
            if st.side is not Side.SELL:
                st.side = Side.SELL
                st.stoch = True
                st.macd = False
                st.rsi = False
        elif sk <= self.stoch_buy and sd <= self.stoch_buy:
            if st.side is not Side.BUY:
                st.side = Side.BUY
                st.stoch = True
                st.macd = False
                st.rsi = False

        if st.side is Side.SELL:
            if sk <= 0.20 or sd <= 0.20:
                st.clear()
            else:
                if not st.macd and macd < macd_prev:
                    st.macd = True
                elif st.macd and macd > macd_prev:
                    st.macd = False
                if not st.rsi and rsi <= rsi_sell:
                    st.rsi = True
                elif st.rsi and rsi >= rsi_sell:
                    st.rsi = False

        if st.side is Side.BUY:
            if sk >= 0.80 or sd >= 0.80:
                st.clear()
            else:
                if not st.macd and macd > macd_prev:
                    st.macd = True
                elif st.macd and macd < macd_prev:
                    st.macd = False
                if not st.rsi and rsi >= rsi_buy:
                    st.rsi = True
                elif st.rsi and rsi <= rsi_buy:
                    st.rsi = False

        if not (st.side and st.stoch and st.macd and st.rsi):
            return None

        side = st.side
        if side is Side.BUY:
            sl_raw = float(row["min_low_20"])
        else:
            sl_raw = float(row["max_high_20"])

        reason = f"{side.value}: stoch+macd+rsi confluence"
        meta = {
            "stoch_k": sk,
            "stoch_d": sd,
            "macd_hist": macd,
            "rsi": rsi,
        }
        st.clear()
        st.side = None  # opportunity consumed; live bot would mark OPEN
        return Signal(side=side, reason=reason, sl_raw=sl_raw, meta=meta)
