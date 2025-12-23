"""Kalshi API client."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import aiohttp
from loguru import logger

from ..models import Market, OrderBook, Platform, Side, Order, OrderStatus, OrderType
from ..utils import get_settings


class KalshiClient:
    """Async client for Kalshi API."""

    def __init__(self):
        """Initialize Kalshi client."""
        self.settings = get_settings()
        self.base_url = self.settings.kalshi_base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP session and authenticate."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        await self._authenticate()
        logger.info("Kalshi client connected")

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Kalshi client closed")

    async def _authenticate(self) -> None:
        """Authenticate and get access token."""
        if not self.settings.kalshi_email or not self.settings.kalshi_password:
            raise ValueError("Kalshi credentials not configured")

        url = f"{self.base_url}/login"
        payload = {
            "email": self.settings.kalshi_email,
            "password": self.settings.kalshi_password,
        }

        async with self.session.post(url, json=payload) as response:
            if response.status != 200:
                error = await response.text()
                raise Exception(f"Kalshi authentication failed: {error}")

            data = await response.json()
            self.token = data["token"]
            # Tokens expire in 30 minutes, refresh at 25 minutes
            self.token_expiry = datetime.utcnow() + timedelta(minutes=25)
            logger.info("Kalshi authentication successful")

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid token."""
        async with self._lock:
            if self.token is None or (
                self.token_expiry and datetime.utcnow() >= self.token_expiry
            ):
                logger.info("Refreshing Kalshi authentication")
                await self._authenticate()

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated API request."""
        await self._ensure_authenticated()

        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"

        async with self.session.request(method, url, headers=headers, **kwargs) as response:
            if response.status == 401:
                # Token expired, re-authenticate and retry
                await self._authenticate()
                headers["Authorization"] = f"Bearer {self.token}"
                async with self.session.request(
                    method, url, headers=headers, **kwargs
                ) as retry_response:
                    retry_response.raise_for_status()
                    return await retry_response.json()

            response.raise_for_status()
            return await response.json()

    async def get_markets(self, event_ticker: Optional[str] = None) -> list[Market]:
        """
        Get markets from Kalshi.

        Args:
            event_ticker: Optional event ticker to filter markets

        Returns:
            List of Market objects
        """
        params = {}
        if event_ticker:
            params["event_ticker"] = event_ticker

        data = await self._request("GET", "/markets", params=params)

        markets = []
        for market_data in data.get("markets", []):
            try:
                market = self._parse_market(market_data)
                markets.append(market)
            except Exception as e:
                logger.warning(f"Failed to parse Kalshi market: {e}")
                continue

        logger.info(f"Retrieved {len(markets)} markets from Kalshi")
        return markets

    async def get_market(self, market_ticker: str) -> Market:
        """
        Get specific market by ticker.

        Args:
            market_ticker: Market ticker (e.g., "INXD-23DEC31-T4500")

        Returns:
            Market object
        """
        data = await self._request("GET", f"/markets/{market_ticker}")
        return self._parse_market(data["market"])

    async def get_orderbook(self, market_ticker: str) -> OrderBook:
        """
        Get orderbook for a market.

        Args:
            market_ticker: Market ticker

        Returns:
            OrderBook object
        """
        data = await self._request("GET", f"/markets/{market_ticker}/orderbook")

        # Kalshi orderbook structure: {"yes": [...], "no": [...]}
        yes_orders = data.get("yes", [])
        no_orders = data.get("no", [])

        # Get best prices (assuming sorted by price)
        best_yes_price = Decimal(str(yes_orders[0][0])) if yes_orders else Decimal("0")
        best_no_price = Decimal(str(no_orders[0][0])) if no_orders else Decimal("0")
        yes_liquidity = Decimal(str(yes_orders[0][1])) if yes_orders else Decimal("0")
        no_liquidity = Decimal(str(no_orders[0][1])) if no_orders else Decimal("0")

        return OrderBook(
            best_yes_price=best_yes_price / 100,  # Convert cents to dollars
            best_no_price=best_no_price / 100,
            yes_liquidity=yes_liquidity,
            no_liquidity=no_liquidity,
        )

    async def place_order(
        self,
        market_ticker: str,
        side: Side,
        quantity: int,
        price: Decimal,
        order_type: OrderType = OrderType.LIMIT,
    ) -> Order:
        """
        Place an order on Kalshi.

        Args:
            market_ticker: Market ticker
            side: YES or NO
            quantity: Number of contracts
            price: Limit price (0-1)
            order_type: Order type (default: LIMIT)

        Returns:
            Order object
        """
        if not self.settings.enable_trading:
            logger.warning("Trading disabled - order not placed")
            raise Exception("Trading is disabled in settings")

        # Convert price to cents
        price_cents = int(price * 100)

        payload = {
            "ticker": market_ticker,
            "action": "buy",  # Always buying (YES or NO)
            "side": side.value.lower(),
            "count": quantity,
            "type": order_type.value.lower(),
            "yes_price": price_cents if side == Side.YES else None,
            "no_price": price_cents if side == Side.NO else None,
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        data = await self._request("POST", "/portfolio/orders", json=payload)

        order = Order(
            platform=Platform.KALSHI,
            market_id=market_ticker,
            side=side,
            order_type=order_type,
            price=price,
            quantity=Decimal(str(quantity)),
            status=OrderStatus.SUBMITTED,
            platform_order_id=data["order"]["order_id"],
        )

        logger.info(f"Placed Kalshi order: {order.order_id} - {side} {quantity} @ {price}")
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Kalshi order ID

        Returns:
            True if successful
        """
        try:
            await self._request("DELETE", f"/portfolio/orders/{order_id}")
            logger.info(f"Cancelled Kalshi order: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_balance(self) -> Decimal:
        """
        Get account balance.

        Returns:
            Available balance in USD
        """
        data = await self._request("GET", "/portfolio/balance")
        balance = Decimal(str(data["balance"])) / 100  # Convert cents to dollars
        logger.debug(f"Kalshi balance: ${balance}")
        return balance

    async def get_positions(self) -> list[dict]:
        """
        Get current positions.

        Returns:
            List of position dictionaries
        """
        data = await self._request("GET", "/portfolio/positions")
        return data.get("positions", [])

    def _parse_market(self, market_data: dict) -> Market:
        """
        Parse Kalshi market data into Market object.

        Args:
            market_data: Raw market data from API

        Returns:
            Market object
        """
        # Extract orderbook if available, otherwise use placeholder
        orderbook_data = market_data.get("orderbook", {})

        # Kalshi uses last_price for current price
        last_yes = Decimal(str(market_data.get("last_price", 50))) / 100
        last_no = Decimal("1.0") - last_yes

        orderbook = OrderBook(
            best_yes_price=last_yes,
            best_no_price=last_no,
            yes_liquidity=Decimal(str(market_data.get("volume", 0))),
            no_liquidity=Decimal(str(market_data.get("volume", 0))),
        )

        return Market(
            platform=Platform.KALSHI,
            market_id=market_data["ticker"],
            event_id=market_data.get("event_ticker", ""),
            question=market_data["title"],
            close_time=datetime.fromisoformat(
                market_data["close_time"].replace("Z", "+00:00")
            ),
            orderbook=orderbook,
            status=market_data["status"],
            min_tick_size=Decimal("0.01"),
        )
