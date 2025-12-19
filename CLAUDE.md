# CLAUDE.md - AI Assistant Guide

This document provides comprehensive guidance for AI assistants working with the Polymarket Hybrid Trading Bot codebase.

## Project Overview

**Polymarket Hybrid Trading Bot** is an automated cryptocurrency trading system that implements two complementary strategies on the Polymarket prediction market platform:

1. **Pair Trading Strategy** (0-14 minutes remaining) - Based on gabagool22's approach
   - Buys both YES and NO outcomes when pair cost < $0.98
   - Guarantees profit when pair settles at $1.00
   - Uses multiple small orders for better price averaging

2. **Last-Second Sniping Strategy** (Final 60 seconds)
   - Identifies winning side from market prices
   - Executes snipe orders at $0.97-0.99 for $1.00 settlement
   - Captures arbitrage opportunities from panic selling

### Key Technologies
- **Language**: Python 3.10+
- **API Client**: py-clob-client (Polymarket official client)
- **Async Framework**: asyncio, aiohttp, websockets
- **Blockchain**: Web3.py (for USDC allowances)
- **Configuration**: python-dotenv
- **Visualization**: matplotlib
- **Logging**: Custom colored logger with file output

---

## Repository Structure

```
polymarket-hybrid-bot/
├── main_hybrid.py              # Main entry point - orchestrates both strategies
├── config.py                   # Centralized configuration with validation
├── requirements_hybrid.txt     # Python dependencies
├── .env                        # Environment variables (NEVER COMMIT)
├── .gitignore                  # Git ignore rules (CRITICAL: protects secrets)
│
├── core/                       # Core trading modules
│   ├── __init__.py
│   ├── client.py              # Polymarket API wrapper (ClobClient)
│   ├── market_scanner.py     # Finds active 15-minute BTC markets
│   ├── pair_trader.py        # Implements pair trading strategy
│   ├── last_second_sniper.py # Implements sniping strategy with WebSocket
│   └── monitor.py            # Trade monitoring and reporting
│
├── utils/                     # Utility modules
│   ├── __init__.py
│   ├── logger.py             # Custom colored logging setup
│   └── chart_generator.py   # Trade visualization
│
├── scripts/                   # Standalone scripts
│   ├── __init__.py
│   └── approve.py            # USDC allowance setup (REQUIRED before trading)
│
└── docs/                      # Documentation
    ├── README_HYBRID.md       # User-facing documentation
    ├── HYBRID_BOT_SUMMARY.md  # Technical summary
    └── FINAL_CHECKLIST.md     # Pre-launch checklist
```

---

## Architecture & Design Patterns

### 1. Async-First Architecture

The bot uses Python's `asyncio` for non-blocking operations:

```python
# Main event loop in main_hybrid.py
async def run(self):
    while self.running:
        # Non-blocking market scanning
        market = await self.scanner.find_active_market_async()

        # Non-blocking strategy execution
        if time_remaining <= 60:
            await self.sniper.execute_snipe()
        else:
            self.pair_trader.execute_trading_cycle()
```

**Why Async?**
- WebSocket connections require non-blocking I/O
- Multiple concurrent API requests
- Real-time price monitoring without blocking

### 2. State Machine Pattern

The bot operates as a state machine with two primary modes:

```
┌─────────────┐
│  SCANNING   │ ──> No market found ──> Continue scanning
└─────┬───────┘
      │
      ├─> Market found (>60s remaining)
      │   ┌────────────────┐
      │   │ PAIR_TRADING   │
      │   └────────┬───────┘
      │            │
      ├─> Time <= 60s
      │   ┌────────────────┐
      │   │   SNIPING      │
      │   └────────┬───────┘
      │            │
      └─> Market settled ──> SCANNING
```

### 3. Configuration Management

All configuration is centralized in `config.py`:

- **Validation**: Config validates on initialization (config.py:100-128)
- **Environment Variables**: All sensitive data from .env
- **Type Safety**: Strong typing with type hints
- **Defaults**: Sensible defaults for all parameters

