"""Tests for arbitrage detection."""

from decimal import Decimal
from datetime import datetime, timedelta

import pytest

from src.core.arbitrage import ArbitrageDetector
from src.models import Market, MarketPair, OrderBook, Platform


@pytest.fixture
def detector():
    """Create arbitrage detector."""
    return ArbitrageDetector()


@pytest.fixture
def profitable_market_pair():
    """Create a market pair with arbitrage opportunity."""
    kalshi_market = Market(
        platform=Platform.KALSHI,
        market_id="TEST-KALSHI",
        event_id="TEST-EVENT",
        question="Will it rain tomorrow?",
        close_time=datetime.utcnow() + timedelta(days=1),
        orderbook=OrderBook(
            best_yes_price=Decimal("0.45"),
            best_no_price=Decimal("0.50"),
            yes_liquidity=Decimal("1000"),
            no_liquidity=Decimal("1000"),
        ),
        status="active",
    )

    poly_market = Market(
        platform=Platform.POLYMARKET,
        market_id="TEST-POLY",
        event_id="TEST-EVENT",
        question="Will it rain tomorrow?",
        close_time=datetime.utcnow() + timedelta(days=1),
        orderbook=OrderBook(
            best_yes_price=Decimal("0.48"),
            best_no_price=Decimal("0.45"),
            yes_liquidity=Decimal("1000"),
            no_liquidity=Decimal("1000"),
        ),
        status="active",
    )

    return MarketPair(
        kalshi=kalshi_market,
        polymarket=poly_market,
        description="Test market pair with arbitrage",
    )


@pytest.fixture
def unprofitable_market_pair():
    """Create a market pair without arbitrage opportunity."""
    kalshi_market = Market(
        platform=Platform.KALSHI,
        market_id="TEST-KALSHI-2",
        event_id="TEST-EVENT-2",
        question="Will it snow tomorrow?",
        close_time=datetime.utcnow() + timedelta(days=1),
        orderbook=OrderBook(
            best_yes_price=Decimal("0.50"),
            best_no_price=Decimal("0.50"),
            yes_liquidity=Decimal("1000"),
            no_liquidity=Decimal("1000"),
        ),
        status="active",
    )

    poly_market = Market(
        platform=Platform.POLYMARKET,
        market_id="TEST-POLY-2",
        event_id="TEST-EVENT-2",
        question="Will it snow tomorrow?",
        close_time=datetime.utcnow() + timedelta(days=1),
        orderbook=OrderBook(
            best_yes_price=Decimal("0.50"),
            best_no_price=Decimal("0.50"),
            yes_liquidity=Decimal("1000"),
            no_liquidity=Decimal("1000"),
        ),
        status="active",
    )

    return MarketPair(
        kalshi=kalshi_market,
        polymarket=poly_market,
        description="Test market pair without arbitrage",
    )


def test_detect_profitable_arbitrage(detector, profitable_market_pair):
    """Test detection of profitable arbitrage."""
    opportunity = detector.detect(profitable_market_pair)

    assert opportunity is not None
    assert opportunity.expected_profit > Decimal("0")
    assert opportunity.is_profitable
    assert opportunity.strategy in ["kalshi_yes_poly_no", "kalshi_no_poly_yes"]


def test_no_arbitrage_when_unprofitable(detector, unprofitable_market_pair):
    """Test no arbitrage detected when unprofitable."""
    opportunity = detector.detect(unprofitable_market_pair)

    assert opportunity is None


def test_scan_multiple_pairs(detector, profitable_market_pair, unprofitable_market_pair):
    """Test scanning multiple market pairs."""
    opportunities = detector.scan_all([profitable_market_pair, unprofitable_market_pair])

    assert len(opportunities) == 1
    assert opportunities[0].market_pair == profitable_market_pair


def test_fee_calculation(detector):
    """Test fee calculation."""
    total_cost = Decimal("0.90")
    fees = detector._calculate_fees(total_cost)

    # Fees should be based on settings
    expected_fees = total_cost * detector.settings.total_fee_rate
    assert fees == expected_fees


def test_statistics(detector, profitable_market_pair):
    """Test statistics tracking."""
    initial_stats = detector.get_statistics()
    assert initial_stats["total_opportunities_found"] == 0

    # Detect an opportunity
    detector.detect(profitable_market_pair)

    updated_stats = detector.get_statistics()
    assert updated_stats["total_opportunities_found"] == 1
