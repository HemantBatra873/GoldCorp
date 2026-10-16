"""Research-layer domain/application errors."""


class ResearchError(Exception):
    """Base error for research services."""


class OwnershipError(ResearchError):
    """User is not allowed to access or mutate this run."""


class InvalidRunState(ResearchError):
    """Lifecycle transition is not allowed from the current status."""


class BacktestDataError(ResearchError):
    """Market data missing or invalid for a requested run."""
