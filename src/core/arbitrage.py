"""Arbitrage detection engine."""

import math
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
        # Calculate total cost before fees
        total_cost = leg1_price + leg2_price

        # Determine which leg is Kalshi and which is Polymarket
        if leg1_platform == Platform.KALSHI:
            kalshi_price = leg1_price
            poly_price = leg2_price
            kalshi_market_ticker = market_pair.kalshi.market_id
        else:
            kalshi_price = leg2_price
            poly_price = leg1_price
            kalshi_market_ticker = market_pair.kalshi.market_id

        # Calculate fees using a standard position size (will be recalculated at execution)
        # For detection purposes, use 100 contracts as reference
        reference_contracts = Decimal("100")
        fees = self._calculate_fees(
            kalshi_price, poly_price, reference_contracts, kalshi_market_ticker
        )

        # Calculate per-contract fee rate for the opportunity
        fee_per_contract = fees / reference_contracts
        total_cost_with_fees = total_cost + fee_per_contract

        # Calculate profit (payout is always $1.00 per contract)
        payout = Decimal("1.0")
        expected_profit = payout - total_cost_with_fees

        # Check if profitable
        if expected_profit <= self.settings.min_profit_threshold:
            return None

        # Calculate profit percentage
        profit_percentage = expected_profit / total_cost_with_fees if total_cost_with_fees > 0 else Decimal("0")

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

    def _calculate_kalshi_fee(
        self, price: Decimal, contracts: Decimal, market_ticker: str, is_maker: bool = False
    ) -> Decimal:
        """
        Calculate Kalshi fee using their actual formula.

        Formula: ceil(fee_rate × C × P × (1-P))
        Where:
        - fee_rate = 0.07 for takers, 0.0175 for makers, 0.035 for special markets
        - C = number of contracts
        - P = price per contract (in dollars)
        - ceil = round up to next cent

        Args:
            price: Price per contract (0-1)
            contracts: Number of contracts
            market_ticker: Market ticker (to check for special markets)
            is_maker: Whether this is a maker order (resting)

        Returns:
            Fee in dollars
        """
        # Determine fee rate
        if self.settings.is_special_kalshi_market(market_ticker):
            fee_rate = self.settings.kalshi_special_market_fee_rate
        elif is_maker:
            fee_rate = self.settings.kalshi_maker_fee_rate
        else:
            fee_rate = self.settings.kalshi_taker_fee_rate

        # Calculate: fee_rate × C × P × (1-P)
        p_variance = price * (Decimal("1") - price)
        fee_dollars = fee_rate * contracts * p_variance

        # Round up to next cent
        fee_cents = math.ceil(fee_dollars * 100)
        fee_rounded = Decimal(fee_cents) / Decimal("100")

        return fee_rounded

    def _calculate_polymarket_fee(self, cost: Decimal) -> Decimal:
        """
        Calculate Polymarket fee (simplified as percentage of cost).

        Args:
            cost: Total cost

        Returns:
            Fee in dollars
        """
        return cost * self.settings.polymarket_fee_rate

    def _calculate_fees(
        self,
        kalshi_price: Decimal,
        poly_price: Decimal,
        position_size: Decimal,
        kalshi_market_ticker: str,
    ) -> Decimal:
        """
        Calculate total fees for both platforms.

        Args:
            kalshi_price: Kalshi contract price (0-1)
            poly_price: Polymarket contract price (0-1)
            position_size: Number of contracts to trade
            kalshi_market_ticker: Kalshi market ticker

        Returns:
            Total fees in dollars
        """
        # Kalshi fee using their formula (assuming taker, immediate execution)
        kalshi_fee = self._calculate_kalshi_fee(
            kalshi_price, position_size, kalshi_market_ticker, is_maker=False
        )

        # Polymarket fee (percentage of cost)
        poly_cost = poly_price * position_size
        poly_fee = self._calculate_polymarket_fee(poly_cost)

        total_fees = kalshi_fee + poly_fee

        logger.debug(
            f"Fee calculation: Kalshi ${kalshi_fee:.4f}, Poly ${poly_fee:.4f}, "
            f"Total ${total_fees:.4f} for {position_size} contracts"
        )

        return total_fees

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
            "kalshi_taker_fee_rate": float(self.settings.kalshi_taker_fee_rate),
            "kalshi_maker_fee_rate": float(self.settings.kalshi_maker_fee_rate),
            "kalshi_special_market_fee_rate": float(self.settings.kalshi_special_market_fee_rate),
            "polymarket_fee_rate": float(self.settings.polymarket_fee_rate),
        }
