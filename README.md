# Prediction Market Arbitrage Bot

An automated trading system that identifies and executes arbitrage opportunities across **Kalshi** and **Polymarket** prediction markets.

## Overview

This bot:
- Monitors prediction markets on Kalshi and Polymarket in real-time
- Detects arbitrage opportunities when the combined cost of opposite outcomes is less than the guaranteed payout
- Executes atomic trades across both platforms
- Manages risk through position sizing, exposure limits, and circuit breakers
- Provides comprehensive logging and monitoring

## How It Works

### Arbitrage Strategy

The bot exploits price discrepancies across platforms:

**Example:**
- Kalshi: YES costs $0.65
- Polymarket: NO costs $0.30
- Total cost: $0.95
- Guaranteed payout: $1.00
- **Profit: $0.05** (before fees)

By buying YES on one platform and NO on the other, you lock in a guaranteed profit regardless of the outcome.

## Features

### Core Functionality
- ✅ Real-time market data aggregation from Kalshi and Polymarket
- ✅ Intelligent event matching across platforms (manual + fuzzy)
- ✅ Arbitrage detection with configurable profit thresholds
- ✅ Atomic order execution (both legs or neither)
- ✅ Comprehensive risk management
- ✅ Position sizing and exposure limits
- ✅ Circuit breaker for safety

### Risk Management
- Position size limits
- Total exposure caps
- Daily loss limits
- Maximum drawdown protection
- Circuit breaker auto-stop
- Balance verification before trades

### Monitoring
- Real-time logging with rotation
- Trade history tracking
- Performance statistics
- P&L reporting
- Error tracking and alerting

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Kalshi account (demo or production)
- Polymarket account with USDC
- API credentials for both platforms

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd trader
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your credentials and settings
```

4. **Configure market pairs** (optional)
```bash
# Edit config/market_pairs.json to add manual market mappings
```

### Configuration

Edit `.env` file with your settings:

```bash
# API Credentials
KALSHI_EMAIL=your@email.com
KALSHI_PASSWORD=your_password
POLYMARKET_PRIVATE_KEY=0x...

# Trading Parameters
ENABLE_TRADING=false  # Start with false for testing!
MIN_PROFIT_THRESHOLD=0.02  # 2% minimum profit
MAX_POSITION_SIZE=100.00  # Max $100 per position
CHECK_INTERVAL=5.0  # Check every 5 seconds

# Risk Management
MAX_DAILY_LOSS=100.00
MAX_TOTAL_EXPOSURE=1000.00
```

### Running the Bot

**Dry-run mode (recommended first):**
```bash
python -m src.main
```

**Live trading (after testing):**
```bash
# Set ENABLE_TRADING=true in .env
python -m src.main
```

### Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
trader/
├── src/
│   ├── main.py                 # Main application
│   ├── clients/
│   │   ├── kalshi.py          # Kalshi API client
│   │   └── polymarket.py      # Polymarket API client
│   ├── models/
│   │   ├── market.py          # Market data models
│   │   └── trade.py           # Trade and order models
│   ├── core/
│   │   ├── arbitrage.py       # Arbitrage detection engine
│   │   ├── executor.py        # Order execution system
│   │   └── risk.py            # Risk management
│   ├── data/
│   │   ├── aggregator.py      # Market data aggregator
│   │   └── matcher.py         # Event matching logic
│   └── utils/
│       ├── config.py          # Configuration management
│       └── logger.py          # Logging setup
├── tests/                      # Test suite
├── config/
│   └── market_pairs.json      # Manual market mappings
├── logs/                       # Log files
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── DESIGN.md                 # Architecture documentation
└── README.md                 # This file
```

## API Documentation