```python
# config.py pattern
class Config:
    def __init__(self):
        self.PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
        self._validate()  # Validate immediately
```

### 4. Separation of Concerns

Each module has a single, well-defined responsibility:

- `client.py` - API communication only
- `pair_trader.py` - Pair trading logic only
- `last_second_sniper.py` - Sniping logic only
- `market_scanner.py` - Market discovery only
- `monitor.py` - Monitoring and reporting only

---

## Key Modules Explained

### core/client.py

**Purpose**: Wrapper around py-clob-client with simplified API

**Key Methods**:
- `get_market(condition_id)` - Fetch market data (client.py:79-111)
- `get_prices(condition_id)` - Get YES/NO prices (client.py:113-154)
- `place_order(token_id, side, size, price)` - Place limit order (client.py:248-290)
- `buy_outcome(token_id, usd_amount, max_price)` - Simplified buy (client.py:460-500)
- `check_allowance()` - Verify USDC allowance (client.py:429-454)

**Important Notes**:
- Always sets API credentials on initialization (client.py:62-66)
- Returns None on failures (graceful degradation)
- Includes retry logic for network issues

### core/pair_trader.py

**Purpose**: Implements gabagool22's pair trading strategy

**Strategy Logic** (pair_trader.py:67-111):
1. Get current YES/NO prices
2. Calculate pair_cost = yes_price + no_price
3. If pair_cost < TARGET_PAIR_COST (default 0.98):
   - Buy YES if spent < MAX_PER_SIDE and price < MAX_PRICE_YES
   - Buy NO if spent < MAX_PER_SIDE and price < MAX_PRICE_NO
4. Maintain balance (imbalance < MAX_IMBALANCE)

**State Tracking**:
- `yes_spent`, `no_spent` - USD spent per side
- `yes_shares`, `no_shares` - Shares accumulated
- `trades` - List of all trades with timestamps

**Safety Features**:
- Position limits (MAX_PER_SIDE)
- Price limits (MAX_PRICE_YES/NO)
- Imbalance control (MAX_IMBALANCE)
- Daily loss limit (MAX_DAILY_LOSS)

### core/last_second_sniper.py

**Purpose**: Implements last-second sniping strategy with WebSocket monitoring

**Strategy Logic** (last_second_sniper.py:155-214):
1. Determine winning side (price > 0.50)
2. Connect to WebSocket for real-time prices
3. When triggered:
   - Check price within limits (SNIPE_MIN_PRICE to SNIPE_MAX_PRICE)
   - Calculate expected profit
   - Execute Fill-or-Kill order
4. Mark as sniped to prevent duplicates

**WebSocket Integration** (last_second_sniper.py:94-153):
```python
async def _ws_monitor(self):
    async with session.ws_connect(self.ws_url) as ws:
        # Subscribe to Level 1 data (best bid/ask)
        await ws.send_json(subscribe_msg)

        # Process real-time updates
        async for msg in ws:
            await self._process_ws_message(data)
```

**Important**: WebSocket provides real-time best ask price, critical for sniping accuracy

### core/market_scanner.py

**Purpose**: Discovers active BTC 15-minute markets

**Discovery Process** (market_scanner.py:32-81):
1. Scrape polymarket.com/crypto/15M for condition_ids (regex-based)
2. Query CLOB API with each condition_id
3. Filter for active markets (active=True, closed=False, accepting_orders=True)
4. Enrich with metadata from Gamma API

**Why This Approach?**
- Polymarket doesn't provide direct "find 15-min BTC markets" API
- Website scraping is most reliable method
- CLOB API requires condition_id for queries

### core/monitor.py

**Purpose**: Tracks trades and generates reports/visualizations

**Monitoring Features**:
- Real-time position tracking
- Trade history logging
- Performance metrics calculation
- Chart generation (matplotlib)
- JSON export for analysis

---

## Configuration & Environment Variables

### Required Variables (.env)

