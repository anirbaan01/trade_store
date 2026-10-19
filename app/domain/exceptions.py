class TradeDomainException(Exception):
    """Base exception for Trade Domain business rule violations."""
    pass

class LowerVersionTradeException(TradeDomainException):
    """Raised when an incoming trade has a version lower than the current stored version."""
    def __init__(self, trade_id: str, incoming_version: int, existing_version: int):
        self.trade_id = trade_id
        self.incoming_version = incoming_version
        self.existing_version = existing_version
        super().__init__(
            f"Trade '{trade_id}' rejected: incoming version {incoming_version} is lower than existing version {existing_version}."
        )

class InvalidMaturityDateException(TradeDomainException):
    """Raised when an incoming trade has a maturity date earlier than today's date."""
    def __init__(self, trade_id: str, maturity_date, current_date):
        self.trade_id = trade_id
        self.maturity_date = maturity_date
        self.current_date = current_date
        super().__init__(
            f"Trade '{trade_id}' rejected: maturity date {maturity_date} is earlier than today's date {current_date}."
        )
