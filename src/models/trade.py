"""Trade and order models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .market import Platform, Side


class OrderStatus(str, Enum):
    """Order status."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    FOK = "FOK"  # Fill or Kill
    FAK = "FAK"  # Fill and Kill
    GTC = "GTC"  # Good til Cancelled


class Order(BaseModel):
    """Trading order."""

    order_id: str = Field(default_factory=lambda: str(uuid4()))
    platform: Platform
    market_id: str
    side: Side
    order_type: OrderType = OrderType.LIMIT
    price: Decimal = Field(description="Limit price (0-1)")
    quantity: Decimal = Field(description="Quantity in USD or contracts")
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Optional[Decimal] = None
    platform_order_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    @property
    def is_filled(self) -> bool:
        """Check if order is filled."""
        return self.status == OrderStatus.FILLED

    @property
    def total_cost(self) -> Decimal:
        """Calculate total cost of filled order."""
        if self.average_fill_price is None:
            return Decimal("0")
        return self.filled_quantity * self.average_fill_price


class Trade(BaseModel):
    """Executed trade (both legs of arbitrage)."""

    trade_id: str = Field(default_factory=lambda: str(uuid4()))
    strategy: str = Field(description="e.g., 'kalshi_yes_poly_no'")
    leg1: Order
    leg2: Order
    expected_profit: Decimal
    actual_profit: Optional[Decimal] = None
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None

    @property
    def is_complete(self) -> bool:
        """Check if both legs are filled."""
        return self.leg1.is_filled and self.leg2.is_filled

    @property
    def total_cost(self) -> Decimal:
        """Calculate total cost of both legs."""
        return self.leg1.total_cost + self.leg2.total_cost

    def calculate_actual_profit(self, payout: Decimal = Decimal("1.0")) -> Decimal:
        """Calculate actual profit from filled orders."""
        if not self.is_complete:
            return Decimal("0")
        self.actual_profit = payout - self.total_cost
        return self.actual_profit


class ArbitrageOpportunity(BaseModel):
    """Detected arbitrage opportunity."""

    opportunity_id: str = Field(default_factory=lambda: str(uuid4()))
    market_pair: "MarketPair"  # Forward reference
    strategy: str
    leg1_platform: Platform
    leg1_side: Side
    leg1_price: Decimal
    leg2_platform: Platform
    leg2_side: Side
    leg2_price: Decimal
    total_cost: Decimal
    expected_profit: Decimal
    profit_percentage: Decimal
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    executed: bool = False
    trade_id: Optional[str] = None

    @property
    def is_profitable(self) -> bool:
        """Check if opportunity is still profitable."""
        return self.expected_profit > Decimal("0")

    def create_orders(self, position_size: Decimal) -> tuple[Order, Order]:
        """Create order objects for this opportunity."""
        leg1 = Order(
            platform=self.leg1_platform,
            market_id=self.market_pair.kalshi.market_id
            if self.leg1_platform == Platform.KALSHI
            else self.market_pair.polymarket.market_id,
            side=self.leg1_side,
            price=self.leg1_price,
            quantity=position_size,
        )

        leg2 = Order(
            platform=self.leg2_platform,
            market_id=self.market_pair.polymarket.market_id
            if self.leg2_platform == Platform.POLYMARKET
            else self.market_pair.kalshi.market_id,
            side=self.leg2_side,
            price=self.leg2_price,
            quantity=position_size,
        )

        return leg1, leg2


class Position(BaseModel):
    """Current position in a market."""

    position_id: str = Field(default_factory=lambda: str(uuid4()))
    platform: Platform
    market_id: str
    side: Side
    quantity: Decimal
    average_entry_price: Decimal
    current_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def total_cost(self) -> Decimal:
        """Calculate total cost basis."""
        return self.quantity * self.average_entry_price

    def update_value(self, current_price: Decimal) -> None:
        """Update current value and PnL."""
        self.current_value = self.quantity * current_price
        self.unrealized_pnl = self.current_value - self.total_cost
        self.updated_at = datetime.utcnow()


# Resolve forward references
from .market import MarketPair

ArbitrageOpportunity.model_rebuild()