```bash
# WALLET (CRITICAL - NEVER COMMIT)
PRIVATE_KEY=your_private_key_without_0x_prefix
PROXY_ADDRESS=0xYourPolymarketProxyWallet

# PAIR TRADING
TARGET_PAIR_COST=0.98          # Max pair cost to enter trade
ORDER_SIZE_USD=0.75            # Size of each order
MAX_PER_SIDE=10.0              # Max USD per side (total 2x exposure)
MAX_IMBALANCE=0.20             # Max imbalance ratio (20%)
POLLING_INTERVAL=5             # Seconds between price checks

# SNIPING
SNIPE_TRIGGER_SECONDS=60       # When to activate sniper
SNIPE_MIN_PRICE=0.90           # Minimum price (data validation)
SNIPE_MAX_PRICE=0.99           # Maximum price willing to pay
SNIPE_SIZE_USD=10.0            # USD amount per snipe

# SAFETY
DRY_RUN=true                   # Test mode (no real orders)
MAX_DAILY_LOSS=50.0            # Stop trading if loss exceeds this
MAX_PRICE_YES=60.0             # Max price in cents for YES
MAX_PRICE_NO=60.0              # Max price in cents for NO
```

### Configuration Validation

The `Config` class validates all parameters on initialization (config.py:100-128):
- Checks required fields (PRIVATE_KEY, PROXY_ADDRESS)
- Validates numeric ranges
- Ensures logical consistency (e.g., ORDER_SIZE <= MAX_ORDER_SIZE)
- Raises `ValueError` with detailed messages if validation fails

---

## Development Workflows

### Adding a New Feature

1. **Identify the appropriate module** based on separation of concerns
2. **Read the module first** to understand existing patterns
3. **Add tests** in the module's `if __name__ == "__main__"` section
4. **Update config.py** if new parameters needed
5. **Update CLAUDE.md** (this file) with new patterns

Example: Adding a new trading strategy

```python
# 1. Create new module: core/new_strategy.py
class NewStrategy:
    def __init__(self, client, config):
        self.client = client
        self.config = config

    async def execute(self):
        # Strategy logic here
        pass

# 2. Add to main_hybrid.py
from core.new_strategy import NewStrategy

class HybridTradingBot:
    def initialize(self):
        self.new_strategy = NewStrategy(self.client, self.config)

    async def run(self):
        # Add to state machine
        if some_condition:
            await self.new_strategy.execute()

# 3. Add config parameters
class Config:
    def __init__(self):
        self.NEW_STRATEGY_PARAM = float(os.getenv("NEW_STRATEGY_PARAM", "0.5"))
```

### Debugging Workflow

1. **Enable debug logging**: Set `LOG_LEVEL=DEBUG` in .env
2. **Use dry run mode**: Set `DRY_RUN=true`
3. **Check logs**: View `logs/bot_TIMESTAMP.log`
4. **Test individual modules**: Run each module's test function

```bash
# Test individual components
python core/market_scanner.py    # Test market discovery
python core/client.py             # Test API connection
python core/pair_trader.py        # Test pair trading logic
python core/last_second_sniper.py # Test sniper logic
```

### Testing Strategy

Each module includes a test function at the bottom:

```python
# Module structure
class SomeClass:
    # Class implementation
    pass

def test_some_class():
    """Test SomeClass with mock data"""
    # Test logic using mocks
    pass

if __name__ == "__main__":
    test_some_class()
```

**Testing Philosophy**:
- Use mock objects to avoid real API calls
- Test edge cases (no market, network errors, etc.)
- Verify state transitions
- Check error handling

### Pre-commit Checklist

Before committing changes:

- [ ] All tests pass (`python -m pytest` if tests exist)
- [ ] No sensitive data in code (private keys, addresses)
- [ ] .env file not staged (`git status` should not show .env)
- [ ] Code follows existing patterns
- [ ] Type hints added for new functions
- [ ] Docstrings added for new classes/methods
- [ ] CLAUDE.md updated if architecture changed
- [ ] Logging statements use appropriate levels (DEBUG/INFO/WARNING/ERROR)

