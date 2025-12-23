"""Configuration management."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Kalshi API
    kalshi_email: str = ""
    kalshi_password: str = ""
    kalshi_api_key: str = ""
    kalshi_private_key_path: Optional[Path] = None
    kalshi_mode: str = "demo"  # demo or prod

    # Polymarket API
    polymarket_private_key: str = ""
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_chain_id: int = 137

    # Trading Parameters
    enable_trading: bool = False
    min_profit_threshold: Decimal = Decimal("0.02")
    max_position_size: Decimal = Decimal("100.00")
    max_total_exposure: Decimal = Decimal("1000.00")
    check_interval: float = 5.0

    # Risk Management
    max_daily_loss: Decimal = Decimal("100.00")
    max_drawdown: Decimal = Decimal("0.20")
    stop_loss_enabled: bool = True

    # Fees
    kalshi_fee_rate: Decimal = Decimal("0.00")
    polymarket_fee_rate: Decimal = Decimal("0.02")

    # Logging
    log_level: str = "INFO"
    log_file: Path = Path("logs/arbitrage_bot.log")

    # Database
    database_url: str = "sqlite:///data/trades.db"

    # Monitoring
    enable_alerts: bool = False
    alert_webhook_url: Optional[str] = None
    slack_webhook_url: Optional[str] = None

    # Rate Limiting
    max_requests_per_minute: int = 60

    @property
    def kalshi_base_url(self) -> str:
        """Get Kalshi API base URL based on mode."""
        if self.kalshi_mode == "prod":
            return "https://trading-api.kalshi.com/trade-api/v2"
        return "https://demo-api.kalshi.co/trade-api/v2"

    @property
    def polymarket_clob_url(self) -> str:
        """Get Polymarket CLOB URL."""
        return "https://clob.polymarket.com"

    @property
    def total_fee_rate(self) -> Decimal:
        """Calculate total fee rate for both platforms."""
        return self.kalshi_fee_rate + self.polymarket_fee_rate

    def validate_credentials(self) -> dict[str, bool]:
        """Validate that required credentials are set."""
        return {
            "kalshi": bool(self.kalshi_email and self.kalshi_password),
            "polymarket": bool(self.polymarket_private_key),
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
