"""Order execution system."""

import asyncio
from decimal import Decimal
from typing import Optional, Tuple

from loguru import logger

from ..clients import KalshiClient, PolymarketClient
from ..models import (
    ArbitrageOpportunity,
    Order,
    OrderStatus,
    OrderType,
    Platform,
    Trade,
)


class OrderExecutor:
    """Executes arbitrage trades across platforms."""

    def __init__(
        self,
        kalshi_client: Optional[KalshiClient] = None,
        polymarket_client: Optional[PolymarketClient] = None,
    ):
        """
        Initialize order executor.

        Args:
            kalshi_client: Kalshi API client
            polymarket_client: Polymarket API client
        """
        self.kalshi = kalshi_client or KalshiClient()
        self.polymarket = polymarket_client or PolymarketClient()
        self.trades_executed = 0
        self.trades_failed = 0

    async def execute_arbitrage(
        self, opportunity: ArbitrageOpportunity, position_size: Decimal
    ) -> Optional[Trade]:
        """
        Execute an arbitrage trade atomically.

        Args:
            opportunity: Arbitrage opportunity
            position_size: Size to trade in USD

        Returns:
            Trade object if successful, None otherwise
        """
        logger.info(
            f"Executing arbitrage: {opportunity.strategy} with size ${position_size:.2f}"
        )

        # Create orders
        leg1, leg2 = opportunity.create_orders(position_size)

        try:
            # Execute both legs concurrently
            results = await asyncio.gather(
                self._execute_order(leg1),
                self._execute_order(leg2),
                return_exceptions=True,
            )

            leg1_result, leg2_result = results

            # Check for errors
            if isinstance(leg1_result, Exception):
                logger.error(f"Leg 1 failed: {leg1_result}")
                leg1.status = OrderStatus.FAILED
                leg1.error_message = str(leg1_result)
                # Cancel leg 2 if it succeeded
                if not isinstance(leg2_result, Exception):
                    await self._cancel_order(leg2_result)
                self.trades_failed += 1
                return None

            if isinstance(leg2_result, Exception):
                logger.error(f"Leg 2 failed: {leg2_result}")
                leg2.status = OrderStatus.FAILED
                leg2.error_message = str(leg2_result)
                # Cancel leg 1 if it succeeded
                if not isinstance(leg1_result, Exception):
                    await self._cancel_order(leg1_result)
                self.trades_failed += 1
                return None

            # Both legs succeeded
            leg1 = leg1_result
            leg2 = leg2_result

            # Create trade record
            trade = Trade(
                strategy=opportunity.strategy,
                leg1=leg1,
                leg2=leg2,
                expected_profit=opportunity.expected_profit,
            )

            # Mark opportunity as executed
            opportunity.executed = True
            opportunity.trade_id = trade.trade_id

            self.trades_executed += 1
            logger.info(
                f"Trade executed successfully: {trade.trade_id} - "
                f"Expected profit: ${trade.expected_profit:.4f}"
            )

            return trade

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            self.trades_failed += 1
            return None

    async def _execute_order(self, order: Order) -> Order:
        """
        Execute a single order.

        Args:
            order: Order to execute

        Returns:
            Updated order

        Raises:
            Exception if execution fails
        """
        logger.debug(
            f"Executing order: {order.platform} {order.side} "
            f"{order.quantity} @ {order.price}"
        )

        try:
            if order.platform == Platform.KALSHI:
                executed = await self.kalshi.place_order(
                    market_ticker=order.market_id,
                    side=order.side,
                    quantity=int(order.quantity),
                    price=order.price,
                    order_type=order.order_type,
                )
            else:  # Polymarket
                executed = await self.polymarket.place_order(
                    token_id=order.market_id,
                    side=order.side,
                    quantity=order.quantity,
                    price=order.price,
                    order_type=order.order_type,
                )

            # Update order with execution details
            order.status = executed.status
            order.platform_order_id = executed.platform_order_id
            order.filled_quantity = executed.filled_quantity or order.quantity
            order.average_fill_price = executed.average_fill_price or order.price

            # For limit orders that are immediately filled, mark as filled
            if order.order_type in [OrderType.MARKET, OrderType.FOK]:
                order.status = OrderStatus.FILLED

            logger.info(
                f"Order executed: {order.platform_order_id} - "
                f"{order.filled_quantity} filled @ {order.average_fill_price}"
            )

            return order

        except Exception as e:
            order.status = OrderStatus.FAILED
            order.error_message = str(e)
            logger.error(f"Order execution failed: {e}")
            raise

    async def _cancel_order(self, order: Order) -> bool:
        """
        Cancel an order (for rollback).

        Args:
            order: Order to cancel

        Returns:
            True if successful
        """
        if not order.platform_order_id:
            return False

        logger.warning(f"Cancelling order {order.platform_order_id} for rollback")

        try:
            if order.platform == Platform.KALSHI:
                success = await self.kalshi.cancel_order(order.platform_order_id)
            else:
                success = await self.polymarket.cancel_order(order.platform_order_id)

            if success:
                order.status = OrderStatus.CANCELLED
                logger.info(f"Order cancelled: {order.platform_order_id}")

            return success

        except Exception as e:
            logger.error(f"Failed to cancel order {order.platform_order_id}: {e}")
            return False

    async def get_balances(self) -> dict[Platform, Decimal]:
        """
        Get account balances from both platforms.

        Returns:
            Dictionary of platform to balance
        """
        balances = await asyncio.gather(
            self.kalshi.get_balance(),
            self.polymarket.get_balance(),
            return_exceptions=True,
        )

        result = {}

        if isinstance(balances[0], Decimal):
            result[Platform.KALSHI] = balances[0]
        else:
            logger.error(f"Failed to get Kalshi balance: {balances[0]}")
            result[Platform.KALSHI] = Decimal("0")

        if isinstance(balances[1], Decimal):
            result[Platform.POLYMARKET] = balances[1]
        else:
            logger.error(f"Failed to get Polymarket balance: {balances[1]}")
            result[Platform.POLYMARKET] = Decimal("0")

        logger.info(
            f"Balances - Kalshi: ${result[Platform.KALSHI]:.2f}, "
            f"Polymarket: ${result[Platform.POLYMARKET]:.2f}"
        )

        return result

    async def verify_trade(self, trade: Trade) -> bool:
        """
        Verify that both legs of a trade were filled.

        Args:
            trade: Trade to verify

        Returns:
            True if both legs are filled
        """
        # In a production system, you would query the APIs to confirm fills
        # For now, we check the order statuses
        return trade.is_complete

    def get_statistics(self) -> dict:
        """
        Get executor statistics.

        Returns:
            Statistics dictionary
        """
        total_trades = self.trades_executed + self.trades_failed
        success_rate = (
            (self.trades_executed / total_trades * 100) if total_trades > 0 else 0
        )

        return {
            "trades_executed": self.trades_executed,
            "trades_failed": self.trades_failed,
            "total_attempts": total_trades,
            "success_rate": success_rate,
        }
