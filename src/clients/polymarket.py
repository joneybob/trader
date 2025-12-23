"""Polymarket API client."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType as PolyClobOrderType
from py_clob_client.order_builder.constants import BUY, SELL

from ..models import Market, OrderBook, Platform, Side, Order, OrderStatus, OrderType
from ..utils import get_settings


class PolymarketClient:
    """Client for Polymarket CLOB API."""

    def __init__(self):
        """Initialize Polymarket client."""
        self.settings = get_settings()
        self.client: Optional[ClobClient] = None
        self._connected = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize CLOB client."""
        if not self.settings.polymarket_private_key:
            raise ValueError("Polymarket private key not configured")

        try:
            # Initialize CLOB client
            self.client = ClobClient(
                host=self.settings.polymarket_clob_url,
                key=self.settings.polymarket_private_key,
                chain_id=self.settings.polymarket_chain_id,
            )

            # Derive and set API credentials
            await self._setup_credentials()

            self._connected = True
            logger.info("Polymarket client connected")
        except Exception as e:
            logger.error(f"Failed to connect to Polymarket: {e}")
            raise

    async def close(self) -> None:
        """Close client connection."""
        self._connected = False
        logger.info("Polymarket client closed")

    async def _setup_credentials(self) -> None:
        """Set up API credentials from private key."""
        try:
            # The py_clob_client handles API key derivation internally
            # We just need to ensure the client is properly configured
            self.client.set_api_creds(self.client.create_api_creds())
            logger.info("Polymarket API credentials configured")
        except Exception as e:
            logger.warning(f"API credentials setup: {e}")

    def _ensure_connected(self) -> None:
        """Ensure client is connected."""
        if not self._connected or self.client is None:
            raise Exception("Polymarket client not connected")

    async def get_markets(self, condition_id: Optional[str] = None) -> list[Market]:
        """
        Get markets from Polymarket.

        Args:
            condition_id: Optional condition ID to filter markets

        Returns:
            List of Market objects
        """
        self._ensure_connected()

        try:
            # Get all markets or filter by condition
            if condition_id:
                markets_data = self.client.get_markets(condition_id=condition_id)
            else:
                # Get sampling of active markets
                markets_data = self.client.get_markets()

            markets = []
            for market_data in markets_data:
                try:
                    market = await self._parse_market(market_data)
                    markets.append(market)
                except Exception as e:
                    logger.warning(f"Failed to parse Polymarket market: {e}")
                    continue

            logger.info(f"Retrieved {len(markets)} markets from Polymarket")
            return markets
        except Exception as e:
            logger.error(f"Failed to get Polymarket markets: {e}")
            return []

    async def get_market(self, token_id: str) -> Market:
        """
        Get specific market by token ID.

        Args:
            token_id: Market token ID

        Returns:
            Market object
        """
        self._ensure_connected()

        market_data = self.client.get_market(token_id)
        return await self._parse_market(market_data)

    async def get_orderbook(self, token_id: str) -> OrderBook:
        """
        Get orderbook for a market.

        Args:
            token_id: Market token ID

        Returns:
            OrderBook object
        """
        self._ensure_connected()

        try:
            orderbook_data = self.client.get_order_book(token_id)

            # Parse bids (YES) and asks (NO)
            bids = orderbook_data.get("bids", [])
            asks = orderbook_data.get("asks", [])

            # Best prices
            best_yes_price = Decimal(str(bids[0]["price"])) if bids else Decimal("0")
            best_no_price = Decimal(str(asks[0]["price"])) if asks else Decimal("0")
            yes_liquidity = Decimal(str(bids[0]["size"])) if bids else Decimal("0")
            no_liquidity = Decimal(str(asks[0]["size"])) if asks else Decimal("0")

            return OrderBook(
                best_yes_price=best_yes_price,
                best_no_price=best_no_price,
                yes_liquidity=yes_liquidity,
                no_liquidity=no_liquidity,
            )
        except Exception as e:
            logger.error(f"Failed to get orderbook for {token_id}: {e}")
            # Return empty orderbook
            return OrderBook(
                best_yes_price=Decimal("0"),
                best_no_price=Decimal("0"),
                yes_liquidity=Decimal("0"),
                no_liquidity=Decimal("0"),
            )

    async def place_order(
        self,
        token_id: str,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        order_type: OrderType = OrderType.GTC,
    ) -> Order:
        """
        Place an order on Polymarket.

        Args:
            token_id: Market token ID
            side: YES (BUY) or NO (SELL)
            quantity: Size in outcome tokens
            price: Limit price (0-1)
            order_type: Order type (GTC, FOK, etc.)

        Returns:
            Order object
        """
        self._ensure_connected()

        if not self.settings.enable_trading:
            logger.warning("Trading disabled - order not placed")
            raise Exception("Trading is disabled in settings")

        try:
            # Map our Side to Polymarket's BUY/SELL
            poly_side = BUY if side == Side.YES else SELL

            # Map order type
            poly_order_type = self._map_order_type(order_type)

            # Create order arguments
            order_args = OrderArgs(
                token_id=token_id,
                price=float(price),
                size=float(quantity),
                side=poly_side,
                fee_rate_bps=0,  # Will be calculated by CLOB
                nonce=0,  # Will be set by client
                expiration=0,  # No expiration
            )

            # Sign and post order
            signed_order = self.client.create_order(order_args)
            response = self.client.post_order(signed_order, order_type=poly_order_type)

            order = Order(
                platform=Platform.POLYMARKET,
                market_id=token_id,
                side=side,
                order_type=order_type,
                price=price,
                quantity=quantity,
                status=OrderStatus.SUBMITTED,
                platform_order_id=response.get("orderID"),
            )

            logger.info(
                f"Placed Polymarket order: {order.order_id} - {side} {quantity} @ {price}"
            )
            return order

        except Exception as e:
            logger.error(f"Failed to place Polymarket order: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Polymarket order ID

        Returns:
            True if successful
        """
        self._ensure_connected()

        try:
            self.client.cancel(order_id)
            logger.info(f"Cancelled Polymarket order: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders.

        Returns:
            True if successful
        """
        self._ensure_connected()

        try:
            self.client.cancel_all()
            logger.info("Cancelled all Polymarket orders")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    async def get_balance(self) -> Decimal:
        """
        Get USDC balance.

        Returns:
            Available balance in USDC
        """
        self._ensure_connected()

        try:
            # Get balance from allowance
            allowance = self.client.get_allowance()
            balance = Decimal(str(allowance))
            logger.debug(f"Polymarket balance: {balance} USDC")
            return balance
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return Decimal("0")

    async def get_positions(self) -> list[dict]:
        """
        Get current positions.

        Returns:
            List of position dictionaries
        """
        self._ensure_connected()

        try:
            # Get open positions from orders
            orders = self.client.get_orders()
            return orders
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    async def _parse_market(self, market_data: dict) -> Market:
        """
        Parse Polymarket market data into Market object.

        Args:
            market_data: Raw market data from API

        Returns:
            Market object
        """
        # Get orderbook for current prices
        token_id = market_data.get("token_id") or market_data.get("id")
        orderbook = await self.get_orderbook(token_id)

        # Parse close time
        end_date_iso = market_data.get("end_date_iso") or market_data.get("endDate")
        if end_date_iso:
            close_time = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        else:
            # Default to far future if no close time
            close_time = datetime(2099, 12, 31)

        return Market(
            platform=Platform.POLYMARKET,
            market_id=token_id,
            event_id=market_data.get("condition_id", ""),
            question=market_data.get("question", market_data.get("title", "")),
            close_time=close_time,
            orderbook=orderbook,
            status="active" if market_data.get("active", True) else "closed",
            min_tick_size=Decimal("0.001"),  # Polymarket has finer tick size
        )

    def _map_order_type(self, order_type: OrderType) -> PolyClobOrderType:
        """Map our OrderType to Polymarket's OrderType."""
        mapping = {
            OrderType.GTC: PolyClobOrderType.GTC,
            OrderType.FOK: PolyClobOrderType.FOK,
            OrderType.GTD: PolyClobOrderType.GTD,
        }
        return mapping.get(order_type, PolyClobOrderType.GTC)