---

## Code Conventions & Patterns

### 1. Error Handling

**Pattern**: Try-except with graceful degradation

```python
# Good - Returns None on failure
def get_market(self, condition_id: str) -> Optional[Dict]:
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception as e:
        logger.error(f"Error getting market: {e}")
        return None

# Bad - Raises exception, crashes bot
def get_market(self, condition_id: str) -> Dict:
    response = requests.get(url)  # No error handling
    return response.json()
```

**Why?** The bot should continue running even if individual operations fail.

### 2. Logging

**Logging Levels**:
- `DEBUG` - Detailed diagnostic info (e.g., raw API responses)
- `INFO` - Normal operation messages (e.g., "Market found")
- `WARNING` - Unexpected but handled situations (e.g., "Price too high")
- `ERROR` - Errors that prevent specific operations
- `CRITICAL` - Fatal errors requiring shutdown

**Pattern**:
```python
logger = get_logger(__name__)  # Use module name

logger.info(f"✅ Order placed: {order_id}")           # Success
logger.warning(f"⚠️ Price {price} exceeds limit")    # Warning
logger.error(f"❌ Error placing order: {e}")         # Error
```

**Emoji Convention** (optional but recommended):
- ✅ Success
- ❌ Error/Failure
- ⚠️ Warning
- 🎯 Strategy execution
- 💰 Pair trading
- 🔍 Searching/Scanning
- 📊 Data/Stats
- 🔐 Security/Auth

### 3. Type Hints

**Always use type hints** for function signatures:

```python
# Good
def get_prices(self, condition_id: str) -> Optional[Dict[str, float]]:
    pass

# Bad
def get_prices(self, condition_id):
    pass
```

**Common types**:
- `Optional[T]` - Value or None
- `Dict[str, Any]` - Dictionary with string keys
- `List[Dict]` - List of dictionaries
- `float`, `int`, `str`, `bool` - Primitives

### 4. Docstrings

**Use Google-style docstrings**:

```python
def place_order(
    self,
    token_id: str,
    side: str,
    size: float,
    price: float
) -> Optional[str]:
    """
    Place a limit order (buy or sell)

    Args:
        token_id: Token ID to trade
        side: 'BUY' or 'SELL'
        size: Amount in shares
        price: Price per share (0-1)

    Returns:
        Order ID or None

    Example:
        order_id = client.place_order("0xABC...", "BUY", 10.0, 0.48)
    """
    pass
```

### 5. Async/Await

**Rules for async functions**:
1. Mark function as `async def` if it:
   - Calls other async functions (`await`)
   - Uses async I/O (WebSocket, aiohttp)
   - Needs non-blocking sleep (`await asyncio.sleep()`)

2. Always await async calls:
   ```python
   # Good
   market = await self.scanner.find_active_market_async()

   # Bad - Creates coroutine object, doesn't execute
   market = self.scanner.find_active_market_async()
   ```

3. Use `asyncio.create_task()` for background tasks:
   ```python
   # Run WebSocket in background
   self.ws_task = asyncio.create_task(self._ws_monitor())
   ```

### 6. Configuration Access

**Always access config through self.config**:

```python
# Good
if pair_cost < self.config.TARGET_PAIR_COST:
    self._execute_buy('yes', yes_price)

# Bad - Hardcoded values
if pair_cost < 0.98:
    self._execute_buy('yes', yes_price)
```

**Why?** Allows runtime configuration changes and testing with different configs.

### 7. State Management

**Pattern**: Track state as instance variables

```python
class PairTrader:
    def __init__(self, client, config):
        # Trading state
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0

        # Trade history
        self.trades = []

    def set_market(self, market: Dict):
        """Reset state for new market"""
        self.yes_spent = 0.0
        self.no_spent = 0.0
        # ... reset all state
```

**Why?** Makes state explicit and enables position tracking.

---

## Security & Safety

### 1. Private Key Handling

