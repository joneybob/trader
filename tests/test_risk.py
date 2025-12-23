"""Tests for risk management."""

from decimal import Decimal
from datetime import datetime, timedelta

import pytest

from src.core.risk import RiskManager
from src.models import (
    ArbitrageOpportunity,
    Market,
    MarketPair,
    OrderBook,
    Platform,
    Side,
)


@pytest.fixture
def risk_manager():
    """Create risk manager."""
    return RiskManager()


@pytest.fixture
def test_opportunity():
    """Create test arbitrage opportunity."""
    kalshi_market = Market(
        platform=Platform.KALSHI,
        market_id="TEST-K",
        event_id="TEST",
        question="Test question?",
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
        market_id="TEST-P",
        event_id="TEST",
        question="Test question?",
        close_time=datetime.utcnow() + timedelta(days=1),
        orderbook=OrderBook(
            best_yes_price=Decimal("0.48"),
            best_no_price=Decimal("0.45"),
            yes_liquidity=Decimal("1000"),
            no_liquidity=Decimal("1000"),
        ),
        status="active",
    )

    market_pair = MarketPair(
        kalshi=kalshi_market, polymarket=poly_market, description="Test"
    )

    return ArbitrageOpportunity(
        market_pair=market_pair,
        strategy="test_strategy",
        leg1_platform=Platform.KALSHI,
        leg1_side=Side.YES,
        leg1_price=Decimal("0.45"),
        leg2_platform=Platform.POLYMARKET,
        leg2_side=Side.NO,
        leg2_price=Decimal("0.45"),
        total_cost=Decimal("0.90"),
        expected_profit=Decimal("0.05"),
        profit_percentage=Decimal("0.055"),
    )


def test_check_opportunity_passes(risk_manager, test_opportunity):
    """Test opportunity passes risk checks."""
    # Enable trading in settings
    risk_manager.settings.enable_trading = True

    approved, reason = risk_manager.check_opportunity(test_opportunity)

    assert approved is True
    assert reason == "Risk checks passed"


def test_check_opportunity_fails_when_trading_disabled(risk_manager, test_opportunity):
    """Test opportunity fails when trading is disabled."""
    risk_manager.settings.enable_trading = False

    approved, reason = risk_manager.check_opportunity(test_opportunity)

    assert approved is False
    assert "disabled" in reason.lower()


def test_check_opportunity_fails_circuit_breaker(risk_manager, test_opportunity):
    """Test opportunity fails when circuit breaker is triggered."""
    risk_manager.trigger_circuit_breaker("Test reason")

    approved, reason = risk_manager.check_opportunity(test_opportunity)

    assert approved is False
    assert "circuit breaker" in reason.lower()


def test_calculate_position_size(risk_manager, test_opportunity):
    """Test position size calculation."""
    available_balance = Decimal("1000.00")

    position_size = risk_manager.calculate_position_size(
        test_opportunity, available_balance
    )

    # Should be limited by max_position_size
    assert position_size > Decimal("0")
    assert position_size <= risk_manager.settings.max_position_size


def test_calculate_position_size_limited_by_balance(risk_manager, test_opportunity):
    """Test position size limited by available balance."""
    available_balance = Decimal("50.00")  # Less than max_position_size

    position_size = risk_manager.calculate_position_size(
        test_opportunity, available_balance
    )

    # Should be limited by balance (90% of it)
    assert position_size <= available_balance * Decimal("0.9")


def test_circuit_breaker(risk_manager):
    """Test circuit breaker."""
    assert risk_manager.circuit_breaker_triggered is False

    risk_manager.trigger_circuit_breaker("Test")

    assert risk_manager.circuit_breaker_triggered is True

    risk_manager.reset_circuit_breaker()

    assert risk_manager.circuit_breaker_triggered is False


def test_statistics(risk_manager):
    """Test statistics."""
    stats = risk_manager.get_statistics()

    assert "total_exposure" in stats
    assert "daily_pnl" in stats
    assert "total_pnl" in stats
    assert "circuit_breaker" in stats
    assert stats["num_trades"] == 0
