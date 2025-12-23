# Prediction Market Arbitrage Bot - Architecture Design

## Overview
An automated trading system that identifies and executes arbitrage opportunities across Kalshi and Polymarket prediction markets.

## Core Concept
Arbitrage exists when the combined cost of buying opposite outcomes across two platforms is less than the guaranteed payout, accounting for fees.

**Example:**
- Kalshi: YES costs $0.65
- Polymarket: NO costs $0.30
- Total cost: $0.95
- Payout: $1.00
- Profit: $0.05 (before fees)

## System Architecture

### 1. Market Data Layer
**Purpose:** Fetch and normalize market data from both platforms

**Components:**
- `KalshiClient`: REST API client for Kalshi
- `PolymarketClient`: API client for Polymarket (CLOB + subgraph)
- `DataNormalizer`: Standardize market data format
- `EventMatcher`: Match equivalent markets across platforms

**Data Flow:**
```
Kalshi API → KalshiClient → Normalized Market Data → Event Matcher
Polymarket API → PolymarketClient → Normalized Market Data → Event Matcher
```

### 2. Arbitrage Detection Engine
**Purpose:** Identify profitable arbitrage opportunities

**Logic:**
```python
for matched_event in matched_events:
    kalshi_yes = matched_event.kalshi.yes_price
    kalshi_no = matched_event.kalshi.no_price
    poly_yes = matched_event.polymarket.yes_price
    poly_no = matched_event.polymarket.no_price

    # Strategy 1: Buy YES on A, NO on B
    cost_1 = kalshi_yes + poly_no
    profit_1 = 1.0 - cost_1 - fees

    # Strategy 2: Buy NO on A, YES on B
    cost_2 = kalshi_no + poly_yes
    profit_2 = 1.0 - cost_2 - fees

    if profit_1 > min_profit_threshold:
        queue_trade(kalshi_yes_order, poly_no_order)
    elif profit_2 > min_profit_threshold:
        queue_trade(kalshi_no_order, poly_yes_order)
```

### 3. Order Execution System
**Purpose:** Execute trades atomically and handle failures

**Features:**
- Atomic execution (both legs or neither)
- Order validation before submission
- Balance checking
- Retry logic with exponential backoff
- Rollback on partial failure

**Execution Flow:**
```
1. Pre-trade validation
   - Check account balances
   - Verify market liquidity
   - Confirm prices haven't moved

2. Simultaneous order placement
   - Submit orders to both platforms concurrently
   - Use asyncio for parallel execution

3. Post-trade verification
   - Confirm both fills
   - Log trade details
   - Update position tracking

4. Error handling
   - Rollback/hedge if only one leg fills
   - Alert on failures
   - Log for analysis
```

### 4. Risk Management
**Purpose:** Protect capital and limit exposure

**Controls:**
- **Position Sizing:** Max size per trade (e.g., $100)
- **Exposure Limits:** Max total exposure per market/platform
- **Drawdown Limits:** Stop trading if losses exceed threshold
- **Minimum Profit:** Only execute if profit > threshold (e.g., 2%)
- **Fee Awareness:** Account for platform fees in calculations

**Fee Structure:**
- Kalshi: Trading fees vary (typically 1-7% on profits)
- Polymarket: Trading fees + gas costs (blockchain)

### 5. Monitoring & Alerting
**Purpose:** Track performance and catch issues

**Metrics:**
- Arbitrage opportunities detected
- Trades executed / failed
- Profit/loss per trade
- Account balances
- API response times
- Error rates

**Alerts:**
- Failed trades
- Balance thresholds
- API connectivity issues
- Unusual market conditions

## Technology Stack

### Language: Python 3.11+
**Rationale:**
- Excellent async support (asyncio)
- Rich ecosystem for API clients
- Great for financial calculations
- Easy deployment

### Key Libraries:
- `aiohttp`: Async HTTP requests
- `web3.py`: Polymarket blockchain interaction
- `pydantic`: Data validation
- `loguru`: Logging
- `python-dotenv`: Configuration
- `pytest`: Testing

### Data Storage:
- **SQLite:** Trade history, positions
- **Redis (optional):** Real-time cache for market data

## Component Details

### API Clients

#### Kalshi Client
```python
class KalshiClient:
    - authenticate()
    - get_markets(event_ticker: str)
    - get_orderbook(market_ticker: str)
    - place_order(side: Side, quantity: int, price: Decimal)
    - get_balance()
    - get_positions()
```

#### Polymarket Client
```python
class PolymarketClient:
    - get_markets(condition_id: str)
    - get_orderbook(token_id: str)
    - place_order(side: Side, quantity: Decimal, price: Decimal)
    - get_balance()
    - sign_order() # Blockchain signing
```

### Event Matching Strategy

**Challenge:** Same event has different identifiers across platforms

**Approach:**
1. **Manual Mapping:** Config file with known market pairs
2. **Fuzzy Matching:** Use string similarity on market titles
3. **Hybrid:** Manual overrides + automated matching

**Example Config:**
```json
{
  "market_pairs": [
    {
      "kalshi": "INXD-23DEC31",
      "polymarket": "0x1234...",
      "description": "Will SPX close above 4500 on Dec 31?"
    }
  ]
}
```

### Arbitrage Detection Algorithm

