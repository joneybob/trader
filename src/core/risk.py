"""Risk management system."""

from decimal import Decimal
from typing import Optional

from loguru import logger

from ..models import ArbitrageOpportunity, Trade, Position, Platform
from ..utils import get_settings


class RiskManager:
    """Manages trading risk and position sizing."""

    def __init__(self):
        """Initialize risk manager."""
        self.settings = get_settings()
        self.total_exposure = Decimal("0")
        self.daily_pnl = Decimal("0")
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.circuit_breaker_triggered = False

    def check_opportunity(self, opportunity: ArbitrageOpportunity) -> tuple[bool, str]:
        """
        Check if an opportunity passes risk checks.

        Args:
            opportunity: Arbitrage opportunity to check

        Returns:
            Tuple of (approved, reason)
        """
        # Check circuit breaker
        if self.circuit_breaker_triggered:
            return False, "Circuit breaker triggered"

        # Check trading enabled
        if not self.settings.enable_trading:
            return False, "Trading disabled in settings"

        # Check opportunity is still valid
        if not opportunity.is_profitable:
            return False, "Opportunity no longer profitable"

        # Check profit threshold
        if opportunity.expected_profit < self.settings.min_profit_threshold:
            return False, f"Profit below threshold ({opportunity.expected_profit:.4f})"

        # Check daily loss limit
        if self.daily_pnl < -self.settings.max_daily_loss:
            self.trigger_circuit_breaker("Daily loss limit exceeded")
            return False, "Daily loss limit exceeded"

        # Check drawdown
        if self._calculate_drawdown() > self.settings.max_drawdown:
            self.trigger_circuit_breaker("Max drawdown exceeded")
            return False, "Max drawdown exceeded"

        return True, "Risk checks passed"

    def calculate_position_size(
        self, opportunity: ArbitrageOpportunity, available_balance: Decimal
    ) -> Decimal:
        """
        Calculate safe position size for an opportunity.

        Args:
            opportunity: Arbitrage opportunity
            available_balance: Available balance across platforms

        Returns:
            Position size in USD
        """
        # Start with max position size from settings
        max_size = self.settings.max_position_size

        # Limit by available balance
        max_size = min(max_size, available_balance * Decimal("0.9"))  # 90% of balance

        # Limit by total exposure
        remaining_exposure = self.settings.max_total_exposure - self.total_exposure
        max_size = min(max_size, remaining_exposure)

        # Limit by market liquidity
        min_liquidity = min(
            opportunity.market_pair.kalshi.orderbook.yes_liquidity,
            opportunity.market_pair.kalshi.orderbook.no_liquidity,
            opportunity.market_pair.polymarket.orderbook.yes_liquidity,
            opportunity.market_pair.polymarket.orderbook.no_liquidity,
        )
        max_size = min(max_size, min_liquidity * Decimal("0.5"))  # 50% of liquidity

        # Ensure minimum viable size
        if max_size < Decimal("10"):  # Minimum $10
            logger.warning(f"Position size too small: ${max_size}")
            return Decimal("0")

        logger.info(f"Calculated position size: ${max_size:.2f}")
        return max_size

    def record_trade(self, trade: Trade) -> None:
        """
        Record a completed trade.

        Args:
            trade: Completed trade
        """
        self.trades.append(trade)

        # Update exposure
        if trade.is_complete:
            self.total_exposure += trade.total_cost

            # Update P&L
            if trade.actual_profit:
                self.daily_pnl += trade.actual_profit

        logger.info(
            f"Recorded trade {trade.trade_id}: "
            f"Profit: ${trade.actual_profit:.4f}, Total exposure: ${self.total_exposure:.2f}"
        )

    def update_position(self, position: Position) -> None:
        """
        Update or add a position.

        Args:
            position: Position to update
        """
        key = f"{position.platform}:{position.market_id}:{position.side}"
        self.positions[key] = position
        logger.debug(f"Updated position: {key}")

    def get_exposure_by_platform(self) -> dict[Platform, Decimal]:
        """
        Get total exposure by platform.

        Returns:
            Dictionary of platform to exposure amount
        """
        exposure = {Platform.KALSHI: Decimal("0"), Platform.POLYMARKET: Decimal("0")}

        for position in self.positions.values():
            exposure[position.platform] += position.total_cost

        return exposure

    def get_total_pnl(self) -> Decimal:
        """
        Calculate total P&L from all trades.

        Returns:
            Total P&L
        """
        total_pnl = Decimal("0")
        for trade in self.trades:
            if trade.actual_profit:
                total_pnl += trade.actual_profit
        return total_pnl

    def _calculate_drawdown(self) -> Decimal:
        """
        Calculate current drawdown.

        Returns:
            Drawdown as percentage
        """
        if not self.trades:
            return Decimal("0")

        peak = Decimal("0")
        current = Decimal("0")
        max_drawdown = Decimal("0")

        for trade in self.trades:
            if trade.actual_profit:
                current += trade.actual_profit
                peak = max(peak, current)
                drawdown = (peak - current) / peak if peak > 0 else Decimal("0")
                max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def trigger_circuit_breaker(self, reason: str) -> None:
        """
        Trigger circuit breaker to stop trading.

        Args:
            reason: Reason for triggering
        """
        self.circuit_breaker_triggered = True
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")

    def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker (use with caution)."""
        self.circuit_breaker_triggered = False
        logger.warning("Circuit breaker reset")

    def reset_daily_pnl(self) -> None:
        """Reset daily P&L (call at start of new trading day)."""
        logger.info(f"Resetting daily P&L (was ${self.daily_pnl:.2f})")
        self.daily_pnl = Decimal("0")

    def get_statistics(self) -> dict:
        """
        Get risk management statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_exposure": float(self.total_exposure),
            "daily_pnl": float(self.daily_pnl),
            "total_pnl": float(self.get_total_pnl()),
            "num_trades": len(self.trades),
            "num_positions": len(self.positions),
            "circuit_breaker": self.circuit_breaker_triggered,
            "max_drawdown": float(self._calculate_drawdown()),
            "exposure_by_platform": {
                k.value: float(v) for k, v in self.get_exposure_by_platform().items()
            },
        }
