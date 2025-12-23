"""Arbitrage detection engine."""

from decimal import Decimal
from typing import Optional

from loguru import logger

from ..models import ArbitrageOpportunity, MarketPair, Platform, Side
from ..utils import get_settings


class ArbitrageDetector:
    """Detects arbitrage opportunities across market pairs."""

    def __init__(self):
        """Initialize arbitrage detector."""
        self.settings = get_settings()
        self.opportunities_found = 0

    def detect(self, market_pair: MarketPair) -> Optional[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunity in a market pair.

        Args:
            market_pair: Matched market pair

        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        if not market_pair.is_valid:
            return None

        kalshi_ob = market_pair.kalshi.orderbook
        poly_ob = market_pair.polymarket.orderbook

        # Check both strategies
        opportunities = []

        # Strategy 1: Buy YES on Kalshi, NO on Polymarket
        opp1 = self._check_strategy(
            market_pair=market_pair,
            leg1_platform=Platform.KALSHI,
            leg1_side=Side.YES,
            leg1_price=kalshi_ob.best_yes_price,
            leg2_platform=Platform.POLYMARKET,
            leg2_side=Side.NO,
            leg2_price=poly_ob.best_no_price,
            strategy="kalshi_yes_poly_no",
        )
        if opp1:
            opportunities.append(opp1)

        # Strategy 2: Buy NO on Kalshi, YES on Polymarket
        opp2 = self._check_strategy(
            market_pair=market_pair,
            leg1_platform=Platform.KALSHI,
            leg1_side=Side.NO,
            leg1_price=kalshi_ob.best_no_price,
            leg2_platform=Platform.POLYMARKET,
            leg2_side=Side.YES,
            leg2_price=poly_ob.best_yes_price,
            strategy="kalshi_no_poly_yes",
        )
        if opp2:
            opportunities.append(opp2)

        # Return best opportunity
        if opportunities:
            best_opp = max(opportunities, key=lambda x: x.expected_profit)
            self.opportunities_found += 1
            logger.info(
                f"Arbitrage found! Strategy: {best_opp.strategy}, "
                f"Profit: ${best_opp.expected_profit:.4f} ({best_opp.profit_percentage:.2%})"
            )
            return best_opp

        return None

    def _check_strategy(
        self,
        market_pair: MarketPair,
        leg1_platform: Platform,
        leg1_side: Side,
        leg1_price: Decimal,
        leg2_platform: Platform,
        leg2_side: Side,
        leg2_price: Decimal,
        strategy: str,
    ) -> Optional[ArbitrageOpportunity]:
        """
        Check if a specific strategy is profitable.

        Args:
            market_pair: Market pair
            leg1_platform: Platform for first leg
            leg1_side: Side for first leg
            leg1_price: Price for first leg
            leg2_platform: Platform for second leg
            leg2_side: Side for second leg
            leg2_price: Price for second leg
            strategy: Strategy name

        Returns:
            ArbitrageOpportunity if profitable, None otherwise
        """
        # Calculate total cost
        total_cost = leg1_price + leg2_price

        # Add fees
        fees = self._calculate_fees(total_cost)
        total_cost_with_fees = total_cost + fees

        # Calculate profit (payout is always $1.00)
        payout = Decimal("1.0")
        expected_profit = payout - total_cost_with_fees

        # Check if profitable
        if expected_profit <= self.settings.min_profit_threshold:
            return None

        # Calculate profit percentage
        profit_percentage = expected_profit / total_cost_with_fees

        return ArbitrageOpportunity(
            market_pair=market_pair,
            strategy=strategy,
            leg1_platform=leg1_platform,
            leg1_side=leg1_side,
            leg1_price=leg1_price,
            leg2_platform=leg2_platform,
            leg2_side=leg2_side,
            leg2_price=leg2_price,
            total_cost=total_cost_with_fees,
            expected_profit=expected_profit,
            profit_percentage=profit_percentage,
        )

    def _calculate_fees(self, total_cost: Decimal) -> Decimal:
        """
        Calculate total fees for both platforms.

        Args:
            total_cost: Total cost before fees

        Returns:
            Total fees
        """
        # Apply fee rates
        kalshi_fee = total_cost * self.settings.kalshi_fee_rate
        poly_fee = total_cost * self.settings.polymarket_fee_rate

        return kalshi_fee + poly_fee

    def scan_all(self, market_pairs: list[MarketPair]) -> list[ArbitrageOpportunity]:
        """
        Scan all market pairs for arbitrage.

        Args:
            market_pairs: List of market pairs to scan

        Returns:
            List of arbitrage opportunities
        """
        opportunities = []

        for pair in market_pairs:
            opp = self.detect(pair)
            if opp:
                opportunities.append(opp)

        logger.info(
            f"Scanned {len(market_pairs)} pairs, found {len(opportunities)} opportunities"
        )
        return opportunities

    def get_statistics(self) -> dict:
        """
        Get detector statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_opportunities_found": self.opportunities_found,
            "min_profit_threshold": float(self.settings.min_profit_threshold),
            "kalshi_fee_rate": float(self.settings.kalshi_fee_rate),
            "polymarket_fee_rate": float(self.settings.polymarket_fee_rate),
        }