```python
def detect_arbitrage(market_pair: MarketPair) -> Optional[ArbitrageOpportunity]:
    """
    Detect arbitrage between matched markets
    """
    # Get best prices
    kalshi_yes = market_pair.kalshi.best_yes_price
    kalshi_no = market_pair.kalshi.best_no_price
    poly_yes = market_pair.polymarket.best_yes_price
    poly_no = market_pair.polymarket.best_no_price

    # Calculate opportunities
    opportunities = [
        {
            "strategy": "kalshi_yes_poly_no",
            "cost": kalshi_yes + poly_no,
            "legs": [
                {"platform": "kalshi", "side": "YES", "price": kalshi_yes},
                {"platform": "polymarket", "side": "NO", "price": poly_no}
            ]
        },
        {
            "strategy": "kalshi_no_poly_yes",
            "cost": kalshi_no + poly_yes,
            "legs": [
                {"platform": "kalshi", "side": "NO", "price": kalshi_no},
                {"platform": "polymarket", "side": "YES", "price": poly_yes}
            ]
        }
    ]

    # Find best opportunity
    for opp in opportunities:
        gross_profit = 1.0 - opp["cost"]
        net_profit = gross_profit - calculate_fees(opp)

        if net_profit > MIN_PROFIT_THRESHOLD:
            return ArbitrageOpportunity(
                market_pair=market_pair,
                strategy=opp["strategy"],
                expected_profit=net_profit,
                legs=opp["legs"]
            )

    return None
```

## Configuration

### Environment Variables
```bash
# API Credentials
KALSHI_EMAIL=your@email.com
KALSHI_PASSWORD=your_password
POLYMARKET_PRIVATE_KEY=0x...

# Trading Parameters
MIN_PROFIT_THRESHOLD=0.02  # 2%
MAX_POSITION_SIZE=100.00   # $100
MAX_TOTAL_EXPOSURE=1000.00 # $1000
CHECK_INTERVAL=5.0         # seconds

# Risk Management
ENABLE_TRADING=false       # Dry-run mode
MAX_DAILY_LOSS=100.00
```

## Deployment Architecture

### Development
```
Local Machine
├── Bot Process (main.py)
├── SQLite Database
└── Logs
```

### Production
```
Cloud Server (AWS/GCP/DigitalOcean)
├── Docker Container
│   ├── Bot Process
│   ├── Health Check Endpoint
│   └── Monitoring Agent
├── PostgreSQL (trade history)
├── Redis (market cache)
└── Log Aggregation (CloudWatch/Datadog)
```

## Safety Features

1. **Dry-Run Mode:** Test without real trades
2. **Trade Logging:** Complete audit trail
3. **Balance Checks:** Verify before each trade
4. **Price Staleness Check:** Reject old prices
5. **Circuit Breaker:** Stop on repeated failures
6. **Gradual Rollout:** Start with small positions

## Operational Workflow

### Startup
1. Load configuration
2. Authenticate with both platforms
3. Verify API connectivity
4. Load market pairs mapping
5. Check account balances
6. Start monitoring loop

### Main Loop
```
while running:
    1. Fetch market data from both platforms
    2. Match markets
    3. Detect arbitrage opportunities
    4. Validate opportunities
    5. Execute profitable trades
    6. Update positions
    7. Log metrics
    8. Sleep for check_interval
```

### Shutdown
1. Cancel pending orders
2. Log final positions
3. Generate session report
4. Close API connections

## Future Enhancements

1. **Additional Markets:** Manifold, PredictIt, etc.
2. **Machine Learning:** Predict arbitrage opportunity duration
3. **Advanced Matching:** NLP for automatic event matching
4. **Hedging Strategies:** Manage imbalanced positions
5. **Multi-leg Arbitrage:** More than 2 markets
6. **WebSocket Feeds:** Lower latency data
7. **Smart Order Routing:** Optimize execution

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| API Downtime | Miss opportunities | Retry logic, fallback endpoints |
| Partial Fill | Unhedged position | Cancel other leg, manual hedge |
| Price Movement | Opportunity disappears | Fast execution, price validation |
| Fee Calculation Error | Unprofitable trade | Conservative fee estimates |
| Account Suspension | Cannot trade | Follow platform rules, rate limits |
| Smart Contract Bug | Loss of funds | Start small, audit contracts |

## Success Metrics

1. **Opportunity Detection Rate:** Arbitrages found per hour
2. **Execution Success Rate:** % of detected arbitrages executed
3. **Average Profit per Trade:** Net profit after fees
4. **Sharpe Ratio:** Risk-adjusted returns
5. **Uptime:** % of time bot is running
6. **Error Rate:** Failed trades / total trades

## Initial Development Phases

### Phase 1: Foundation (Week 1)
- [ ] Project structure
- [ ] Kalshi API client
- [ ] Polymarket API client
- [ ] Basic data models
- [ ] Configuration system

### Phase 2: Core Logic (Week 2)
- [ ] Event matching
- [ ] Arbitrage detection
- [ ] Trade execution (dry-run)
- [ ] Risk management
- [ ] Logging & monitoring

### Phase 3: Testing & Hardening (Week 3)
- [ ] Unit tests
- [ ] Integration tests
- [ ] Error handling
- [ ] Performance optimization
- [ ] Documentation

### Phase 4: Production (Week 4)
- [ ] Live testing with small amounts
- [ ] Monitoring dashboard
- [ ] Alerting system
- [ ] Production deployment
- [ ] Performance tuning
