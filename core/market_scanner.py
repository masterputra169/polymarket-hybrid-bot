"""
Market Scanner V5 - TIMESTAMP-BASED SLUG DISCOVERY
BTC 15-minute markets use slug format: btc-updown-15m-{unix_timestamp}

Example: https://polymarket.com/event/btc-updown-15m-1765269000
- 1765269000 = Unix timestamp
- Market runs every 15 minutes (900 seconds)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import aiohttp
import asyncio
import time
from typing import Optional, Dict, List
from datetime import datetime, timezone
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketScanner:
    """
    Market scanner using TIMESTAMP-BASED slugs
    
    BTC/ETH 15-min markets use: {asset}-updown-15m-{timestamp}
    Where timestamp is Unix time rounded to 15-minute intervals
    """
    
    def __init__(self, asset: str = "BTC", duration: int = 15):
        self.asset = asset.upper()
        self.duration = duration
        self.interval_seconds = duration * 60  # 900 for 15min
        
        # API endpoints
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.clob_url = "https://clob.polymarket.com/markets"
        
        # Slug patterns - TIMESTAMP BASED
        self.slug_patterns = {
            'BTC': 'btc-updown-15m-',
            'ETH': 'eth-updown-15m-',
            'SOL': 'sol-updown-15m-',
        }
        
        logger.info(f"📡 Scanner V5 initialized for {self.asset} {self.duration}min markets")
        logger.info(f"   Slug pattern: {self.slug_patterns.get(self.asset, 'unknown')}<timestamp>")
    
    def _get_market_timestamps(self) -> List[int]:
        """
        Calculate timestamps for current and nearby market intervals
        
        Markets run every 15 minutes, so we calculate:
        - Current interval
        - Previous interval (might still be settling)
        - Next interval (might be in pre-trading)
        - And a few more for safety
        """
        now = int(time.time())
        interval = self.interval_seconds
        
        # Round down to current interval
        current = (now // interval) * interval
        
        # Generate timestamps for nearby intervals
        timestamps = []
        
        # Previous 2 intervals (might still be active or settling)
        for i in range(-2, 0):
            timestamps.append(current + (i * interval))
        
        # Current interval
        timestamps.append(current)
        
        # Next 2 intervals (pre-trading)
        for i in range(1, 3):
            timestamps.append(current + (i * interval))
        
        return timestamps
    
    def _timestamp_to_readable(self, ts: int) -> str:
        """Convert timestamp to readable format"""
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M UTC')
    
    # ==========================================
    # MAIN: Find Active Market
    # ==========================================
    
    def find_active_market(self) -> Optional[Dict]:
        """
        Find active market using timestamp-based slug discovery
        """
        now = int(time.time())
        now_readable = self._timestamp_to_readable(now)
        
        logger.info(f"🔍 Scanning for {self.asset} {self.duration}min market...")
        logger.info(f"   Current time: {now_readable} (ts: {now})")
        
        # Method 1: Timestamp-based slug lookup (MOST RELIABLE)
        market = self._find_by_timestamp_slug()
        if market:
            return market
        
        # Method 2: Fallback - search events API
        market = self._find_by_events_api()
        if market:
            return market
        
        # Method 3: Direct CLOB check
        market = self._find_by_clob_direct()
        if market:
            return market
        
        logger.warning("⚠️ No active market found")
        return None
    
    async def find_active_market_async(self) -> Optional[Dict]:
        """Async version"""
        now = int(time.time())
        logger.info(f"🔍 Scanning for {self.asset} {self.duration}min market...")
        logger.info(f"   Current time: {self._timestamp_to_readable(now)}")
        
        market = await self._find_by_timestamp_slug_async()
        if market:
            return market
        
        market = await self._find_by_events_api_async()
        if market:
            return market
        
        market = await self._find_by_clob_direct_async()
        if market:
            return market
        
        logger.warning("⚠️ No active market found")
        return None
    
    # ==========================================
    # METHOD 1: Timestamp-Based Slug Lookup
    # ==========================================
    
    def _find_by_timestamp_slug(self) -> Optional[Dict]:
        """
        Find market by constructing slug from timestamps
        
        Slug format: btc-updown-15m-{timestamp}
        """
        slug_prefix = self.slug_patterns.get(self.asset)
        
        if not slug_prefix:
            logger.warning(f"No slug pattern for {self.asset}")
            return None
        
        timestamps = self._get_market_timestamps()
        
        logger.info(f"   Method 1: Timestamp slug lookup")
        logger.info(f"   Trying {len(timestamps)} timestamps...")
        
        for ts in timestamps:
            slug = f"{slug_prefix}{ts}"
            readable = self._timestamp_to_readable(ts)
            
            logger.debug(f"   Trying: {slug} ({readable})")
            
            # Fetch event by slug
            event = self._get_event_by_slug(slug)
            
            if event:
                logger.info(f"   ✅ Found event: {slug}")
                logger.info(f"      Time: {readable}")
                
                # Get market from event
                markets = event.get('markets', [])
                
                if markets:
                    market = markets[0]
                    condition_id = market.get('condition_id') or market.get('conditionId')
                    
                    if condition_id:
                        # Verify with CLOB
                        clob_data = self._get_market_from_clob(condition_id)
                        
                        if clob_data:
                            active = clob_data.get('active', False)
                            closed = clob_data.get('closed', False)
                            accepting = clob_data.get('accepting_orders', False)
                            
                            logger.info(f"      CLOB status: active={active}, closed={closed}, accepting={accepting}")
                            
                            if self._is_market_tradeable(clob_data):
                                logger.info(f"   ✅ TRADEABLE MARKET FOUND!")
                                return self._build_market_info(market, clob_data, event)
                            else:
                                logger.info(f"      ⏭️ Not accepting orders yet")
        
        logger.info(f"   No tradeable market via timestamp slugs")
        return None
    
    async def _find_by_timestamp_slug_async(self) -> Optional[Dict]:
        """Async version"""
        slug_prefix = self.slug_patterns.get(self.asset)
        
        if not slug_prefix:
            return None
        
        timestamps = self._get_market_timestamps()
        
        logger.info(f"   Method 1: Timestamp slug lookup")
        logger.info(f"   Trying {len(timestamps)} timestamps...")
        
        async with aiohttp.ClientSession() as session:
            for ts in timestamps:
                slug = f"{slug_prefix}{ts}"
                readable = self._timestamp_to_readable(ts)
                
                event = await self._get_event_by_slug_async(session, slug)
                
                if event:
                    logger.info(f"   ✅ Found: {slug} ({readable})")
                    
                    markets = event.get('markets', [])
                    
                    if markets:
                        market = markets[0]
                        condition_id = market.get('condition_id') or market.get('conditionId')
                        
                        if condition_id:
                            clob_data = await self._get_market_from_clob_async(session, condition_id)
                            
                            if clob_data:
                                accepting = clob_data.get('accepting_orders', False)
                                logger.info(f"      accepting_orders={accepting}")
                                
                                if self._is_market_tradeable(clob_data):
                                    logger.info(f"   ✅ TRADEABLE!")
                                    return self._build_market_info(market, clob_data, event)
        
        return None
    
    def _get_event_by_slug(self, slug: str) -> Optional[Dict]:
        """Get event from Gamma API by slug"""
        try:
            # Try multiple endpoint formats
            endpoints = [
                f"{self.gamma_url}/events/slug/{slug}",
                f"{self.gamma_url}/events/{slug}",
            ]
            
            for url in endpoints:
                try:
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Could be direct event or list
                        if isinstance(data, dict):
                            return data
                        elif isinstance(data, list) and data:
                            return data[0]
                            
                except requests.exceptions.RequestException:
                    continue
            
            return None
            
        except Exception as e:
            logger.debug(f"Slug lookup error: {e}")
            return None
    
    async def _get_event_by_slug_async(
        self, 
        session: aiohttp.ClientSession, 
        slug: str
    ) -> Optional[Dict]:
        """Async version"""
        try:
            endpoints = [
                f"{self.gamma_url}/events/slug/{slug}",
                f"{self.gamma_url}/events/{slug}",
            ]
            
            for url in endpoints:
                try:
                    async with session.get(
                        url, 
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if isinstance(data, dict):
                                return data
                            elif isinstance(data, list) and data:
                                return data[0]
                except:
                    continue
            
            return None
            
        except:
            return None
    
    # ==========================================
    # METHOD 2: Events API Search
    # ==========================================
    
    def _find_by_events_api(self) -> Optional[Dict]:
        """Fallback: search events API"""
        logger.info(f"   Method 2: Events API search...")
        
        try:
            url = f"{self.gamma_url}/events"
            params = {
                'limit': 50,
                'closed': 'false',
                'active': 'true'
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                return None
            
            events = response.json()
            
            if not isinstance(events, list):
                return None
            
            # Look for BTC updown markets
            asset_lower = self.asset.lower()
            
            for event in events:
                slug = event.get('slug', '').lower()
                title = event.get('title', '').lower()
                
                # Check slug pattern
                is_match = (
                    f"{asset_lower}-updown" in slug or
                    f"{asset_lower} up or down" in title or
                    (asset_lower in slug and 'updown' in slug)
                )
                
                if is_match:
                    markets = event.get('markets', [])
                    
                    if markets:
                        market = markets[0]
                        condition_id = market.get('condition_id') or market.get('conditionId')
                        
                        if condition_id:
                            clob_data = self._get_market_from_clob(condition_id)
                            
                            if clob_data and self._is_market_tradeable(clob_data):
                                logger.info(f"   ✅ Found via events API: {event.get('slug')}")
                                return self._build_market_info(market, clob_data, event)
            
            return None
            
        except Exception as e:
            logger.error(f"Events API error: {e}")
            return None
    
    async def _find_by_events_api_async(self) -> Optional[Dict]:
        """Async version"""
        logger.info(f"   Method 2: Events API search...")
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.gamma_url}/events"
                params = {
                    'limit': 50,
                    'closed': 'false',
                    'active': 'true'
                }
                
                async with session.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status != 200:
                        return None
                    
                    events = await response.json()
                    
                    if not isinstance(events, list):
                        return None
                    
                    asset_lower = self.asset.lower()
                    
                    for event in events:
                        slug = event.get('slug', '').lower()
                        title = event.get('title', '').lower()
                        
                        is_match = (
                            f"{asset_lower}-updown" in slug or
                            f"{asset_lower} up or down" in title
                        )
                        
                        if is_match:
                            markets = event.get('markets', [])
                            
                            if markets:
                                market = markets[0]
                                condition_id = market.get('condition_id') or market.get('conditionId')
                                
                                if condition_id:
                                    clob_data = await self._get_market_from_clob_async(session, condition_id)
                                    
                                    if clob_data and self._is_market_tradeable(clob_data):
                                        logger.info(f"   ✅ Found via events API")
                                        return self._build_market_info(market, clob_data, event)
                    
                    return None
                    
        except Exception as e:
            logger.error(f"Async events API error: {e}")
            return None
    
    # ==========================================
    # METHOD 3: Direct CLOB Check
    # ==========================================
    
    def _find_by_clob_direct(self) -> Optional[Dict]:
        """Direct CLOB API check for any accepting market"""
        logger.info(f"   Method 3: Direct CLOB check...")
        
        try:
            url = f"{self.gamma_url}/markets"
            params = {
                'limit': 100,
                'closed': 'false',
                'active': 'true'
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                return None
            
            markets = response.json()
            
            if not isinstance(markets, list):
                return None
            
            asset_lower = self.asset.lower()
            
            for market in markets:
                slug = market.get('slug', '').lower()
                question = market.get('question', '').lower()
                
                is_match = (
                    f"{asset_lower}-updown" in slug or
                    f"{asset_lower}" in question and 'up or down' in question
                )
                
                if is_match:
                    condition_id = market.get('condition_id') or market.get('conditionId')
                    
                    if condition_id:
                        clob_data = self._get_market_from_clob(condition_id)
                        
                        if clob_data and self._is_market_tradeable(clob_data):
                            logger.info(f"   ✅ Found via CLOB: {slug}")
                            return self._build_market_info(market, clob_data)
            
            return None
            
        except Exception as e:
            logger.error(f"CLOB check error: {e}")
            return None
    
    async def _find_by_clob_direct_async(self) -> Optional[Dict]:
        """Async version"""
        logger.info(f"   Method 3: Direct CLOB check...")
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.gamma_url}/markets"
                params = {
                    'limit': 100,
                    'closed': 'false',
                    'active': 'true'
                }
                
                async with session.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status != 200:
                        return None
                    
                    markets = await response.json()
                    
                    if not isinstance(markets, list):
                        return None
                    
                    asset_lower = self.asset.lower()
                    
                    for market in markets:
                        slug = market.get('slug', '').lower()
                        question = market.get('question', '').lower()
                        
                        is_match = (
                            f"{asset_lower}-updown" in slug or
                            (asset_lower in question and 'up or down' in question)
                        )
                        
                        if is_match:
                            condition_id = market.get('condition_id') or market.get('conditionId')
                            
                            if condition_id:
                                clob_data = await self._get_market_from_clob_async(session, condition_id)
                                
                                if clob_data and self._is_market_tradeable(clob_data):
                                    logger.info(f"   ✅ Found via CLOB")
                                    return self._build_market_info(market, clob_data)
                    
                    return None
                    
        except Exception as e:
            logger.error(f"Async CLOB error: {e}")
            return None
    
    # ==========================================
    # CLOB API Methods
    # ==========================================
    
    def _get_market_from_clob(self, condition_id: str) -> Optional[Dict]:
        """Get market from CLOB API"""
        try:
            params = {'condition_id': condition_id}
            response = requests.get(self.clob_url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if isinstance(data, dict) and 'data' in data:
                markets = data['data']
            else:
                markets = data if isinstance(data, list) else []
            
            return markets[0] if markets else None
            
        except:
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
                
        except:
            return None
    
    def _is_market_tradeable(self, clob_data: Dict) -> bool:
        """Check if market can be traded"""
        return (
            clob_data.get('active', False) and
            not clob_data.get('closed', False) and
            clob_data.get('accepting_orders', False) and
            len(clob_data.get('tokens', [])) == 2
        )
    
    def _build_market_info(
        self, 
        gamma_data: Dict, 
        clob_data: Dict,
        event_data: Optional[Dict] = None
    ) -> Dict:
        """Build standardized market info"""
        tokens = clob_data.get('tokens', [])
        
        yes_token = no_token = None
        
        for token in tokens:
            outcome = token.get('outcome', '').upper()
            
            if any(kw in outcome for kw in ['YES', 'UP', 'HIGHER']):
                yes_token = token
            elif any(kw in outcome for kw in ['NO', 'DOWN', 'LOWER']):
                no_token = token
        
        if not yes_token:
            yes_token = tokens[0] if tokens else {}
        if not no_token:
            no_token = tokens[1] if len(tokens) > 1 else {}
        
        question = (
            gamma_data.get('question') or
            gamma_data.get('title') or
            (event_data.get('title') if event_data else None) or
            'Unknown'
        )
        
        end_time = (
            gamma_data.get('end_date_iso') or
            gamma_data.get('endDate') or
            clob_data.get('end_date_iso') or
            (event_data.get('endDate') if event_data else None) or
            ''
        )
        
        return {
            'condition_id': clob_data.get('condition_id', ''),
            'question': question,
            'title': question,
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
            'end_time': end_time,
        }
    
    # ==========================================
    # Utility Methods
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
            
            if any(kw in outcome for kw in ['YES', 'UP']):
                prices['YES'] = price
            elif any(kw in outcome for kw in ['NO', 'DOWN']):
                prices['NO'] = price
        
        return prices if prices else None
    
    def wait_for_market(
        self,
        max_wait: int = 300,
        check_interval: int = 15
    ) -> Optional[Dict]:
        """Wait for market to become available"""
        start_time = time.time()
        check_count = 0
        
        while (time.time() - start_time) < max_wait:
            check_count += 1
            
            logger.info(f"Check #{check_count}...")
            
            market = self.find_active_market()
            
            if market:
                return market
            
            logger.info(f"   Retrying in {check_interval}s...")
            time.sleep(check_interval)
        
        return None


# ==========================================
# Test Function
# ==========================================

def test_scanner():
    print("\n" + "="*80)
    print("🧪 TESTING MARKET SCANNER V5 (Timestamp Slug)")
    print("="*80)
    
    scanner = MarketScanner(asset="BTC", duration=15)
    
    # Show current time and timestamps
    now = int(time.time())
    print(f"\n📅 Current Time:")
    print(f"   Unix timestamp: {now}")
    print(f"   UTC: {scanner._timestamp_to_readable(now)}")
    print(f"   Local: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show timestamps being checked
    print(f"\n1️⃣ Timestamps to check:")
    timestamps = scanner._get_market_timestamps()
    
    for ts in timestamps:
        slug = f"btc-updown-15m-{ts}"
        readable = scanner._timestamp_to_readable(ts)
        print(f"   {slug}")
        print(f"      → {readable}")
    
    # Test specific slug from user's URL
    print(f"\n2️⃣ Testing user's slug: btc-updown-15m-1765269000")
    event = scanner._get_event_by_slug("btc-updown-15m-1765269000")
    
    if event:
        print(f"   ✅ Event found!")
        print(f"   Title: {event.get('title', 'N/A')}")
        
        markets = event.get('markets', [])
        if markets:
            market = markets[0]
            condition_id = market.get('condition_id') or market.get('conditionId')
            print(f"   Condition ID: {condition_id[:30] if condition_id else 'N/A'}...")
            
            if condition_id:
                clob = scanner._get_market_from_clob(condition_id)
                if clob:
                    print(f"   CLOB Status:")
                    print(f"      active: {clob.get('active')}")
                    print(f"      closed: {clob.get('closed')}")
                    print(f"      accepting_orders: {clob.get('accepting_orders')}")
    else:
        print(f"   ❌ Event not found via API")
    
    # Test main method
    print(f"\n3️⃣ Testing find_active_market()...")
    market = scanner.find_active_market()
    
    if market:
        print(f"\n✅ MARKET FOUND!")
        print(f"   Question: {market['question']}")
        print(f"   Slug: {market['slug']}")
        print(f"   YES: ${market['yes_price']:.4f}")
        print(f"   NO: ${market['no_price']:.4f}")
        print(f"   Accepting: {market['accepting_orders']}")
    else:
        print(f"\n⚠️ No active market found")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    test_scanner()