**CRITICAL RULES**:
- ❌ NEVER log private keys
- ❌ NEVER commit .env files
- ❌ NEVER hardcode private keys
- ✅ Always load from environment variables
- ✅ Validate .gitignore includes .env

```python
# .gitignore (MUST INCLUDE)
.env
.env.*
!.env.example
*.key
```

### 2. DRY_RUN Mode

**Always test in DRY_RUN mode first**:

```python
if self.config.DRY_RUN:
    print(f"🔔 DRY RUN: Would buy {size} shares @ ${price}")
    return True  # Simulate success
else:
    # Execute real order
    order_id = self.client.place_order(...)
```

**Purpose**: Allows testing logic without risking real funds.

### 3. Order Validation

**Validate before executing orders**:

```python
def _execute_buy(self, side: str, price: float):
    # 1. Check budget
    if self.yes_spent >= self.config.MAX_PER_SIDE:
        return

    # 2. Check price limits
    if price > self.config.MAX_PRICE_YES / 100:
        return

    # 3. Check imbalance
    if self._calculate_imbalance() > self.config.MAX_IMBALANCE:
        return

    # 4. Execute order
    success = self.client.buy_outcome(...)
```

### 4. Daily Loss Limits

**Implement circuit breakers**:

```python
def _check_daily_loss_limit(self) -> bool:
    """Check if daily loss limit exceeded"""
    today = datetime.now().date()

    # Reset if new day
    if today != self.start_of_day:
        self.daily_pnl = 0.0
        self.start_of_day = today

    # Check limit
    return self.daily_pnl < -self.config.MAX_DAILY_LOSS
```

---

## Common Issues & Solutions

### Issue 1: "USDC allowance not set"

**Cause**: Bot needs USDC spending approval on-chain

**Solution**:
```bash
python scripts/approve.py
```

**How it works**: Uses Web3.py to call `approve()` on USDC contract, granting Polymarket's Exchange contract permission to spend USDC.

### Issue 2: "No active market found"

**Causes**:
- Markets only available during US trading hours (9:30 AM - 4 PM EST)
- Low volatility periods
- Weekends

**Solution**: Wait for market hours or test with different ASSET in config

### Issue 3: WebSocket disconnects

**Cause**: Network instability or Polymarket server issues

**Solution**: Sniper includes auto-reconnect logic. If persistent:
```python
# Add retry logic in _ws_monitor
for attempt in range(3):
    try:
        async with session.ws_connect(self.ws_url) as ws:
            # ...
    except Exception as e:
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
        else:
            raise
```

### Issue 4: Orders not filling

**Causes**:
- Price moved too fast
- Insufficient liquidity
- Network latency

**Solutions**:
1. Increase price slippage tolerance:
   ```python
   price=current_price * 1.02  # Allow 2% slippage
   ```
2. Reduce order size
3. Run on VPS closer to Polymarket servers

### Issue 5: Imbalance errors

**Cause**: YES/NO positions too unbalanced

**Solution**: Imbalance control logic in pair_trader.py:220-235 automatically rebalances by preferring the underweight side.

---

## API Rate Limits & Best Practices

### Polymarket API Limits

- **CLOB API**: ~100 requests/second
- **Gamma API**: ~50 requests/second
- **WebSocket**: 1 connection per market

**Best Practices**:
1. Cache market data (avoid repeated fetches)
2. Use WebSocket for real-time data (not polling)
3. Add exponential backoff on failures
4. Respect rate limits (use request throttling if needed)

```python
# Example: Simple rate limiter
import time
from functools import wraps

def rate_limit(calls_per_second):
    min_interval = 1.0 / calls_per_second
    last_call = [0.0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_call[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            result = func(*args, **kwargs)
            last_call[0] = time.time()
            return result
        return wrapper
    return decorator

@rate_limit(10)  # Max 10 calls/second
def get_market(self, condition_id):
    # ...
```

---

## Testing Strategies

### Unit Testing

Test individual components in isolation:

