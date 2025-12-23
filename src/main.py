"""Main arbitrage bot application."""

import asyncio
import signal
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from loguru import logger

from .clients import KalshiClient, PolymarketClient
from .core import ArbitrageDetector, OrderExecutor, RiskManager
from .data import EventMatcher, MarketAggregator
from .models import ArbitrageOpportunity, Platform
from .utils import get_settings, setup_logger


class ArbitrageBot:
    """Main arbitrage trading bot."""

    def __init__(self):
        """Initialize the bot."""
        self.settings = get_settings()
        setup_logger()

        # Initialize components
        self.kalshi = KalshiClient()
        self.polymarket = PolymarketClient()
        self.aggregator = MarketAggregator(self.kalshi, self.polymarket)
        self.matcher = EventMatcher()
        self.detector = ArbitrageDetector()
        self.executor = OrderExecutor(self.kalshi, self.polymarket)
        self.risk_manager = RiskManager()

        # State
        self.running = False
        self.iteration = 0
        self.start_time: Optional[datetime] = None

    async def start(self) -> None:
        """Start the bot."""
        logger.info("=" * 80)
        logger.info("ARBITRAGE BOT STARTING")
        logger.info("=" * 80)

        # Validate configuration
        self._validate_config()

        # Connect to APIs
        logger.info("Connecting to APIs...")
        await self.aggregator.connect_all()

        # Verify credentials
        credentials = self.settings.validate_credentials()
        logger.info(f"Credentials validated: {credentials}")

        # Check balances
        balances = await self.executor.get_balances()
        total_balance = sum(balances.values())
        logger.info(f"Total available balance: ${total_balance:.2f}")

        if total_balance < self.settings.max_position_size:
            logger.warning(
                f"Balance (${total_balance:.2f}) is less than max position size "
                f"(${self.settings.max_position_size:.2f})"
            )

        # Setup signal handlers
        self._setup_signal_handlers()

        # Mark as running
        self.running = True
        self.start_time = datetime.utcnow()

        logger.info("Bot started successfully!")
        logger.info(f"Trading enabled: {self.settings.enable_trading}")
        logger.info(f"Check interval: {self.settings.check_interval}s")
        logger.info(f"Min profit threshold: {self.settings.min_profit_threshold}")
        logger.info(f"Max position size: ${self.settings.max_position_size}")
        logger.info("=" * 80)

        # Start main loop
        await self.run()

    async def run(self) -> None:
        """Main bot loop."""
        try:
            while self.running:
                self.iteration += 1
                logger.info(f"\n{'='*80}")
                logger.info(f"Iteration {self.iteration} - {datetime.utcnow()}")
                logger.info(f"{'='*80}")

                try:
                    await self._run_iteration()
                except Exception as e:
                    logger.error(f"Error in iteration {self.iteration}: {e}", exc_info=True)

                # Wait before next iteration
                await asyncio.sleep(self.settings.check_interval)

        except asyncio.CancelledError:
            logger.info("Bot loop cancelled")
        finally:
            await self.shutdown()

    async def _run_iteration(self) -> None:
        """Run a single iteration of the bot."""
        # 1. Fetch market data
        logger.info("Fetching market data...")
        markets = await self.aggregator.fetch_all_markets()

        kalshi_count = len(markets.get(Platform.KALSHI, []))
        poly_count = len(markets.get(Platform.POLYMARKET, []))
        logger.info(f"Fetched {kalshi_count} Kalshi markets, {poly_count} Polymarket markets")

        # 2. Match markets
        logger.info("Matching markets across platforms...")
        market_pairs = self.matcher.match_markets(
            self.aggregator.kalshi_markets, self.aggregator.polymarket_markets
        )
        logger.info(f"Matched {len(market_pairs)} market pairs")

        if not market_pairs:
            logger.warning("No market pairs found to analyze")
            return

        # 3. Update orderbooks for matched pairs
        logger.info("Updating orderbooks...")
        all_markets = []
        for pair in market_pairs:
            all_markets.extend([pair.kalshi, pair.polymarket])

        updated_markets = await self.aggregator.update_orderbooks(all_markets)

        # 4. Detect arbitrage opportunities
        logger.info("Scanning for arbitrage opportunities...")
        opportunities = self.detector.scan_all(market_pairs)

        if not opportunities:
            logger.info("No arbitrage opportunities found")
            self._log_statistics()
            return

        # 5. Sort by profitability
        opportunities.sort(key=lambda x: x.expected_profit, reverse=True)

        # 6. Execute profitable opportunities
        logger.info(f"Found {len(opportunities)} opportunities, evaluating...")
        executed_count = 0

        for i, opp in enumerate(opportunities, 1):
            logger.info(
                f"\nOpportunity {i}/{len(opportunities)}: "
                f"{opp.strategy} - Profit: ${opp.expected_profit:.4f} ({opp.profit_percentage:.2%})"
            )

            # Risk check
            approved, reason = self.risk_manager.check_opportunity(opp)
            if not approved:
                logger.warning(f"Opportunity rejected: {reason}")
                continue

            # Get current balances
            balances = await self.executor.get_balances()
            total_balance = sum(balances.values())

            # Calculate position size
            position_size = self.risk_manager.calculate_position_size(opp, total_balance)
            if position_size <= 0:
                logger.warning("Position size too small, skipping")
                continue

            # Execute trade
            trade = await self.executor.execute_arbitrage(opp, position_size)
            if trade:
                # Record trade
                self.risk_manager.record_trade(trade)
                executed_count += 1
                logger.success(
                    f"Trade executed! ID: {trade.trade_id}, "
                    f"Size: ${position_size:.2f}, "
                    f"Expected profit: ${trade.expected_profit:.4f}"
                )

                # Verify trade
                verified = await self.executor.verify_trade(trade)
                if verified:
                    logger.success("Trade verified successfully")
                else:
                    logger.warning("Trade verification failed")
            else:
                logger.error("Trade execution failed")

        logger.info(f"\nExecuted {executed_count} trades this iteration")
        self._log_statistics()

    def _validate_config(self) -> None:
        """Validate configuration."""
        logger.info("Validating configuration...")

        if not self.settings.enable_trading:
            logger.warning("Trading is DISABLED - running in dry-run mode")

        if self.settings.min_profit_threshold <= 0:
            raise ValueError("Min profit threshold must be positive")

        if self.settings.max_position_size <= 0:
            raise ValueError("Max position size must be positive")

        logger.info("Configuration validated successfully")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _log_statistics(self) -> None:
        """Log bot statistics."""
        logger.info("\n" + "=" * 80)
        logger.info("STATISTICS")
        logger.info("=" * 80)

        # Runtime
        if self.start_time:
            runtime = datetime.utcnow() - self.start_time
            logger.info(f"Runtime: {runtime}")

        # Detector stats
        detector_stats = self.detector.get_statistics()
        logger.info(
            f"Opportunities found: {detector_stats['total_opportunities_found']}"
        )

        # Executor stats
        executor_stats = self.executor.get_statistics()
        logger.info(
            f"Trades executed: {executor_stats['trades_executed']} / "
            f"{executor_stats['total_attempts']} "
            f"({executor_stats['success_rate']:.1f}% success rate)"
        )

        # Risk stats
        risk_stats = self.risk_manager.get_statistics()
        logger.info(f"Total P&L: ${risk_stats['total_pnl']:.2f}")
        logger.info(f"Daily P&L: ${risk_stats['daily_pnl']:.2f}")
        logger.info(f"Total exposure: ${risk_stats['total_exposure']:.2f}")
        logger.info(f"Max drawdown: {risk_stats['max_drawdown']:.2%}")
        logger.info(f"Active positions: {risk_stats['num_positions']}")
        logger.info(
            f"Circuit breaker: {'TRIGGERED' if risk_stats['circuit_breaker'] else 'OK'}"
        )

        logger.info("=" * 80)

    async def shutdown(self) -> None:
        """Shutdown the bot gracefully."""
        logger.info("\n" + "=" * 80)
        logger.info("SHUTTING DOWN")
        logger.info("=" * 80)

        # Log final statistics
        self._log_statistics()

        # Close connections
        logger.info("Closing API connections...")
        await self.aggregator.close_all()

        # Save any state
        logger.info("Saving state...")
        # TODO: Save positions, trades to database

        logger.info("Shutdown complete")
        logger.info("=" * 80)


async def main():
    """Main entry point."""
    bot = ArbitrageBot()
    await bot.start()


if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
