"""Fee calculation examples and verification."""

import math
from decimal import Decimal


def calculate_kalshi_fee(price: float, contracts: int, fee_rate: float = 0.07) -> float:
    """
    Calculate Kalshi fee using their formula.

    Formula: ceil(fee_rate × C × P × (1-P))

    Args:
        price: Price per contract (0-1, e.g., 0.50 for 50 cents)
        contracts: Number of contracts
        fee_rate: Fee rate (0.07 for general, 0.035 for S&P/NASDAQ, 0.0175 for maker)

    Returns:
        Fee in dollars
    """
    # Calculate P × (1-P) - the variance term
    variance = price * (1 - price)

    # Calculate fee before rounding
    fee_dollars = fee_rate * contracts * variance

    # Round up to next cent
    fee_cents = math.ceil(fee_dollars * 100)
    fee_rounded = fee_cents / 100

    return fee_rounded


# Examples from Kalshi's fee table
print("Kalshi General Trading Fees (100 contracts):")
print("=" * 60)

test_cases = [
    (0.01, 100, 0.07),
    (0.05, 100, 0.07),
    (0.10, 100, 0.07),
    (0.25, 100, 0.07),
    (0.50, 100, 0.07),  # Maximum fee (highest variance)
    (0.75, 100, 0.07),
    (0.99, 100, 0.07),
]

for price, contracts, rate in test_cases:
    fee = calculate_kalshi_fee(price, contracts, rate)
    variance = price * (1 - price)
    print(f"Price: ${price:.2f} | Variance: {variance:.4f} | Fee: ${fee:.2f}")

print("\nKalshi S&P500/NASDAQ Fees (100 contracts, 3.5% rate):")
print("=" * 60)

sp_test_cases = [
    (0.01, 100, 0.035),
    (0.25, 100, 0.035),
    (0.50, 100, 0.035),  # Maximum fee
    (0.75, 100, 0.035),
    (0.99, 100, 0.035),
]

for price, contracts, rate in sp_test_cases:
    fee = calculate_kalshi_fee(price, contracts, rate)
    variance = price * (1 - price)
    print(f"Price: ${price:.2f} | Variance: {variance:.4f} | Fee: ${fee:.2f}")

print("\nArbitrage Example:")
print("=" * 60)
print("Scenario: Kalshi YES @ $0.45, Polymarket NO @ $0.45")
print()

kalshi_price = 0.45
poly_price = 0.45
contracts = 100

# Calculate Kalshi fee
kalshi_fee = calculate_kalshi_fee(kalshi_price, contracts, 0.07)

# Calculate Polymarket fee (simple percentage)
poly_cost = poly_price * contracts
poly_fee = poly_cost * 0.02

# Total costs
kalshi_cost = kalshi_price * contracts + kalshi_fee
poly_cost_total = poly_price * contracts + poly_fee
total_cost = kalshi_cost + poly_cost_total

# Profit
payout = 1.00 * contracts  # $100
profit = payout - total_cost
profit_percentage = (profit / total_cost) * 100

print(f"Kalshi: {contracts} contracts @ ${kalshi_price:.2f} = ${kalshi_price * contracts:.2f}")
print(f"  + Fee: ${kalshi_fee:.2f}")
print(f"  = Total: ${kalshi_cost:.2f}")
print()
print(f"Polymarket: {contracts} contracts @ ${poly_price:.2f} = ${poly_price * contracts:.2f}")
print(f"  + Fee (2%): ${poly_fee:.2f}")
print(f"  = Total: ${poly_cost_total:.2f}")
print()
print(f"Total Cost: ${total_cost:.2f}")
print(f"Payout: ${payout:.2f}")
print(f"Profit: ${profit:.2f} ({profit_percentage:.2f}%)")
print()

# Break-even analysis
print("Break-even Analysis:")
print("=" * 60)
print("For 100 contracts, what's the max combined price for profit?")
print()

for target_profit in [0, 1, 2, 5]:
    # Binary search for max price
    low, high = 0.0, 1.0

    for _ in range(50):  # 50 iterations for precision
        mid = (low + high) / 2

        # Assume equal split
        kalshi_p = mid / 2
        poly_p = mid / 2

        kalshi_fee = calculate_kalshi_fee(kalshi_p, contracts, 0.07)
        poly_fee = (poly_p * contracts) * 0.02

        total = (kalshi_p + poly_p) * contracts + kalshi_fee + poly_fee
        profit = 100 - total

        if profit > target_profit:
            low = mid
        else:
            high = mid

    max_price = (low + high) / 2
    print(f"Target profit ${target_profit}: Max combined price ${max_price:.4f}")
