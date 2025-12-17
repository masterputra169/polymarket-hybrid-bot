"""
Configuration Module - Updated for Asymmetric Strategy
Centralized configuration for the bot
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load .env file BEFORE reading any environment variables
load_dotenv()

class Config:
    """Bot configuration"""
    
    def __init__(self):
        # ==========================================
        # WALLET & AUTHENTICATION
        # ==========================================
        self.PRIVATE_KEY: str = os.getenv("PRIVATE_KEY", "")
        self.PROXY_ADDRESS: str = os.getenv("PROXY_ADDRESS", "")
        self.CHAIN_ID: int = int(os.getenv("CHAIN_ID", "137"))
        self.SIGNATURE_TYPE: int = int(os.getenv("SIGNATURE_TYPE", "2"))
        
        # ==========================================
        # POLYMARKET API
        # ==========================================
        self.CLOB_HOST: str = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
        self.GAMMA_API: str = "https://gamma-api.polymarket.com"
        self.DATA_API: str = "https://data-api.polymarket.com"
        
        # ==========================================
        # TRADING STRATEGY SELECTION
        # ==========================================
        # Choose strategy: "ASYMMETRIC" (gabagool's real strategy) or "PAIR" (old symmetric)
        self.STRATEGY_TYPE: str = os.getenv("STRATEGY_TYPE", "ASYMMETRIC")
        
        # ==========================================
        # ASYMMETRIC STRATEGY (gabagool22's TRUE approach)
        # ==========================================
        # Buy when price drops below recent average
        # Example: 0.05 = buy when 5% below recent average
        # Conservative: 0.08 (8% drop needed)
        # Balanced: 0.05 (5% drop)
        # Aggressive: 0.03 (3% drop)
        self.CHEAP_THRESHOLD: float = float(os.getenv("CHEAP_THRESHOLD", "0.05"))
        
        # Minimum samples needed before using average-based strategy
        self.MIN_PRICE_HISTORY: int = int(os.getenv("MIN_PRICE_HISTORY", "10"))
        
        # Maximum price history to keep (rolling window)
        self.MAX_PRICE_HISTORY: int = int(os.getenv("MAX_PRICE_HISTORY", "100"))
        
        # ==========================================
        # PAIR TRADING STRATEGY (old symmetric approach)
        # ==========================================
        # Target pair cost (YES avg + NO avg must be < this)
        self.TARGET_PAIR_COST: float = float(os.getenv("TARGET_PAIR_COST", "0.98"))
        
        # ==========================================
        # COMMON TRADING PARAMETERS
        # ==========================================
        # Order size per trade
        self.ORDER_SIZE_USD: float = float(os.getenv("ORDER_SIZE_USD", "0.75"))
        self.MIN_ORDER_SIZE: float = float(os.getenv("MIN_ORDER_SIZE", "0.50"))
        self.MAX_ORDER_SIZE: float = float(os.getenv("MAX_ORDER_SIZE", "1.00"))
        
        # Maximum spent per side (CONSERVATIVE: $5 per side, $10 total)
        self.MAX_PER_SIDE: float = float(os.getenv("MAX_PER_SIDE", "5.0"))
        
        # Maximum imbalance between YES and NO
        # Asymmetric strategy can tolerate higher imbalance (0.50 = 50%)
        # Pair trading needs lower imbalance (0.20 = 20%)
        if self.STRATEGY_TYPE == "ASYMMETRIC":
            default_imbalance = "0.50"  # 50% for asymmetric
        else:
            default_imbalance = "0.20"  # 20% for pair trading
        
        self.MAX_IMBALANCE: float = float(os.getenv("MAX_IMBALANCE", default_imbalance))
        
        # How often to check prices (seconds)
        self.POLLING_INTERVAL: int = int(os.getenv("POLLING_INTERVAL", "5"))
        
        # Stop loss per day
        self.MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", "50.0"))
        
        # ==========================================
        # MARKET SELECTION
        # ==========================================
        self.ASSET: str = os.getenv("ASSET", "BTC")
        self.MARKET_DURATION: int = int(os.getenv("MARKET_DURATION", "15"))
        
        # ==========================================
        # MONITORING & VISUALIZATION
        # ==========================================
        self.CHART_UPDATE_INTERVAL: int = int(os.getenv("CHART_UPDATE_INTERVAL", "60"))
        self.AUTO_GENERATE_CHART: bool = os.getenv("AUTO_GENERATE_CHART", "true").lower() == "true"
        
        # ==========================================
        # DATABASE & LOGGING
        # ==========================================
        self.TRADE_LOG_FILE: str = os.getenv("TRADE_LOG_FILE", "trades_session.json")
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        
        # ==========================================
        # LAST-SECOND SNIPING STRATEGY
        # ==========================================
        # When to trigger snipe (seconds before settlement)
        self.SNIPE_TRIGGER_SECONDS: int = int(os.getenv("SNIPE_TRIGGER_SECONDS", "60"))
        
        # Price limits for sniping
        self.SNIPE_MIN_PRICE: float = float(os.getenv("SNIPE_MIN_PRICE", "0.90"))
        self.SNIPE_MAX_PRICE: float = float(os.getenv("SNIPE_MAX_PRICE", "0.99"))
        
        # How much to snipe (CONSERVATIVE: $5)
        self.SNIPE_SIZE_USD: float = float(os.getenv("SNIPE_SIZE_USD", "5.0"))
        
        # Dry run mode (test without real orders)
        self.DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
        
        # ==========================================
        # SAFETY LIMITS
        # ==========================================
        # Price limits (in cents, 0-100)
        self.MAX_PRICE_YES: float = float(os.getenv("MAX_PRICE_YES", "60.0"))
        self.MAX_PRICE_NO: float = float(os.getenv("MAX_PRICE_NO", "60.0"))
        
        # Minimum profit margin
        self.MIN_PROFIT_MARGIN: float = float(os.getenv("MIN_PROFIT_MARGIN", "0.02"))  # 2%
        
        # Timeout for API calls
        self.API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "15"))
        
        # Validate configuration
        self._validate()
    
    def _validate(self):
        """Validate configuration"""
        errors = []
        
        # Check required fields
        if not self.PRIVATE_KEY:
            errors.append("PRIVATE_KEY is required")
        
        if not self.PROXY_ADDRESS:
            errors.append("PROXY_ADDRESS is required")
        
        # Check strategy type
        if self.STRATEGY_TYPE not in ["ASYMMETRIC", "PAIR"]:
            errors.append("STRATEGY_TYPE must be 'ASYMMETRIC' or 'PAIR'")
        
        # Check numeric ranges
        if self.TARGET_PAIR_COST <= 0 or self.TARGET_PAIR_COST >= 2:
            errors.append("TARGET_PAIR_COST must be between 0 and 2")
        
        if self.CHEAP_THRESHOLD <= 0 or self.CHEAP_THRESHOLD >= 1:
            errors.append("CHEAP_THRESHOLD must be between 0 and 1")
        
        if self.ORDER_SIZE_USD < self.MIN_ORDER_SIZE:
            errors.append(f"ORDER_SIZE_USD must be >= MIN_ORDER_SIZE ({self.MIN_ORDER_SIZE})")
        
        if self.ORDER_SIZE_USD > self.MAX_ORDER_SIZE:
            errors.append(f"ORDER_SIZE_USD must be <= MAX_ORDER_SIZE ({self.MAX_ORDER_SIZE})")
        
        if self.MAX_PER_SIDE <= 0:
            errors.append("MAX_PER_SIDE must be > 0")
        
        if self.MAX_IMBALANCE < 0 or self.MAX_IMBALANCE > 1:
            errors.append("MAX_IMBALANCE must be between 0 and 1")
        
        if errors:
            raise ValueError(f"Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    def get_summary(self) -> dict:
        """Get configuration summary"""
        return {
            'strategy': {
                'type': self.STRATEGY_TYPE,
                'asset': self.ASSET,
                'duration': f"{self.MARKET_DURATION}min",
                'cheap_threshold': f"{self.CHEAP_THRESHOLD * 100}%" if self.STRATEGY_TYPE == "ASYMMETRIC" else "N/A",
                'target_pair_cost': f"${self.TARGET_PAIR_COST}" if self.STRATEGY_TYPE == "PAIR" else "N/A",
                'order_size': f"${self.ORDER_SIZE_USD}",
                'max_per_side': f"${self.MAX_PER_SIDE}",
                'max_exposure': f"${self.MAX_PER_SIDE * 2}"
            },
            'limits': {
                'max_imbalance': f"{self.MAX_IMBALANCE * 100}%",
                'max_daily_loss': f"${self.MAX_DAILY_LOSS}",
                'max_yes_price': f"{self.MAX_PRICE_YES}¢",
                'max_no_price': f"{self.MAX_PRICE_NO}¢"
            },
            'sniper': {
                'trigger_seconds': self.SNIPE_TRIGGER_SECONDS,
                'min_price': f"${self.SNIPE_MIN_PRICE}",
                'max_price': f"${self.SNIPE_MAX_PRICE}",
                'size': f"${self.SNIPE_SIZE_USD}"
            },
            'settings': {
                'polling_interval': f"{self.POLLING_INTERVAL}s",
                'chart_updates': f"{self.CHART_UPDATE_INTERVAL}s",
                'auto_chart': self.AUTO_GENERATE_CHART,
                'dry_run': self.DRY_RUN
            }
        }


# Example .env template
ENV_TEMPLATE = """
# ═══════════════════════════════════════════════════════════════
# POLYMARKET HYBRID TRADING BOT - CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# ===========================
# WALLET CONFIGURATION
# ===========================
PRIVATE_KEY=your_private_key_without_0x
PROXY_ADDRESS=0xYourProxyWalletAddress
CHAIN_ID=137
SIGNATURE_TYPE=2

