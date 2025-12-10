"""
Last-Second Sniper V2 - Uses CLOB Orderbook for Real Prices
"""
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict


class LastSecondSniper:
    """
    Last-second sniping strategy with REAL orderbook prices
    """
    
    def __init__(self, client, config):
        self.client = client
        self.config = config
        
        # API endpoints
        self.clob_url = "https://clob.polymarket.com"
        self.gamma_url = "https://gamma-api.polymarket.com"
        
        # Market state
        self.market = None
        self.yes_token_id = None
        self.no_token_id = None
        self.winning_side = None
        self.winning_token_id = None
        self.best_ask = None
        
        # Execution state
        self.sniped = False
        self.last_snipe_time = None
        
        # Price monitoring
        self.price_updates = []
        self.monitoring_task = None
    
    async def set_market(self, market: Dict):
        """Set market and start price monitoring"""
        self.market = market
        self.yes_token_id = market.get('yes_token_id', '')
        self.no_token_id = market.get('no_token_id', '')
        self.sniped = False
        
        print(f"\n🎯 Sniper armed for: {market['title'][:50]}...")
        
        # Determine winning side from REAL orderbook prices
        await self._determine_winning_side()
        
        # Start price monitoring task
        if not self.monitoring_task or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self._price_monitor())
    
    async def _determine_winning_side(self):
        """Determine which side is likely to win based on REAL orderbook prices"""
        
        prices = await self._fetch_clob_prices_async()
        
        if not prices:
            # Fallback to market data
            yes_price = self.market.get('yes_price', 0.5)
            no_price = self.market.get('no_price', 0.5)
        else:
            yes_price = prices.get('yes', 0.5)
            no_price = prices.get('no', 0.5)
        
        # Side with price > 0.50 is likely winner
        if yes_price > no_price:
            self.winning_side = 'YES'
            self.winning_token_id = self.yes_token_id
            self.best_ask = yes_price
            print(f"   Predicted winner: YES (price: ${yes_price:.4f})")
        else:
            self.winning_side = 'NO'
            self.winning_token_id = self.no_token_id
            self.best_ask = no_price
            print(f"   Predicted winner: NO (price: ${no_price:.4f})")
    
    async def _price_monitor(self):
        """Monitor prices via CLOB orderbook polling"""
        print(f"   📡 Price monitoring started (CLOB orderbook)")
        
        while not self.sniped:
            try:
                prices = await self._fetch_clob_prices_async()
                
                if prices:
                    # Update winning side dynamically
                    yes_price = prices.get('yes', 0.5)
                    no_price = prices.get('no', 0.5)
                    
                    if yes_price > no_price:
                        self.winning_side = 'YES'
                        self.winning_token_id = self.yes_token_id
                        self.best_ask = yes_price
                    else:
                        self.winning_side = 'NO'
                        self.winning_token_id = self.no_token_id
                        self.best_ask = no_price
                    
                    # Track price history
                    self.price_updates.append({
                        'timestamp': datetime.now().timestamp(),
                        'yes_price': yes_price,
                        'no_price': no_price,
                        'winning_side': self.winning_side,
                        'best_ask': self.best_ask
                    })
                    
                    # Limit history
                    if len(self.price_updates) > 100:
                        self.price_updates.pop(0)
                
                # Poll every 1 second for sniper (faster than pair trader)
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ Price monitor error: {e}")
                await asyncio.sleep(2)
    
    async def _fetch_clob_prices_async(self) -> Optional[Dict]:
        """Fetch real prices from CLOB orderbook (async)"""
        try:
            prices = {}
            
            async with aiohttp.ClientSession() as session:
                # Get YES orderbook
                if self.yes_token_id:
                    async with session.get(
                        f"{self.clob_url}/book",
                        params={'token_id': self.yes_token_id},
                        timeout=aiohttp.ClientTimeout(total=3)
                    ) as response:
                        if response.status == 200:
                            book = await response.json()
                            if book.get('asks'):
                                prices['yes'] = float(book['asks'][0]['price'])
                
                # Get NO orderbook
                if self.no_token_id:
                    async with session.get(
                        f"{self.clob_url}/book",
                        params={'token_id': self.no_token_id},
                        timeout=aiohttp.ClientTimeout(total=3)
                    ) as response:
                        if response.status == 200:
                            book = await response.json()
                            if book.get('asks'):
                                prices['no'] = float(book['asks'][0]['price'])
            
            if 'yes' in prices and 'no' in prices:
                return prices
            
            return None
            
        except Exception as e:
            return None
    
    async def execute_snipe(self):
        """Execute snipe if conditions are met"""
        
        if self.sniped:
            return
        
        # Refresh prices
        prices = await self._fetch_clob_prices_async()
        if prices:
            if self.winning_side == 'YES':
                self.best_ask = prices.get('yes', self.best_ask)
            else:
                self.best_ask = prices.get('no', self.best_ask)
        
        if self.best_ask is None:
            print(f"   ⚠️ No price data available")
            return
        
        # Check conditions
        if self.best_ask >= self.config.SNIPE_MAX_PRICE:
            print(f"   ⏸️  Price too high: ${self.best_ask:.4f} (max: ${self.config.SNIPE_MAX_PRICE})")
            return
        
        if self.best_ask < self.config.SNIPE_MIN_PRICE:
            print(f"   ⚠️ Price too low: ${self.best_ask:.4f} (might be wrong side)")
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
            self.sniped = True
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
        """Execute the actual snipe order"""
        try:
            shares = self.config.SNIPE_SIZE_USD / self.best_ask
            premium_price = self.best_ask * 1.005  # 0.5% premium for fast fill
            
            print(f"   Placing order: {shares:.2f} shares @ ${premium_price:.4f}")
            
            order_id = self.client.create_limit_buy_order(
                token_id=self.winning_token_id,
                size=shares,
                price=premium_price
            )
            
            if order_id:
                print(f"   Order ID: {order_id}")
                await asyncio.sleep(1)
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
# TEST
# ==========================================

