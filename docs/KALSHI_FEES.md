# Kalshi Fee Structure Explained

## Overview

Kalshi charges **dynamic fees** based on the uncertainty of the contract, using the formula:

```
fees = ceil(fee_rate × C × P × (1-P))
```

Where:
- **fee_rate**: Base fee rate (varies by order type and market)
- **C**: Number of contracts
- **P**: Price per contract in dollars (0 to 1)
- **ceil**: Round up to the next cent

## Key Insight: The P × (1-P) Term

The `P × (1-P)` term represents the **variance** of a binary outcome:

- At **P = 0.50** (50/50 odds): Variance = 0.50 × 0.50 = **0.25** (maximum)
- At **P = 0.10** or **P = 0.90**: Variance = 0.10 × 0.90 = **0.09**
- At **P = 0.01** or **P = 0.99**: Variance = 0.01 × 0.99 = **0.0099** (minimum)

This means:
- **Higher fees** on uncertain markets (near 50/50)
- **Lower fees** on more certain markets (near 0 or 1)

## Fee Rates

### General Markets (Most markets)

**Taker Orders** (immediate execution):
- fee_rate = **0.07** (7%)
- Formula: `ceil(0.07 × C × P × (1-P))`

**Maker Orders** (resting on orderbook):
- fee_rate = **0.0175** (1.75%)
- Formula: `ceil(0.0175 × C × P × (1-P))`

### Special Markets (S&P 500, NASDAQ-100)

Markets where ticker starts with `INX` or `NASDAQ100`:
- fee_rate = **0.035** (3.5%)
- Formula: `ceil(0.035 × C × P × (1-P))`

## Fee Examples

### Example 1: General Market, 100 contracts

| Price | P×(1-P) | Fee (7%) | Fee (3.5% special) |
|-------|---------|----------|-------------------|
| $0.01 | 0.0099 | $0.07 | $0.04 |
| $0.10 | 0.09 | $0.63 | $0.32 |
| $0.25 | 0.1875 | $1.32 | $0.66 |
| **$0.50** | **0.25** | **$1.75** | **$0.88** |
| $0.75 | 0.1875 | $1.32 | $0.66 |
| $0.90 | 0.09 | $0.63 | $0.32 |
| $0.99 | 0.0099 | $0.07 | $0.04 |

Notice how fees peak at $0.50 (most uncertain) and drop toward extremes.

### Example 2: Single Contract

| Price | General Fee | S&P/NASDAQ Fee | Maker Fee |
|-------|-------------|----------------|-----------|
| $0.01 | $0.01 | $0.01 | $0.01 |
| $0.25 | $0.02 | $0.01 | $0.01 |
| $0.50 | $0.02 | $0.01 | $0.01 |
| $0.75 | $0.02 | $0.01 | $0.01 |
| $0.99 | $0.01 | $0.01 | $0.01 |

Single contracts have minimum $0.01 fee due to rounding.

## Impact on Arbitrage

### Scenario: Kalshi YES @ $0.45, Polymarket NO @ $0.45

For 100 contracts:

**Kalshi Cost:**
- Contracts: 100 × $0.45 = $45.00
- Fee: ceil(0.07 × 100 × 0.45 × 0.55) = ceil(1.7325) = **$1.74**
- Total: **$46.74**

**Polymarket Cost:**
- Contracts: 100 × $0.45 = $45.00
- Fee (2%): $45.00 × 0.02 = **$0.90**
- Total: **$45.90**

**Combined:**
- Total Cost: $46.74 + $45.90 = **$92.64**
- Payout: **$100.00**
- **Profit: $7.36 (7.9% return)**

### What Makes Arbitrage Profitable?

For an arbitrage to be profitable after Kalshi's fees, the spread needs to account for:

1. **Base cost** (P_kalshi + P_poly)
2. **Kalshi dynamic fee** based on P × (1-P)
3. **Polymarket ~2% fee**

Generally, you need:
```
P_kalshi + P_poly + kalshi_fee + poly_fee < $1.00
```

The sweet spot is when:
- Prices are **NOT at 0.50** (lower Kalshi fees)
- Combined price is **well below $1.00**

### Example: Better Arbitrage

**Kalshi YES @ $0.30, Polymarket NO @ $0.60**

For 100 contracts:

**Kalshi:**
- Cost: 100 × $0.30 = $30.00
- Fee: ceil(0.07 × 100 × 0.30 × 0.70) = ceil(1.47) = **$1.47**
- Total: **$31.47**

**Polymarket:**
- Cost: 100 × $0.60 = $60.00
- Fee: $60.00 × 0.02 = **$1.20**
- Total: **$61.20**

**Combined:**
- Total Cost: $31.47 + $61.20 = **$92.67**
- Payout: **$100.00**
- **Profit: $7.33 (7.9% return)**

Notice the combined price is $0.90, but total cost with fees is $0.9267.

## Optimization Tips

### 1. Target Mid-Range Prices
- Prices near 0.30-0.40 or 0.60-0.70 have lower variance
- Avoid 0.50 where fees are highest
- But spreads are typically tighter away from 0.50

### 2. Larger Position Sizes
- Minimum $0.01 fee per contract means small positions are inefficient
- For 1 contract @ $0.50: fee is $0.02 (4% of cost)
- For 100 contracts @ $0.50: fee is $1.75 (1.75% of cost)

### 3. Special Markets
- S&P 500 and NASDAQ-100 have **50% lower fees**
- Target these for larger arbitrages
- Look for tickers starting with `INX` or `NASDAQ100`

### 4. Maker vs Taker
- If you can wait, maker orders save 75% on fees
- But arbitrage typically requires immediate execution (taker)
- Consider maker orders if you can leg in over time

## Fee Calculation in Code

The bot now uses the accurate formula:

```python
def calculate_kalshi_fee(price, contracts, market_ticker, is_maker=False):
    # Determine rate
    if market_ticker.startswith(('INX', 'NASDAQ100')):
        rate = 0.035  # Special markets
    elif is_maker:
        rate = 0.0175  # Maker orders
    else:
        rate = 0.07  # Taker orders (most common for arbitrage)

    # Calculate variance term
    variance = price * (1 - price)

    # Calculate fee
    fee = rate * contracts * variance

    # Round up to next cent
    return math.ceil(fee * 100) / 100
```

## Summary

Kalshi's fee structure:
- ✅ **Dynamic**: Based on contract uncertainty
- ✅ **Lower** at price extremes (high certainty)
- ✅ **Higher** near 0.50 (high uncertainty)
- ✅ **Cheaper** for S&P/NASDAQ markets
- ✅ **Much cheaper** for maker orders

For arbitrage:
- Factor in exact fees using the P×(1-P) formula
- Consider position size (larger is more efficient)
- Target special markets when possible
- Account for both Kalshi's dynamic fee + Polymarket's ~2%