# ===========================
# STRATEGY SELECTION
# ===========================
# ASYMMETRIC = Gabagool's real strategy (buy YES/NO at different times when cheap)
# PAIR = Old symmetric strategy (buy YES+NO together when pair cost < target)
STRATEGY_TYPE=ASYMMETRIC

# ===========================
# ASYMMETRIC STRATEGY SETTINGS
# ===========================
# Buy when price drops X% below recent average
# Conservative: 0.08 (8% drop needed - fewer trades, better prices)
# Balanced: 0.05 (5% drop - recommended)
# Aggressive: 0.03 (3% drop - more trades, decent prices)
CHEAP_THRESHOLD=0.05

# Price history window
MIN_PRICE_HISTORY=10
MAX_PRICE_HISTORY=100

# ===========================
# PAIR TRADING STRATEGY SETTINGS
# ===========================
# Only used if STRATEGY_TYPE=PAIR
TARGET_PAIR_COST=0.98

# ===========================
# COMMON TRADING PARAMETERS
# ===========================
ORDER_SIZE_USD=0.75
MIN_ORDER_SIZE=0.50
MAX_ORDER_SIZE=1.00
MAX_PER_SIDE=5.0

# Max imbalance (ASYMMETRIC can tolerate more)
# ASYMMETRIC: 0.50 (50%) recommended
# PAIR: 0.20 (20%) recommended
MAX_IMBALANCE=0.50

