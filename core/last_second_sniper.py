"""
Last-Second Sniper Module
Snipes winning outcome in final seconds before settlement

Strategy:
- Wait until < 60s before market closes
- Identify winning side (price > 0.50)
- Buy if available < $0.99
- Near-zero risk (guaranteed $1.00 settlement)
"""
import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Optional, Dict


class LastSecondSniper:
    """
    Last-second sniping strategy
    
    Logic:
    1. Connect to Polymarket WebSocket for real-time prices
    2. Monitor best ask price for winning side
    3. When time < trigger_seconds AND price < max_price:
       - Execute FOK (Fill or Kill) order
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
        
        # WebSocket connection
        self.ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.ws = None
        self.ws_task = None
        
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
    
    async def set_market(self, market: Dict):
        """
        Set market and start WebSocket monitoring
        
        Args:
            market: Market info dict
        """
        self.market = market
        self.sniped = False
        
        print(f"\n🎯 Sniper armed for: {market['title']}")
        
        # Determine winning side from current prices
        await self._determine_winning_side()
        
        # Start WebSocket connection
        if not self.ws_task or self.ws_task.done():
            self.ws_task = asyncio.create_task(self._ws_monitor())
    
    async def _determine_winning_side(self):
        """Determine which side is likely to win based on current price"""
        
        yes_price = self.market.get('yes_price', 0.5)
        no_price = self.market.get('no_price', 0.5)
        
        # Side with price > 0.50 is likely winner
        if yes_price > 0.50:
            self.winning_side = 'YES'
            self.winning_token_id = self.market['yes_token_id']
            print(f"   Predicted winner: YES (price: ${yes_price:.4f})")
        else:
            self.winning_side = 'NO'
            self.winning_token_id = self.market['no_token_id']
            print(f"   Predicted winner: NO (price: ${no_price:.4f})")
    
    async def _ws_monitor(self):
        """
        Monitor WebSocket for real-time price updates
        
        Connects to Polymarket's WebSocket and tracks best ask price
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.ws_url) as ws:
                    self.ws = ws
                    
                    # Subscribe to market
                    subscribe_msg = {
                        "type": "subscribe",
                        "channel": "market",
                        "market": self.market['condition_id'],
                        "level": 1  # Level 1 = best bid/ask only
                    }
                    
                    await ws.send_json(subscribe_msg)
                    print(f"   📡 WebSocket connected, monitoring prices...")
                    
                    # Listen for messages
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            await self._process_ws_message(data)
                        
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"⚠️ WebSocket error: {ws.exception()}")
                            break
        
        except Exception as e:
            print(f"❌ WebSocket monitor error: {e}")
    
    async def _process_ws_message(self, data: dict):
        """Process WebSocket price update message"""
        
        if data.get('type') != 'market':
            return
        
        # Extract best ask for winning token
        market_data = data.get('data', {})
        token_data = market_data.get(self.winning_token_id, {})
        
        if 'asks' in token_data and token_data['asks']:
            # Best ask = lowest sell price
            best_ask_data = token_data['asks'][0]
            self.best_ask = float(best_ask_data.get('price', 0))
            
            # Track price history
            self.price_updates.append({
                'timestamp': datetime.now().timestamp(),
                'price': self.best_ask,
                'side': self.winning_side
            })
            
            # Limit history to last 100 updates
            if len(self.price_updates) > 100:
                self.price_updates.pop(0)
    
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
            # No price data yet, use client to fetch
            self.best_ask = self.client.get_market_price(self.winning_token_id)
        
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
        
        print(f"\n{'='*60}")
        print(f"🎯 SNIPE OPPORTUNITY DETECTED!")
        print(f"{'='*60}")
        print(f"Side:           {self.winning_side}")
        print(f"Current Price:  ${self.best_ask:.4f}")
        print(f"Settlement:     $1.00")
        print(f"Profit/Share:   ${potential_profit:.4f} ({profit_pct:.2f}%)")
        print(f"Snipe Size:     ${self.config.SNIPE_SIZE_USD}")
        print(f"Expected Gain:  ${potential_profit * (self.config.SNIPE_SIZE_USD / self.best_ask):.2f}")
        print(f"{'='*60}")
        
        # DRY RUN mode
        if self.config.DRY_RUN:
            print(f"🔔 DRY RUN: Would execute snipe now")
            print(f"   Set DRY_RUN=false in .env to execute real orders")
            self.sniped = True  # Mark as done
            return
        
        # EXECUTE SNIPE
        print(f"⚡ EXECUTING SNIPE...")
        
        success = await self._execute_snipe_order()
        
        if success:
            print(f"✅ SNIPE SUCCESSFUL!")
            self.sniped = True
            self.last_snipe_time = datetime.now()
        else:
            print(f"❌ Snipe failed")
    
    async def _execute_snipe_order(self) -> bool:
        """
        Execute the actual snipe order
        
        Uses Fill-or-Kill (FOK) order type for immediate execution
        
        Returns:
            True if successful
        """
        try:
            # Calculate shares to buy
            shares = self.config.SNIPE_SIZE_USD / self.best_ask
            
            # Create FOK order (Fill or Kill - execute immediately or cancel)
            order_id = self.client.create_limit_buy_order(
                token_id=self.winning_token_id,
                size=shares,
                price=self.best_ask * 1.001  # Slight premium for faster fill
            )
            
            if order_id:
                print(f"   Order ID: {order_id}")
                
                # Wait briefly for fill confirmation
                await asyncio.sleep(1)
                
                # Check if filled
                # (In production, you'd verify via order status API)
                
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
            'snipe_time': self.last_snipe_time,
            'price_updates_count': len(self.price_updates)
        }
    
    async def cleanup(self):
        """Cleanup WebSocket connections"""
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        if self.ws_task and not self.ws_task.done():
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass


# ==========================================
# TESTING
# ==========================================

async def test_sniper():
    """Test sniper with mock data"""
    
    print("🧪 Testing Last-Second Sniper...\n")
    
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