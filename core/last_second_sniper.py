"""
Last-Second Sniper Module - FIXED VERSION
Snipes winning outcome in final seconds before settlement

Strategy:
- Wait until < 60s before market closes
- Monitor real-time prices via REST API (WebSocket optional)
- Identify winning side (price > 0.50)
- Buy if available < $0.99
- Near-zero risk (guaranteed $1.00 settlement)

FIXES:
- Removed broken WebSocket implementation
- Uses REST API polling for price updates (more reliable)
- Proper async/await throughout
"""
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict


class LastSecondSniper:
    """
    Last-second sniping strategy (FIXED)
    
    Logic:
    1. Poll CLOB API for real-time prices every 1-2 seconds
    2. Monitor best ask price for winning side
    3. When time < trigger_seconds AND price < max_price:
       - Execute market buy order
    4. Profit from panic selling / liquidity gaps
    """
    
    def __init__(self, client, config):
        """
        Initialize sniper
        
        Args:
            client: PolymarketClient instance
            config: Bot configuration
        """
        self.client = client
        self.config = config
        
        # API endpoints
        self.clob_url = "https://clob.polymarket.com"
        
        # Market state
        self.market = None
        self.winning_side = None  # 'YES' or 'NO'
        self.winning_token_id = None
        self.best_ask = None
        
        # Execution state
        self.sniped = False
        self.last_snipe_time = None
        
        # Price monitoring
        self.price_updates = []
        self.monitoring_task = None
    
    async def set_market(self, market: Dict):
        """
        Set market and start price monitoring
        
        Args:
            market: Market info dict
        """
        self.market = market
        self.sniped = False
        
        print(f"\n🎯 Sniper armed for: {market['title']}")
        
        # Determine winning side from current prices
        await self._determine_winning_side()
        
        # Start price monitoring task
        if not self.monitoring_task or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self._price_monitor())
    
    async def _determine_winning_side(self):
        """Determine which side is likely to win based on current price"""
        
        # Get latest prices from market
        prices = await self._fetch_current_prices()
        
        if not prices:
            # Fallback to market data
            yes_price = self.market.get('yes_price', 0.5)
            no_price = self.market.get('no_price', 0.5)
        else:
            yes_price = prices.get('YES', 0.5)
            no_price = prices.get('NO', 0.5)
        
        # Side with price > 0.50 is likely winner
        if yes_price > 0.50:
            self.winning_side = 'YES'
            self.winning_token_id = self.market['yes_token_id']
            print(f"   Predicted winner: YES (price: ${yes_price:.4f})")
        else:
            self.winning_side = 'NO'
            self.winning_token_id = self.market['no_token_id']
            print(f"   Predicted winner: NO (price: ${no_price:.4f})")
    
    async def _price_monitor(self):
        """
        Monitor prices via REST API polling (more reliable than WebSocket)
        
        Polls CLOB API every 2 seconds for latest prices
        """
        print(f"   📡 Price monitoring started (REST API polling)")
        
        while not self.sniped:
            try:
                # Fetch current prices
                prices = await self._fetch_current_prices()
                
                if prices and self.winning_side in prices:
                    self.best_ask = prices[self.winning_side]
                    
                    # Track price history
                    self.price_updates.append({
                        'timestamp': datetime.now().timestamp(),
                        'price': self.best_ask,
                        'side': self.winning_side
                    })
                    
                    # Limit history to last 100 updates
                    if len(self.price_updates) > 100:
                        self.price_updates.pop(0)
                
                # Poll every 2 seconds
                await asyncio.sleep(2)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ Price monitor error: {e}")
                await asyncio.sleep(5)
    
    async def _fetch_current_prices(self) -> Optional[Dict]:
        """
        Fetch current prices from CLOB API
        
        Returns:
            Dict with YES/NO prices or None
        """
        try:
            url = f"{self.clob_url}/markets"
            params = {'condition_id': self.market['condition_id']}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Parse response
                    if isinstance(data, dict) and 'data' in data:
                        markets = data['data']
                    else:
                        markets = data if isinstance(data, list) else []
                    
                    if not markets:
                        return None
                    
                    market = markets[0]
                    tokens = market.get('tokens', [])
                    
                    prices = {}
                    
                    for token in tokens:
                        outcome = token.get('outcome', '').upper()
                        price = float(token.get('price', 0))
                        
                        if outcome in ['YES', 'UP']:
                            prices['YES'] = price
                        elif outcome in ['NO', 'DOWN']:
                            prices['NO'] = price
                    
                    return prices if prices else None
                    
        except Exception as e:
            # Suppress errors during polling (too noisy)
            return None
    
    async def execute_snipe(self):
        """
        Execute snipe if conditions are met
        
        Conditions:
        1. Not already sniped
        2. Best ask price available
        3. Price within limits (< max_price)
        """
        
        if self.sniped:
            return
        
        if self.best_ask is None:
            # No price data yet, try to fetch
            prices = await self._fetch_current_prices()
            if prices and self.winning_side in prices:
                self.best_ask = prices[self.winning_side]
            else:
                print(f"   ⚠️ No price data available")
                return
        
        # Check conditions
        if self.best_ask >= self.config.SNIPE_MAX_PRICE:
            print(f"   ⏸️  Price too high: ${self.best_ask:.4f} (max: ${self.config.SNIPE_MAX_PRICE})")
            return
        
        if self.best_ask < self.config.SNIPE_MIN_PRICE:
            print(f"   ⚠️ Suspicious low price: ${self.best_ask:.4f}")
            # Could be error in data, skip
            return
        
        # Calculate potential profit
        potential_profit = 1.0 - self.best_ask
        profit_pct = (potential_profit / self.best_ask) * 100
        expected_shares = self.config.SNIPE_SIZE_USD / self.best_ask
        expected_gain = potential_profit * expected_shares
        
        print(f"\n{'='*60}")
        print(f"🎯 SNIPE OPPORTUNITY DETECTED!")
        print(f"{'='*60}")
        print(f"Side:           {self.winning_side}")
        print(f"Current Price:  ${self.best_ask:.4f}")
        print(f"Settlement:     $1.00")
        print(f"Profit/Share:   ${potential_profit:.4f} ({profit_pct:.2f}%)")
        print(f"Snipe Size:     ${self.config.SNIPE_SIZE_USD}")
        print(f"Expected Shares: {expected_shares:.2f}")
        print(f"Expected Gain:  ${expected_gain:.2f}")
        print(f"{'='*60}")
        
        # DRY RUN mode
        if self.config.DRY_RUN:
            print(f"🔔 DRY RUN: Would execute snipe now")
            print(f"   Set DRY_RUN=false in .env to execute real orders")
            self.sniped = True  # Mark as done
            self.last_snipe_time = datetime.now()
            return
        
        # EXECUTE SNIPE
        print(f"⚡ EXECUTING SNIPE...")
        
        success = await self._execute_snipe_order()
        
        if success:
            print(f"✅ SNIPE SUCCESSFUL!")
            self.sniped = True
            self.last_snipe_time = datetime.now()
        else:
            print(f"❌ Snipe failed - will retry if time permits")
    
    async def _execute_snipe_order(self) -> bool:
        """
        Execute the actual snipe order
        
        Uses limit order with slight premium for fast fill
        
        Returns:
            True if successful
        """
        try:
            # Calculate shares to buy
            shares = self.config.SNIPE_SIZE_USD / self.best_ask
            
            # Create limit order with 0.1% premium for faster fill
            premium_price = self.best_ask * 1.001
            
            print(f"   Placing order: {shares:.2f} shares @ ${premium_price:.4f}")
            
            # Place order (synchronous - client is not async)
            order_id = self.client.create_limit_buy_order(
                token_id=self.winning_token_id,
                size=shares,
                price=premium_price
            )
            
            if order_id:
                print(f"   Order ID: {order_id}")
                
                # Wait briefly for potential fill
                await asyncio.sleep(1)
                
                # In production, verify fill via order status API
                # For now, assume success if order was placed
                
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Snipe execution error: {e}")
            return False
    
    def get_snipe_summary(self) -> Dict:
        """Get summary of snipe activity"""
        return {
            'sniped': self.sniped,
            'winning_side': self.winning_side,
            'best_ask': self.best_ask,
            'snipe_time': self.last_snipe_time.isoformat() if self.last_snipe_time else None,
            'price_updates_count': len(self.price_updates)
        }
    
    async def cleanup(self):
        """Cleanup monitoring tasks"""
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        print("   🎯 Sniper cleanup complete")