async def test_sniper():
    """Test sniper with real CLOB data"""
    
    print("🧪 Testing Last-Second Sniper V2 (CLOB Prices)...\n")
    
    class MockConfig:
        DRY_RUN = True
        SNIPE_TRIGGER_SECONDS = 60
        SNIPE_MIN_PRICE = 0.50  # Lowered for testing
        SNIPE_MAX_PRICE = 0.99
        SNIPE_SIZE_USD = 10.0
    
    class MockClient:
        def create_limit_buy_order(self, token_id, size, price):
            print(f"   [MOCK] Order: {size:.2f} shares @ ${price:.4f}")
            return "mock_order_123"
    
    # We need real token IDs - let's fetch them
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        # Find active BTC market
        async with session.get(
            "https://gamma-api.polymarket.com/markets",
            params={'limit': 50, 'closed': 'false', 'active': 'true'}
        ) as response:
            if response.status != 200:
                print("❌ Failed to fetch markets")
                return
            
            markets = await response.json()
            
            for market in markets:
                slug = market.get('slug', '').lower()
                if 'btc-updown' in slug:
                    print(f"Found: {market.get('question', 'Unknown')[:50]}")
                    
                    import json
                    clob_tokens = market.get('clobTokenIds')
                    if isinstance(clob_tokens, str):
                        clob_tokens = json.loads(clob_tokens.replace("'", '"'))
                    
                    outcome_prices = market.get('outcomePrices')
                    if isinstance(outcome_prices, str):
                        outcome_prices = json.loads(outcome_prices.replace("'", '"'))
                    
                    mock_market = {
                        'title': market.get('question', 'Test'),
                        'condition_id': market.get('conditionId', ''),
                        'yes_token_id': clob_tokens[0] if clob_tokens else '',
                        'no_token_id': clob_tokens[1] if clob_tokens else '',
                        'yes_price': float(outcome_prices[0]) if outcome_prices else 0.5,
                        'no_price': float(outcome_prices[1]) if outcome_prices else 0.5,
                    }
                    
                    sniper = LastSecondSniper(MockClient(), MockConfig())
                    await sniper.set_market(mock_market)
                    
                    # Wait a bit for price updates
                    await asyncio.sleep(3)
                    
                    # Try execute snipe
                    await sniper.execute_snipe()
                    
                    # Show summary
                    print("\n📊 Snipe Summary:")
                    summary = sniper.get_snipe_summary()
                    for key, value in summary.items():
                        print(f"   {key}: {value}")
                    
                    await sniper.cleanup()
                    break
            else:
                print("No BTC updown market found")


if __name__ == "__main__":
    asyncio.run(test_sniper())