"""
WebSocket Real-Time Market Scanner
Connects to Polymarket WebSocket for INSTANT market notifications
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import websockets
import json
import aiohttp
from typing import Optional, Dict, Callable
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketScanner:
    """
    Real-time market scanner using WebSocket
    
    Polymarket WebSocket endpoint: wss://ws-subscriptions-clob.polymarket.com/ws/market
    """
    
    def __init__(self, on_market_found: Optional[Callable] = None):
        """
        Initialize WebSocket scanner
        
        Args:
            on_market_found: Callback function when market is found
                             Signature: async def callback(market: Dict)
        """
        self.ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.clob_url = "https://clob.polymarket.com/markets"
        self.gamma_url = "https://gamma-api.polymarket.com/markets"
        
        self.on_market_found = on_market_found
        
        self.connected = False
        self.subscribed_markets = set()
        
        # Track active BTC 15M markets
        self.active_markets = {}
        
        logger.info("🔌 WebSocket Scanner initialized")
    
    async def start(self):
        """
        Start WebSocket connection and listen for markets
        
        This runs indefinitely, reconnecting on disconnect
        """
        retry_count = 0
        max_retries = 10
        
        while retry_count < max_retries:
            try:
                logger.info("📡 Connecting to Polymarket WebSocket...")
                
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    
                    self.connected = True
                    retry_count = 0  # Reset on successful connection
                    
                    logger.info("✅ WebSocket connected!")
                    
                    # Start periodic market discovery
                    discovery_task = asyncio.create_task(
                        self._periodic_market_discovery()
                    )
                    
                    # Listen for messages
                    try:
                        async for message in websocket:
                            await self._handle_message(message, websocket)
                    
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("⚠️  WebSocket connection closed")
                        self.connected = False
                    
                    finally:
                        discovery_task.cancel()
                        try:
                            await discovery_task
                        except asyncio.CancelledError:
                            pass
            
            except Exception as e:
                logger.error(f"❌ WebSocket error: {e}")
                self.connected = False
                retry_count += 1
                
                if retry_count < max_retries:
                    wait_time = min(2 ** retry_count, 60)  # Exponential backoff
                    logger.info(f"   Retrying in {wait_time}s... ({retry_count}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("❌ Max retries reached, giving up")
                    break
    
    async def _periodic_market_discovery(self):
        """
        Periodically discover new BTC 15M markets
        
        Runs every 30 seconds to check for new markets
        """
        while self.connected:
            try:
                logger.info("🔍 Discovering markets...")
                
                # Get active BTC 15M markets from Gamma API
                markets = await self._get_btc_markets()
                
                for market in markets:
                    condition_id = market.get('condition_id')
                    
                    if not condition_id:
                        continue
                    
                    # Check if this is a new market
                    if condition_id not in self.active_markets:
                        logger.info(f"🆕 New market discovered: {condition_id[:20]}...")
                        
                        # Verify with CLOB
                        clob_data = await self._get_market_from_clob(condition_id)
                        
                        if clob_data and self._is_market_active(clob_data):
                            # Build market info
                            market_info = self._build_market_info(market, clob_data)
                            
                            # Store
                            self.active_markets[condition_id] = market_info
                            
                            logger.info(f"✅ Active market confirmed!")
                            logger.info(f"   {market_info.get('question', 'N/A')[:70]}")
                            
                            # Subscribe to this market on WebSocket
                            await self._subscribe_market(condition_id)
                            
                            # Trigger callback
                            if self.on_market_found:
                                await self.on_market_found(market_info)
                
                logger.info(f"   Active markets: {len(self.active_markets)}")
                
            except Exception as e:
                logger.error(f"Error in market discovery: {e}")
            
            # Wait 30 seconds before next discovery
            await asyncio.sleep(30)
    
    async def _subscribe_market(self, condition_id: str):
        """
        Subscribe to market updates via WebSocket
        
        This sends subscription message to WebSocket
        """
        # Note: Polymarket WebSocket subscription format might differ
        # This is a placeholder - need to check actual Polymarket WS protocol
        
        subscribe_msg = {
            "type": "subscribe",
            "channel": "market",
            "condition_id": condition_id
        }
        
        # Send will happen in _handle_message when websocket is available
        self.subscribed_markets.add(condition_id)
        
        logger.debug(f"📬 Subscribed to market: {condition_id[:20]}...")
    
    async def _handle_message(self, message: str, websocket):
        """
        Handle incoming WebSocket message
        
        Args:
            message: Raw WebSocket message
            websocket: WebSocket connection (for sending)
        """
        try:
            data = json.loads(message)
            
            msg_type = data.get('type')
            
            if msg_type == 'price_update':
                # Price update for subscribed market
                condition_id = data.get('condition_id')
                
                if condition_id in self.active_markets:
                    # Update prices
                    prices = data.get('prices', {})
                    
                    market = self.active_markets[condition_id]
                    market['yes_price'] = float(prices.get('YES', market['yes_price']))
                    market['no_price'] = float(prices.get('NO', market['no_price']))
                    
                    logger.debug(f"💹 Price update: YES ${market['yes_price']:.4f}, NO ${market['no_price']:.4f}")
            
            elif msg_type == 'market_created':
                # New market created
                condition_id = data.get('condition_id')
                
                logger.info(f"🆕 Market created notification: {condition_id[:20]}...")
                
                # Fetch full market data
                market = await self._get_market_from_gamma(condition_id)
                clob_data = await self._get_market_from_clob(condition_id)
                
                if market and clob_data and self._is_market_active(clob_data):
                    market_info = self._build_market_info(market, clob_data)
                    self.active_markets[condition_id] = market_info
                    
                    # Subscribe
                    await self._subscribe_market(condition_id)
                    
                    # Callback
                    if self.on_market_found:
                        await self.on_market_found(market_info)
            
            elif msg_type == 'market_closed':
                # Market closed
                condition_id = data.get('condition_id')
                
                if condition_id in self.active_markets:
                    logger.info(f"🔒 Market closed: {condition_id[:20]}...")
                    del self.active_markets[condition_id]
                    self.subscribed_markets.discard(condition_id)
            
            else:
                logger.debug(f"📨 Unknown message type: {msg_type}")
        
        except json.JSONDecodeError:
            logger.debug(f"⚠️  Invalid JSON: {message[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    # ==========================================
    # API Methods
    # ==========================================
    
    async def _get_btc_markets(self) -> list:
        """Get BTC 15M markets from Gamma API"""
        try:
            params = {
                'limit': 50,
                'active': 'true',
                'closed': 'false',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.gamma_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status != 200:
                        return []
                    
                    markets = await response.json()
                    
                    if not isinstance(markets, list):
                        return []
                    
                    # Filter for BTC 15M
                    btc_markets = []
                    
                    for market in markets:
                        question = market.get('question', '').lower()
                        
                        is_btc = any(kw in question for kw in ['btc', 'bitcoin'])
                        is_15m = any(kw in question for kw in ['15 minute', '15min', '15m'])
                        
                        if is_btc and is_15m:
                            btc_markets.append(market)
                    
                    return btc_markets
        
        except Exception as e:
            logger.error(f"Error getting BTC markets: {e}")
            return []
    
    async def _get_market_from_gamma(self, condition_id: str) -> Optional[Dict]:
        """Get market from Gamma API"""
        try:
            params = {'condition_id': condition_id}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.gamma_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status != 200:
                        return None
                    
                    markets = await response.json()
                    
                    return markets[0] if markets and len(markets) > 0 else None
        
        except Exception as e:
            logger.debug(f"Error getting market from Gamma: {e}")
            return None
    
    async def _get_market_from_clob(self, condition_id: str) -> Optional[Dict]:
        """Get market from CLOB API"""
        try:
            params = {'condition_id': condition_id}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.clob_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    if isinstance(data, dict) and 'data' in data:
                        markets = data['data']
                    else:
                        markets = data if isinstance(data, list) else []
                    
                    return markets[0] if markets else None
        
        except Exception as e:
            logger.debug(f"Error getting market from CLOB: {e}")
            return None
    
    def _is_market_active(self, clob_data: Dict) -> bool:
        """Check if market is tradeable"""
        if not clob_data.get('active', False):
            return False
        
        if clob_data.get('closed', False):
            return False
        
        if not clob_data.get('accepting_orders', False):
            return False
        
        tokens = clob_data.get('tokens', [])
        if len(tokens) != 2:
            return False
        
        return True
    
    def _build_market_info(self, gamma_market: Dict, clob_data: Dict) -> Dict:
        """Build standardized market info"""
        tokens = clob_data.get('tokens', [])
        
        yes_token = None
        no_token = None
        
        for token in tokens:
            outcome = token.get('outcome', '').upper()
            if outcome in ['YES', 'UP', 'HIGHER']:
                yes_token = token
            elif outcome in ['NO', 'DOWN', 'LOWER']:
                no_token = token
        
        if not yes_token:
            yes_token = tokens[0] if len(tokens) > 0 else {}
        if not no_token:
            no_token = tokens[1] if len(tokens) > 1 else {}
        
        return {
            'condition_id': clob_data.get('condition_id', ''),
            'question': gamma_market.get('question', 'Unknown'),
            'title': gamma_market.get('question', 'Unknown'),
            'slug': gamma_market.get('slug', ''),
            'active': clob_data.get('active', False),
            'closed': clob_data.get('closed', False),
            'accepting_orders': clob_data.get('accepting_orders', False),
            'outcomes': [yes_token.get('outcome', 'Yes'), no_token.get('outcome', 'No')],
            'yes_token_id': yes_token.get('token_id', ''),
            'no_token_id': no_token.get('token_id', ''),
            'yes_outcome': yes_token.get('outcome', 'Yes'),
            'no_outcome': no_token.get('outcome', 'No'),
            'yes_price': float(yes_token.get('price', 0.5)),
            'no_price': float(no_token.get('price', 0.5)),
            'volume': float(gamma_market.get('volume', 0)),
            'liquidity': float(gamma_market.get('liquidity', 0)),
            'end_time': gamma_market.get('end_date_iso', ''),
        }
    
    async def stop(self):
        """Stop WebSocket scanner"""
        self.connected = False
        logger.info("🔌 WebSocket scanner stopped")


# Test function
async def test_websocket():
    """Test WebSocket scanner"""
    
    print("\n🧪 TESTING WEBSOCKET SCANNER")
    print("="*80)
    
    async def on_market(market):
        print(f"\n🎉 MARKET FOUND!")
        print(f"   Question: {market.get('question')}")
        print(f"   Condition ID: {market.get('condition_id')[:30]}...")
        print(f"   YES: ${market.get('yes_price'):.4f}")
        print(f"   NO: ${market.get('no_price'):.4f}")
    
    scanner = WebSocketScanner(on_market_found=on_market)
    
    print("🔌 Starting WebSocket scanner...")
    print("   Will run for 5 minutes or until market found")
    print("   Press Ctrl+C to stop\n")
    
    try:
        await asyncio.wait_for(scanner.start(), timeout=300)
    except asyncio.TimeoutError:
        print("\n⏰ 5 minutes elapsed")
    except KeyboardInterrupt:
        print("\n⚠️  Stopped by user")
    finally:
        await scanner.stop()
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(test_websocket())