```python
def test_pair_trader():
    # Mock config
    class MockConfig:
        TARGET_PAIR_COST = 0.98
        ORDER_SIZE_USD = 0.75
        MAX_PER_SIDE = 10.0

    # Mock client
    class MockClient:
        def buy_outcome(self, token_id, usd_amount, max_price):
            print(f"[MOCK] Would buy {usd_amount} at {max_price}")
            return True

    trader = PairTrader(MockClient(), MockConfig())
    # Test logic...
```

### Integration Testing

Test module interactions with real APIs (use testnet if available):

```bash
# Set test mode in .env
DRY_RUN=true
MAX_PER_SIDE=1.0  # Small amounts

# Run bot
python main_hybrid.py
```

### Simulation Testing

Use historical data to simulate strategies:

```python
# utils/backtester.py (you could create this)
class Backtester:
    def __init__(self, historical_prices):
        self.prices = historical_prices

    def simulate_pair_trading(self, target_pair_cost):
        # Simulate trades on historical data
        pass
```

---

## Performance Optimization

### 1. Async Optimization

**Use gather() for parallel operations**:

```python
# Bad - Sequential (slow)
prices = {}
prices['YES'] = await self.get_price(yes_token_id)
prices['NO'] = await self.get_price(no_token_id)

# Good - Parallel (fast)
yes_price, no_price = await asyncio.gather(
    self.get_price(yes_token_id),
    self.get_price(no_token_id)
)
prices = {'YES': yes_price, 'NO': no_price}
```

### 2. Caching

**Cache market data to reduce API calls**:

```python
from functools import lru_cache
from time import time

@lru_cache(maxsize=128)
def get_market_cached(self, condition_id: str, ttl: int = 30):
    """Cache market data for ttl seconds"""
    # Implementation with TTL
    pass
```

### 3. Connection Pooling

**Reuse HTTP connections**:

```python
import requests

# Create session (reuses connections)
self.session = requests.Session()

# Use session for all requests
response = self.session.get(url, params=params)
```

---

## Monitoring & Observability

### Logging Best Practices

1. **Log at appropriate levels**:
   ```python
   logger.debug(f"Raw API response: {response.json()}")  # Verbose
   logger.info(f"Market found: {market['title']}")       # Normal
   logger.warning(f"Price exceeds limit: {price}")       # Unexpected
   logger.error(f"API request failed: {e}")              # Error
   ```

2. **Include context in log messages**:
   ```python
   # Good - Includes context
   logger.info(f"Bought {shares} shares of {side} @ ${price:.4f} in market {market_id}")

   # Bad - Missing context
   logger.info("Order executed")
   ```

3. **Use structured logging for critical events**:
   ```python
   logger.info(f"TRADE_EXECUTED: "
               f"side={side} "
               f"shares={shares:.2f} "
               f"price={price:.4f} "
               f"market={market_id}")
   ```

### Metrics to Track

1. **Performance Metrics**:
   - Win rate (profitable trades / total trades)
   - Average profit per trade
   - Daily/weekly PnL
   - Sharpe ratio (if tracking long enough)

2. **Operational Metrics**:
   - API response times
   - Order fill rates
   - WebSocket uptime
   - Error rates

3. **Risk Metrics**:
   - Current exposure (total capital at risk)
   - Position imbalance
   - Daily loss
   - Largest drawdown

---

## Deployment Considerations

### Running in Production

**VPS Setup** (for best latency):

```bash
# 1. Choose VPS near Polymarket servers
# Recommended: AWS US-East or Germany

# 2. Install dependencies
sudo apt update
sudo apt install python3.10 python3-pip
pip3 install -r requirements_hybrid.txt

# 3. Configure .env
nano .env
# Add PRIVATE_KEY, PROXY_ADDRESS, etc.

# 4. Run bot in background
nohup python3 main_hybrid.py > bot.log 2>&1 &

# 5. Monitor
tail -f bot.log
```

### Process Management

**Use systemd for auto-restart**:

```ini
# /etc/systemd/system/polymarket-bot.service
[Unit]
Description=Polymarket Hybrid Trading Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/polymarket-hybrid-bot
ExecStart=/usr/bin/python3 main_hybrid.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable polymarket-bot
sudo systemctl start polymarket-bot

# Check status
sudo systemctl status polymarket-bot
```

