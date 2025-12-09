"""
Market Scanner - WORKING VERSION
Based on: https://github.com/Kushak1/polymarket-auto-trade-example
Uses ONLY Gamma API - NO HTML scraping!
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import aiohttp
import asyncio
import time
from typing import Optional, Dict, List
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketScanner:
    """
    Market scanner using Gamma API only
    NO HTML scraping - direct API queries
    """
    
    def __init__(self):
        self.clob_url = "https://clob.polymarket.com/markets"
        self.gamma_url = "https://gamma-api.polymarket.com/markets"
        
        # Cache
        self._last_markets = []
        self._last_check = 0
        self._cache_duration = 10  # 10 seconds cache
    
    # ==========================================
    # MAIN: Find Active Market
    # ==========================================
    
    def find_active_market(self) -> Optional[Dict]:
        """
        Find active BTC 15M market using Gamma API
        
        Strategy (from reference repo):
        1. Query Gamma API for ALL active markets
        2. Filter for BTC + 15-minute keywords
        3. Verify with CLOB API
        4. Return first tradeable market
        """
        try:
            logger.info("🔍 Scanning for active BTC 15-minute market...")
            
            # Step 1: Get all active markets from Gamma
            markets = self._get_active_markets_from_gamma()
            
            if not markets:
                logger.warning("❌ No active markets from Gamma API")
                return None
            
            logger.info(f"✅ Gamma returned {len(markets)} active markets")
            
            # Step 2: Filter for BTC 15M
            btc_markets = self._filter_btc_15min(markets)
            
            if not btc_markets:
                logger.warning("⚠️  No BTC 15-minute markets found")
                return None
            
            logger.info(f"✅ Found {len(btc_markets)} BTC 15M markets")
            
            # Step 3: Verify each with CLOB
            for market in btc_markets:
                condition_id = market.get('condition_id')
                
                if not condition_id:
                    continue
                
                # Get live data from CLOB
                clob_data = self._get_market_from_clob(condition_id)
                
                if not clob_data:
                    continue
                
                # Check if accepting orders
                if self._is_market_tradeable(clob_data):
                    # Build market info
                    market_info = self._build_market_info(market, clob_data)
                    
                    logger.info(f"✅ Found tradeable market!")
                    logger.info(f"   {market_info['question'][:70]}")
                    
                    return market_info
            
            logger.warning("⚠️  No tradeable markets (all pre-trading or closed)")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error scanning: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def find_active_market_async(self) -> Optional[Dict]:
        """Async version"""
        try:
            logger.info("🔍 Scanning for active BTC 15-minute market...")
            
            # Get markets
            markets = await self._get_active_markets_from_gamma_async()
            
            if not markets:
                logger.warning("❌ No active markets from Gamma API")
                return None
            
            logger.info(f"✅ Gamma returned {len(markets)} active markets")
            
            # Filter
            btc_markets = self._filter_btc_15min(markets)
            
            if not btc_markets:
                logger.warning("⚠️  No BTC 15-minute markets found")
                return None
            
            logger.info(f"✅ Found {len(btc_markets)} BTC 15M markets")
            
            # Verify with CLOB
            async with aiohttp.ClientSession() as session:
                for market in btc_markets:
                    condition_id = market.get('condition_id')
                    
                    if not condition_id:
                        continue
                    
                    clob_data = await self._get_market_from_clob_async(session, condition_id)
                    
                    if not clob_data:
                        continue
                    
                    if self._is_market_tradeable(clob_data):
                        market_info = self._build_market_info(market, clob_data)
                        
                        logger.info(f"✅ Found tradeable market!")
                        logger.info(f"   {market_info['question'][:70]}")
                        
                        return market_info
            
            logger.warning("⚠️  No tradeable markets")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error scanning: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ==========================================
    # Gamma API Methods
    # ==========================================
    
    def _get_active_markets_from_gamma(self) -> List[Dict]:
        """
        Get active markets from Gamma API
        
        Based on reference repo approach
        """
        try:
            # Check cache
            now = time.time()
            if self._last_markets and (now - self._last_check) < self._cache_duration:
                return self._last_markets
            
            # Query Gamma API
            params = {
                'limit': 100,
                'active': 'true',
                'closed': 'false',
                'order': 'volume24hr'  # Most active first
            }
            
            response = requests.get(
                self.gamma_url,
                params=params,
                timeout=15
            )
            
            if response.status_code != 200:
                logger.error(f"Gamma API error: {response.status_code}")
                return []
            
            markets = response.json()
            
            if not isinstance(markets, list):
                logger.error(f"Unexpected Gamma response type: {type(markets)}")
                return []
            
            # Update cache
            self._last_markets = markets
            self._last_check = now
            
            return markets
            
        except Exception as e:
            logger.error(f"Error fetching from Gamma: {e}")
            return []
    
    async def _get_active_markets_from_gamma_async(self) -> List[Dict]:
        """Async version"""
        try:
            # Check cache
            now = time.time()
            if self._last_markets and (now - self._last_check) < self._cache_duration:
                return self._last_markets
            
            params = {
                'limit': 100,
                'active': 'true',
                'closed': 'false',
                'order': 'volume24hr'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.gamma_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status != 200:
                        logger.error(f"Gamma API error: {response.status}")
                        return []
                    
                    markets = await response.json()
                    
                    if not isinstance(markets, list):
                        return []
                    
                    # Update cache
                    self._last_markets = markets
                    self._last_check = now
                    
                    return markets
        
        except Exception as e:
            logger.error(f"Error fetching from Gamma: {e}")
            return []
    
    def _filter_btc_15min(self, markets: List[Dict]) -> List[Dict]:
        """
        Filter for BTC 15-minute markets
        
        Based on reference repo logic
        """
        filtered = []
        
        for market in markets:
            question = market.get('question', '').lower()
            
            # Must contain BTC
            has_btc = any(kw in question for kw in ['btc', 'bitcoin'])
            
            # Must contain 15-minute indicator
            has_15m = any(kw in question for kw in [
                '15 minute',
                '15min',
                '15-minute',
                '15 min',
                '15m'
            ])
            
            # Optional: Must be "up or down" type
            is_updown = any(kw in question for kw in [
                'up or down',
                'higher or lower',
                'up/down'
            ])
            
            if has_btc and has_15m:
                filtered.append(market)
        
        return filtered
    
    # ==========================================
    # CLOB API Methods
    # ==========================================
    
    def _get_market_from_clob(self, condition_id: str) -> Optional[Dict]:
        """Get market from CLOB API"""
        try:
            params = {'condition_id': condition_id}
            
            response = requests.get(
                self.clob_url,
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # CLOB can return dict with 'data' or list
            if isinstance(data, dict) and 'data' in data:
                markets = data['data']
            else:
                markets = data if isinstance(data, list) else []
            
            return markets[0] if markets else None
            
        except Exception as e:
            logger.debug(f"CLOB error: {e}")
            return None
    
    async def _get_market_from_clob_async(
        self,
        session: aiohttp.ClientSession,
        condition_id: str
    ) -> Optional[Dict]:
        """Async version"""
        try:
            params = {'condition_id': condition_id}
            
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
            logger.debug(f"CLOB error: {e}")
            return None
    
    def _is_market_tradeable(self, clob_data: Dict) -> bool:
        """
        Check if market is tradeable
        
        Based on reference repo criteria
        """
        # Must be active
        if not clob_data.get('active', False):
            return False
        
        # Must not be closed
        if clob_data.get('closed', False):
            return False
        
        # Must accept orders
        if not clob_data.get('accepting_orders', False):
            return False
        
        # Must have exactly 2 tokens
        tokens = clob_data.get('tokens', [])
        if len(tokens) != 2:
            return False
        
        return True
    
    def _build_market_info(self, gamma_data: Dict, clob_data: Dict) -> Dict:
        """Build standardized market info"""
        tokens = clob_data.get('tokens', [])
        
        # Identify YES/NO tokens
        yes_token = None
        no_token = None
        
        for token in tokens:
            outcome = token.get('outcome', '').upper()
            
            if any(kw in outcome for kw in ['YES', 'UP', 'HIGHER']):
                yes_token = token
            elif any(kw in outcome for kw in ['NO', 'DOWN', 'LOWER']):
                no_token = token
        
        # Fallback
        if not yes_token:
            yes_token = tokens[0] if len(tokens) > 0 else {}
        if not no_token:
            no_token = tokens[1] if len(tokens) > 1 else {}
        
        return {
            'condition_id': clob_data.get('condition_id', ''),
            'question': gamma_data.get('question', 'Unknown'),
            'title': gamma_data.get('question', 'Unknown'),
            'slug': gamma_data.get('slug', ''),
            'active': clob_data.get('active', False),
            'closed': clob_data.get('closed', False),
            'accepting_orders': clob_data.get('accepting_orders', False),
            'outcomes': [
                yes_token.get('outcome', 'Yes'),
                no_token.get('outcome', 'No')
            ],
            'yes_token_id': yes_token.get('token_id', ''),
            'no_token_id': no_token.get('token_id', ''),
            'yes_outcome': yes_token.get('outcome', 'Yes'),
            'no_outcome': no_token.get('outcome', 'No'),
            'yes_price': float(yes_token.get('price', 0.5)),
            'no_price': float(no_token.get('price', 0.5)),
            'volume': float(gamma_data.get('volume', 0)),
            'liquidity': float(gamma_data.get('liquidity', 0)),
            'end_time': gamma_data.get('end_date_iso', ''),
        }
    
    # ==========================================
    # Helper Methods
    # ==========================================
    
    def get_market_prices(self, condition_id: str) -> Optional[Dict]:
        """Get current prices"""
        market = self._get_market_from_clob(condition_id)
        
        if not market:
            return None
        
        tokens = market.get('tokens', [])
        prices = {}
        
        for token in tokens:
            outcome = token.get('outcome', '').upper()
            price = float(token.get('price', 0))
            
            if any(kw in outcome for kw in ['YES', 'UP', 'HIGHER']):
                prices['YES'] = price
            elif any(kw in outcome for kw in ['NO', 'DOWN', 'LOWER']):
                prices['NO'] = price
        
        return prices if prices else None
    
    async def get_market_prices_async(self, condition_id: str) -> Optional[Dict]:
        """Async version"""
        async with aiohttp.ClientSession() as session:
            market = await self._get_market_from_clob_async(session, condition_id)
        
        if not market:
            return None
        
        tokens = market.get('tokens', [])
        prices = {}
        
        for token in tokens:
            outcome = token.get('outcome', '').upper()
            price = float(token.get('price', 0))
            
            if any(kw in outcome for kw in ['YES', 'UP', 'HIGHER']):
                prices['YES'] = price
            elif any(kw in outcome for kw in ['NO', 'DOWN', 'LOWER']):
                prices['NO'] = price
        
        return prices if prices else None
    
    def wait_for_market(
        self,
        max_wait: int = 300,
        check_interval: int = 30
    ) -> Optional[Dict]:
        """Wait for market"""
        start_time = time.time()
        check_count = 0
        
        while (time.time() - start_time) < max_wait:
            check_count += 1
            
            logger.info(f"Check #{check_count}: Scanning...")
            
            market = self.find_active_market()
            
            if market:
                return market
            
            logger.info(f"   No market, retrying in {check_interval}s...")
            time.sleep(check_interval)
        
        return None


# Test function
def test_scanner():
    """Test the scanner"""
    
    print("\n🧪 TESTING GAMMA API SCANNER")
    print("="*80)
    
    scanner = MarketScanner()
    
    print("\n1️⃣ Fetching active markets from Gamma...")
    markets = scanner._get_active_markets_from_gamma()
    print(f"   Found {len(markets)} active markets")
    
    if markets:
        print(f"\n   Sample markets:")
        for i, m in enumerate(markets[:5], 1):
            print(f"   {i}. {m.get('question', 'N/A')[:70]}")
    
    print("\n2️⃣ Filtering for BTC 15M...")
    btc_markets = scanner._filter_btc_15min(markets)
    print(f"   Found {len(btc_markets)} BTC 15M markets")
    
    if btc_markets:
        print(f"\n   BTC 15M markets:")
        for i, m in enumerate(btc_markets, 1):
            print(f"   {i}. {m.get('question')}")
            print(f"      Condition ID: {m.get('condition_id', 'N/A')[:30]}...")
    
    print("\n3️⃣ Finding tradeable market...")
    market = scanner.find_active_market()
    
    if market:
        print(f"\n✅ FOUND TRADEABLE MARKET!")
        print(f"   Question: {market['question']}")
        print(f"   Condition ID: {market['condition_id'][:30]}...")
        print(f"   YES: ${market['yes_price']:.4f}")
        print(f"   NO: ${market['no_price']:.4f}")
        print(f"   Accepting Orders: {market['accepting_orders']}")
    else:
        print(f"\n⚠️  No tradeable market found")
        print(f"   Markets may be pre-trading or between rounds")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    test_scanner()