### Kalshi
- **Docs:** https://docs.kalshi.com
- **API Reference:** https://trading-api.readme.io/reference
- **Mode:** Demo (https://demo-api.kalshi.co) or Production (https://trading-api.kalshi.com)
- **Fees:** Currently 0% trading fees
- **Authentication:** Email/password, token expires every 30 minutes

### Polymarket
- **Docs:** https://docs.polymarket.com
- **CLOB API:** https://clob.polymarket.com
- **Python Client:** https://github.com/Polymarket/py-clob-client
- **Network:** Polygon (Chain ID 137)
- **Fees:** ~2% including gas costs
- **Authentication:** Private key-based (L1 + L2)

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_TRADING` | Enable real trading | `false` |
| `MIN_PROFIT_THRESHOLD` | Minimum profit % to execute | `0.02` (2%) |
| `MAX_POSITION_SIZE` | Max USD per position | `100.00` |
| `MAX_TOTAL_EXPOSURE` | Max total exposure | `1000.00` |
| `CHECK_INTERVAL` | Seconds between checks | `5.0` |
| `MAX_DAILY_LOSS` | Max daily loss before stop | `100.00` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Market Pair Mapping

Edit `config/market_pairs.json` to manually map equivalent markets:

```json
{
  "market_pairs": [
    {
      "kalshi": "INXD-23DEC31-T4500",
      "polymarket": "0x1234567890abcdef",
      "description": "S&P 500 above 4500 on Dec 31"
    }
  ]
}
```

The bot also uses fuzzy matching for automatic discovery.

## Safety Features

### 1. Dry-Run Mode
- Default: `ENABLE_TRADING=false`
- Detects opportunities without executing trades
- Perfect for testing and validation

### 2. Circuit Breaker
- Automatically stops trading on:
  - Daily loss limit exceeded
  - Max drawdown exceeded
  - Repeated execution failures
- Requires manual reset

### 3. Atomic Execution
- Both legs execute or neither
- Automatic rollback on partial fills
- Position verification after trades

### 4. Pre-Trade Validation
- Balance checking
- Liquidity verification
- Price staleness checks
- Risk limit enforcement

## Monitoring

### Logs

Logs are written to:
- **Console:** Real-time colored output
- **File:** `logs/arbitrage_bot.log` (rotated at 100MB, 30-day retention)

### Statistics

The bot logs statistics each iteration:
- Opportunities detected
- Trades executed/failed
- Total P&L
- Daily P&L
- Current exposure
- Drawdown
- Circuit breaker status

### Example Output

```
================================================================================
Iteration 42 - 2025-01-15 10:30:00
================================================================================
Fetching market data...
Fetched 150 Kalshi markets, 200 Polymarket markets
Matching markets across platforms...
Matched 25 market pairs
Scanning for arbitrage opportunities...

Arbitrage found! Strategy: kalshi_yes_poly_no, Profit: $0.0450 (4.50%)
Trade executed! ID: abc123, Size: $100.00, Expected profit: $0.0450

STATISTICS
================================================================================
Runtime: 0:45:30
Opportunities found: 15
Trades executed: 8 / 10 (80.0% success rate)
Total P&L: $0.32
Daily P&L: $0.32
Total exposure: $800.00
Circuit breaker: OK
================================================================================
```

## Risk Disclosure

⚠️ **WARNING:** Trading prediction markets carries risk.

- Past performance does not guarantee future results
- Markets can move quickly, eliminating arbitrage windows
- Platform fees reduce profits
- API failures can result in unhedged positions
- Network latency affects execution
- Regulatory requirements vary by jurisdiction

**USE AT YOUR OWN RISK. Start with small positions and test thoroughly.**

## Development

### Adding Features

1. Create feature branch
2. Implement changes
3. Add tests
4. Update documentation
5. Submit pull request

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_arbitrage.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type checking
mypy src/
```

## Troubleshooting

### Common Issues

**1. API Authentication Failures**
- Verify credentials in `.env`
- Check API key permissions
- Ensure Kalshi mode (demo/prod) is correct

**2. No Opportunities Found**
- Markets may be efficiently priced
- Adjust `MIN_PROFIT_THRESHOLD` lower (carefully)
- Add more manual market mappings
- Check that markets are active

**3. Trade Execution Failures**
- Verify account balances
- Check platform status/downtime
- Review error logs for details
- Ensure sufficient liquidity

**4. High Fees Eating Profits**
- Include gas costs for Polymarket
- Account for slippage
- Use larger position sizes
- Focus on higher-profit opportunities

## Roadmap

- [ ] WebSocket feeds for lower latency
- [ ] Additional platforms (Manifold, PredictIt)
- [ ] Advanced NLP for market matching
- [ ] Machine learning for opportunity prediction
- [ ] Dashboard UI for monitoring
- [ ] Telegram/Slack alerts
- [ ] Database persistence
- [ ] Multi-leg arbitrage (3+ markets)

## License

MIT License

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Review the DESIGN.md for architecture details
- Check logs for debugging information

## Disclaimer

This software is provided "as is" without warranty. The authors are not responsible for any losses incurred through use of this software. Always comply with platform terms of service and local regulations.
