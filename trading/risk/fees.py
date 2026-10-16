"""Trading cost model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeModel:
    """Per-side fee as a fraction of notional (e.g. 0.00045 = 0.045%)."""

    rate: float = 0.00045

    def round_trip(self, entry_notional: float, exit_notional: float) -> float:
        return entry_notional * self.rate + exit_notional * self.rate

    def entry_fee(self, notional: float) -> float:
        return notional * self.rate


@dataclass(frozen=True)
class SlippageModel:
    """Simple adverse slippage applied to fill prices (fraction)."""

    rate: float = 0.0

    def apply(self, price: float, *, side_is_buy: bool, is_entry: bool) -> float:
        if self.rate <= 0:
            return price
        # Entries: buys pay more, sells receive less. Exits: opposite adverse.
        if is_entry:
            return price * (1 + self.rate) if side_is_buy else price * (1 - self.rate)
        return price * (1 - self.rate) if side_is_buy else price * (1 + self.rate)