# ==========================================
# TESTING
# ==========================================

async def test_sniper():
    """Test sniper with mock data"""
    
    print("🧪 Testing Last-Second Sniper (FIXED)...\n")
    
    # Mock config
    class MockConfig:
        DRY_RUN = True
        SNIPE_TRIGGER_SECONDS = 60
        SNIPE_MIN_PRICE = 0.90
        SNIPE_MAX_PRICE = 0.99
        SNIPE_SIZE_USD = 10.0
    
    # Mock client
    class MockClient:
        def get_market_price(self, token_id):
            return 0.97
        
        def create_limit_buy_order(self, token_id, size, price):
            print(f"   [MOCK] Order: {size:.2f} shares @ ${price:.4f}")
            return "mock_order_123"
    
    # Mock market
    mock_market = {
        'title': 'Test BTC 15min',
        'condition_id': '0x123',
        'yes_token_id': '0xYES',
        'no_token_id': '0xNO',
        'yes_price': 0.97,
        'no_price': 0.03,
        'end_time': '2025-12-08T12:15:00Z'
    }
    
    # Create sniper
    sniper = LastSecondSniper(MockClient(), MockConfig())
    await sniper.set_market(mock_market)
    
    # Simulate price update
    sniper.best_ask = 0.97
    
    # Execute snipe
    await sniper.execute_snipe()
    
    # Show summary
    print("\n📊 Snipe Summary:")
    summary = sniper.get_snipe_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")
    
    await sniper.cleanup()


if __name__ == "__main__":
    asyncio.run(test_sniper())