### Monitoring in Production

**Use monitoring tools**:

1. **Uptime monitoring**: Pingdom, UptimeRobot
2. **Log aggregation**: Papertrail, Loggly
3. **Alerting**: PagerDuty, Telegram bot

**Example Telegram alerting**:

```python
import requests

def send_telegram_alert(message):
    """Send alert to Telegram"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

    requests.post(url, json=payload)

# Use in critical paths
try:
    order_id = self.client.place_order(...)
    send_telegram_alert(f"✅ Order executed: {order_id}")
except Exception as e:
    send_telegram_alert(f"❌ Order failed: {e}")
```

---

## Git Workflow

### Branch Strategy

- `main` - Production-ready code
- `develop` - Development branch
- `feature/*` - Feature branches
- `hotfix/*` - Critical fixes

### Commit Message Convention

Follow conventional commits:

```
type(scope): subject

body (optional)

footer (optional)
```

**Types**:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks

**Examples**:
```
feat(sniper): add WebSocket reconnection logic

Add automatic reconnection with exponential backoff
when WebSocket connection drops.

Closes #42

fix(pair_trader): correct imbalance calculation

The imbalance was using absolute values incorrectly,
causing trades to be skipped unnecessarily.

docs(claude): update CLAUDE.md with new patterns
```

### Pre-commit Hooks (Recommended)

```bash
# .git/hooks/pre-commit
#!/bin/bash

# Check for .env in staged files
if git diff --cached --name-only | grep -q "^.env$"; then
    echo "❌ Error: .env file is staged! Aborting commit."
    exit 1
fi

# Check for private keys in code
if git diff --cached | grep -i "private_key.*=.*['\"]0x"; then
    echo "❌ Error: Private key found in code! Aborting commit."
    exit 1
fi

echo "✅ Pre-commit checks passed"
exit 0
```

---

## Future Enhancements

### Potential Improvements

1. **Multi-asset support**:
   - Extend beyond BTC to ETH, SOL, etc.
   - Add asset selection logic

2. **Machine learning**:
   - Predict optimal entry/exit times
   - Sentiment analysis from Polymarket comments

3. **Portfolio optimization**:
   - Kelly criterion for position sizing
   - Dynamic risk adjustment

4. **Advanced order types**:
   - Iceberg orders (hide true size)
   - TWAP (Time-Weighted Average Price)

5. **Backtesting framework**:
   - Historical data replay
   - Strategy optimization
   - Walk-forward analysis

6. **Web dashboard**:
   - Real-time monitoring UI
   - Performance analytics
   - Manual override controls

---

## Resources & References

### Official Documentation
- [Polymarket API Docs](https://docs.polymarket.com/)
- [py-clob-client GitHub](https://github.com/Polymarket/py-clob-client)
- [Python Asyncio Docs](https://docs.python.org/3/library/asyncio.html)

### Trading Strategy References
- gabagool22's pair trading approach (inspiration for Strategy 1)
- Last-second sniping latency arbitrage (Strategy 2)

### Related Projects
- Polymarket trading bots on GitHub
- Prediction market analytics tools

---

## Contact & Support

### For Issues
1. Check existing documentation (README_HYBRID.md, HYBRID_BOT_SUMMARY.md)
2. Review logs in `logs/` directory
3. Test individual components
4. Check Polymarket API status

### Contributing
1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Submit pull request with detailed description
5. Update CLAUDE.md if adding new patterns

---

## Changelog

### Version 1.0.0 (Current)
- Initial release with dual-strategy system
- Pair trading (gabagool22 approach)
- Last-second sniping with WebSocket
- Full async architecture
- Comprehensive monitoring and reporting
- DRY_RUN mode for safe testing

---

**Last Updated**: 2025-12-08
**Maintained By**: Project Team
**For AI Assistants**: This document should be updated whenever architectural changes are made to the codebase.
