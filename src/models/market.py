"""Market data models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Side(str, Enum):
    """Order side."""

    YES = "YES"
    NO = "NO"
    BUY = "BUY"  # For platforms that use BUY/SELL instead of YES/NO
    SELL = "SELL"


class Platform(str, Enum):
    """Trading platform."""

    KALSHI = "KALSHI"
    POLYMARKET = "POLYMARKET"


class OrderBook(BaseModel):
    """Order book for a market."""

    best_yes_price: Decimal = Field(description="Best available YES price")
    best_no_price: Decimal = Field(description="Best available NO price")
    yes_liquidity: Decimal = Field(description="Available YES liquidity")
    no_liquidity: Decimal = Field(description="Available NO liquidity")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("best_yes_price", "best_no_price")
    @classmethod
    def validate_price(cls, v: Decimal) -> Decimal:
        """Validate price is between 0 and 1."""
        if not (Decimal("0") <= v <= Decimal("1")):
            raise ValueError("Price must be between 0 and 1")
        return v

    @property
    def spread(self) -> Decimal:
        """Calculate the spread."""
        return self.best_yes_price + self.best_no_price - Decimal("1")


class Market(BaseModel):
    """Normalized market data."""

    platform: Platform
    market_id: str = Field(description="Platform-specific market ID")
    event_id: str = Field(description="Platform-specific event ID")
    question: str = Field(description="Market question/title")
    close_time: datetime = Field(description="Market close time")
    orderbook: OrderBook
    status: str = Field(default="active")
    min_tick_size: Decimal = Field(default=Decimal("0.01"))
    max_volume: Optional[Decimal] = None

    @property
    def is_active(self) -> bool:
        """Check if market is active."""
        return self.status == "active" and self.close_time > datetime.utcnow()


class MarketPair(BaseModel):
    """Matched market pair across platforms."""

    kalshi: Market
    polymarket: Market
    description: str = Field(description="Human-readable description of the matched event")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Matching confidence (0-1)"
    )
    last_checked: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_valid(self) -> bool:
        """Check if both markets are still valid for trading."""
        return self.kalshi.is_active and self.polymarket.is_active

    def update_timestamp(self) -> None:
        """Update last checked timestamp."""
        self.last_checked = datetime.utcnow()