POLLING_INTERVAL=5
MAX_DAILY_LOSS=50.0

# ===========================
# LAST-SECOND SNIPING
# ===========================
SNIPE_TRIGGER_SECONDS=60
SNIPE_MIN_PRICE=0.90
SNIPE_MAX_PRICE=0.99
SNIPE_SIZE_USD=5.0

# ===========================
# MARKET SELECTION
# ===========================
ASSET=BTC
MARKET_DURATION=15

# ===========================
# EXECUTION MODE
# ===========================
DRY_RUN=true
SKIP_ALLOWANCE_CHECK=true

# ===========================
# MONITORING
# ===========================
CHART_UPDATE_INTERVAL=60
AUTO_GENERATE_CHART=true
LOG_LEVEL=INFO

# ===========================
# SAFETY LIMITS
# ===========================
MAX_PRICE_YES=60.0
MAX_PRICE_NO=60.0
MIN_PROFIT_MARGIN=0.02
"""


def create_env_template(filename: str = ".env.example"):
    """Create .env template file"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(ENV_TEMPLATE)
    print(f"✅ Created {filename}")


if __name__ == "__main__":
    # Test configuration
    try:
        config = Config()
        print("✅ Configuration valid")
        print("\n📊 Summary:")
        import json
        print(json.dumps(config.get_summary(), indent=2))
    except ValueError as e:
        print(f"❌ Configuration error:\n{e}")
        print("\n💡 Creating .env.example template...")
        try:
            create_env_template()
            print("\n📝 Next steps:")
            print("   1. Copy .env.example to .env")
            print("   2. Edit .env and fill in your credentials:")
            print("      - PRIVATE_KEY (without 0x prefix)")
            print("      - PROXY_ADDRESS (with 0x prefix)")
            print("   3. Run: python config.py")
        except Exception as create_error:
            print(f"❌ Could not create template: {create_error}")
            print("\n💡 Please manually create .env file with required variables")