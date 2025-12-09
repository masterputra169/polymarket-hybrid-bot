"""
Market Scanner V6 - TIMEZONE-AWARE VERSION
Properly handles WIB → UTC conversion for accurate market discovery

FIXES:
- Uses UTC time for all calculations
- Looks ahead for future markets (not just past)
- Better handling of market settlement times
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import aiohttp
import asyncio
import time
from typing import Optional, Dict, List
from datetime import datetime, timezone, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketScanner:
    """
    Market scanner with proper timezone handling
    Converts local time → UTC for accurate market discovery
    """
    
    def __init__(self, asset: str = "BTC", duration: int = 15):
        self.asset = asset.upper()
        self.duration = duration
        self.interval_seconds = duration * 60  # 900 for 15min
        
        # API endpoints
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.clob_url = "https://clob.polymarket.com/markets"
        
        # Slug patterns
        self.slug_patterns = {
            'BTC': 'btc-updown-15m-',
            'ETH': 'eth-updown-15m-',
            'SOL': 'sol-updown-15m-',
        }
        
        logger.info(f"📡 Scanner V6 (Timezone-Aware) initialized")
        logger.info(f"   Asset: {self.asset} | Duration: {self.duration}min")
        logger.info(f"   Slug: {self.slug_patterns.get(self.asset, 'unknown')}<timestamp>")
    
    def _get_utc_now(self) -> int:
        """Get current UTC timestamp"""
        return int(datetime.now(timezone.utc).timestamp())
    
    def _get_market_timestamps(self, look_back: int = 2, look_ahead: int = 3) -> List[int]:
        """
        Calculate market timestamps in UTC
        
        Args:
            look_back: How many past intervals to check
            look_ahead: How many future intervals to check
        
        Returns:
            List of Unix timestamps
        """
        now_utc = self._get_utc_now()
        interval = self.interval_seconds
        
        # Round down to current interval
        current = (now_utc // interval) * interval
        
        timestamps = []
        
        # Past intervals (might still be settling)
        for i in range(-look_back, 0):
            timestamps.append(current + (i * interval))
        
        # Current interval
        timestamps.append(current)
        
        # Future intervals (pre-trading phase)
        for i in range(1, look_ahead + 1):
            timestamps.append(current + (i * interval))
        
        return timestamps
    
    def _timestamp_to_readable(self, ts: int) -> str:
        """Convert Unix timestamp to readable UTC time"""
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M UTC')
    
    def _calculate_time_until_market(self, market_ts: int) -> int:
        """Calculate seconds until market starts"""
        now = self._get_utc_now()
        return market_ts - now
    
    # ==========================================
    # MAIN: Find Active Market
    # ==========================================
    
    def find_active_market(self) -> Optional[Dict]:
        """Find active market with timezone-aware logic"""
        
        now = self._get_utc_now()
        now_readable = self._timestamp_to_readable(now)
        
        logger.info(f"🔍 Scanning for {self.asset} {self.duration}min market...")
        logger.info(f"   Current UTC: {now_readable} (ts: {now})")
        
        # Show local time for reference
        local_dt = datetime.now()
        logger.info(f"   Your local time: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Method 1: Timestamp-based slug lookup
        market = self._find_by_timestamp_slug()
        if market:
            return market
        
        # Method 2: Events API search
        market = self._find_by_events_api()
        if market:
            return market
        
        # Method 3: Direct CLOB check
        market = self._find_by_clob_direct()
        if market:
            return market
        
        logger.warning("⚠️ No active market found")
        logger.info("💡 Markets typically available during:")
        logger.info("   - US trading hours (14:30-21:00 UTC)")
        logger.info("   - High volatility periods")
        
        return None
    
    async def find_active_market_async(self) -> Optional[Dict]:
        """Async version"""
        now = self._get_utc_now()
        logger.info(f"🔍 Scanning (UTC: {self._timestamp_to_readable(now)})...")
        
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
    # METHOD 1: Timestamp Slug Discovery
    # ==========================================
    
    def _find_by_timestamp_slug(self) -> Optional[Dict]:
        """Find market by timestamp-based slug"""
        
        slug_prefix = self.slug_patterns.get(self.asset)
        if not slug_prefix:
            return None
        
        timestamps = self._get_market_timestamps(look_back=2, look_ahead=3)
        
        logger.info(f"   Method 1: Checking {len(timestamps)} timestamps...")
        
        for ts in timestamps:
            slug = f"{slug_prefix}{ts}"
            readable = self._timestamp_to_readable(ts)
            
            # Show what we're checking
            time_diff = self._calculate_time_until_market(ts)
            
            if time_diff > 0:
                logger.debug(f"   Trying: {slug} (starts in {time_diff}s)")
            else:
                logger.debug(f"   Trying: {slug} (started {abs(time_diff)}s ago)")
            
            event = self._get_event_by_slug(slug)
            
            if event:
                logger.info(f"   ✅ Found: {slug}")
                logger.info(f"      Time: {readable}")
                
                markets = event.get('markets', [])
                
                if markets:
                    market = markets[0]
                    condition_id = market.get('condition_id') or market.get('conditionId')
                    
                    if condition_id:
                        clob_data = self._get_market_from_clob(condition_id)
                        
                        if clob_data:
                            # Check status
                            active = clob_data.get('active', False)
                            closed = clob_data.get('closed', False)
                            accepting = clob_data.get('accepting_orders', False)
                            
                            logger.info(f"      Status: active={active}, closed={closed}, accepting={accepting}")
                            
                            # IMPORTANT: Only return if accepting orders
                            if accepting and not closed:
                                logger.info(f"   ✅ TRADEABLE MARKET!")
                                return self._build_market_info(market, clob_data, event)
                            else:
                                if closed:
                                    logger.debug(f"      ⏭️ Market closed/settled")
                                else:
                                    logger.debug(f"      ⏭️ Not accepting orders yet")
        
        logger.info(f"   No tradeable markets in timestamp range")
        return None
    
    async def _find_by_timestamp_slug_async(self) -> Optional[Dict]:
        """Async version"""
        slug_prefix = self.slug_patterns.get(self.asset)
        if not slug_prefix:
            return None
        
        timestamps = self._get_market_timestamps(look_back=2, look_ahead=3)
        
        logger.info(f"   Method 1: Checking {len(timestamps)} timestamps...")
        
        async with aiohttp.ClientSession() as session:
            for ts in timestamps:
                slug = f"{slug_prefix}{ts}"
                
                event = await self._get_event_by_slug_async(session, slug)
                
                if event:
                    logger.info(f"   ✅ Found: {slug}")
                    
                    markets = event.get('markets', [])
                    
                    if markets:
                        market = markets[0]
                        condition_id = market.get('condition_id') or market.get('conditionId')
                        
                        if condition_id:
                            clob_data = await self._get_market_from_clob_async(session, condition_id)
                            
                            if clob_data:
                                accepting = clob_data.get('accepting_orders', False)
                                closed = clob_data.get('closed', False)
                                
                                if accepting and not closed:
                                    logger.info(f"   ✅ TRADEABLE!")
                                    return self._build_market_info(market, clob_data, event)
        
        return None
    
    # ==========================================
    # METHOD 2: Events API
    # ==========================================
    
    def _find_by_events_api(self) -> Optional[Dict]:
        """Search via Events API"""
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
            
            asset_lower = self.asset.lower()
            
            for event in events:
                slug = event.get('slug', '').lower()
                
                if f"{asset_lower}-updown" in slug:
                    markets = event.get('markets', [])
                    
                    if markets:
                        market = markets[0]
                        condition_id = market.get('condition_id') or market.get('conditionId')
                        
                        if condition_id:
                            clob_data = self._get_market_from_clob(condition_id)
                            
                            if clob_data and self._is_market_tradeable(clob_data):
                                logger.info(f"   ✅ Found via Events API")
                                return self._build_market_info(market, clob_data, event)
            
            return None
            
        except Exception as e:
            logger.error(f"Events API error: {e}")
            return None
    
    async def _find_by_events_api_async(self) -> Optional[Dict]:
        """Async version"""
        logger.info(f"   Method 2: Events API...")
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.gamma_url}/events"
                params = {'limit': 50, 'closed': 'false', 'active': 'true'}
                
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        return None
                    
                    events = await response.json()
                    
                    if not isinstance(events, list):
                        return None
                    
                    asset_lower = self.asset.lower()
                    
                    for event in events:
                        slug = event.get('slug', '').lower()
                        
                        if f"{asset_lower}-updown" in slug:
                            markets = event.get('markets', [])
                            
                            if markets:
                                market = markets[0]
                                condition_id = market.get('condition_id') or market.get('conditionId')
                                
                                if condition_id:
                                    clob_data = await self._get_market_from_clob_async(session, condition_id)
                                    
                                    if clob_data and self._is_market_tradeable(clob_data):
                                        logger.info(f"   ✅ Found via Events")
                                        return self._build_market_info(market, clob_data, event)
                    
                    return None
        except Exception as e:
            logger.error(f"Async events error: {e}")
            return None
    
    # ==========================================
    # METHOD 3: Direct CLOB
    # ==========================================
    
    def _find_by_clob_direct(self) -> Optional[Dict]:
        """Direct CLOB check"""
        logger.info(f"   Method 3: Direct CLOB...")
        
        try:
            url = f"{self.gamma_url}/markets"
            params = {'limit': 100, 'closed': 'false', 'active': 'true'}
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                return None
            
            markets = response.json()
            
            if not isinstance(markets, list):
                return None
            
            asset_lower = self.asset.lower()
            
            for market in markets:
                slug = market.get('slug', '').lower()
                
                if f"{asset_lower}-updown" in slug:
                    condition_id = market.get('condition_id') or market.get('conditionId')
                    
                    if condition_id:
                        clob_data = self._get_market_from_clob(condition_id)
                        
                        if clob_data and self._is_market_tradeable(clob_data):
                            logger.info(f"   ✅ Found via CLOB")
                            return self._build_market_info(market, clob_data)
            
            return None
            
        except Exception as e:
            logger.error(f"CLOB error: {e}")
            return None
    
    async def _find_by_clob_direct_async(self) -> Optional[Dict]:
        """Async version"""
        logger.info(f"   Method 3: CLOB...")
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.gamma_url}/markets"
                params = {'limit': 100, 'closed': 'false', 'active': 'true'}
                
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        return None
                    
                    markets = await response.json()
                    
                    if not isinstance(markets, list):
                        return None
                    
                    asset_lower = self.asset.lower()
                    
                    for market in markets:
                        slug = market.get('slug', '').lower()
                        
                        if f"{asset_lower}-updown" in slug:
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
    # Helper Methods
    # ==========================================
    
    def _get_event_by_slug(self, slug: str) -> Optional[Dict]:
        """Get event from Gamma API"""
        try:
            endpoints = [
                f"{self.gamma_url}/events/slug/{slug}",
                f"{self.gamma_url}/events/{slug}",
            ]
            
            for url in endpoints:
                try:
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if isinstance(data, dict):
                            return data
                        elif isinstance(data, list) and data:
                            return data[0]
                except:
                    continue
            
            return None
        except:
            return None
    
    async def _get_event_by_slug_async(self, session: aiohttp.ClientSession, slug: str) -> Optional[Dict]:
        """Async version"""
        try:
            endpoints = [
                f"{self.gamma_url}/events/slug/{slug}",
                f"{self.gamma_url}/events/{slug}",
            ]
            
            for url in endpoints:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
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
    
    async def _get_market_from_clob_async(self, session: aiohttp.ClientSession, condition_id: str) -> Optional[Dict]:
        """Async version"""
        try:
            params = {'condition_id': condition_id}
            
            async with session.get(self.clob_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
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
        """Check if market is tradeable"""
        return (
            clob_data.get('active', False) and
            not clob_data.get('closed', False) and
            clob_data.get('accepting_orders', False) and
            len(clob_data.get('tokens', [])) == 2
        )
    
    def _build_market_info(self, gamma_data: Dict, clob_data: Dict, event_data: Optional[Dict] = None) -> Dict:
        """Build market info dict"""
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


# ==========================================
# Test Function
# ==========================================

def test_scanner():
    """Test scanner with timezone awareness"""
    
    print("\n" + "="*80)
    print("🧪 TESTING MARKET SCANNER V6 (Timezone-Aware)")
    print("="*80)
    
    scanner = MarketScanner(asset="BTC", duration=15)
    
    # Show time info
    now_utc = scanner._get_utc_now()
    now_local = datetime.now()
    
    print(f"\n🕐 Time Information:")
    print(f"   UTC Now:   {scanner._timestamp_to_readable(now_utc)}")
    print(f"   Local Now: {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   UTC Offset: {now_local.strftime('%z')}")
    
    # Show timestamps being checked
    print(f"\n🔍 Timestamps to check:")
    timestamps = scanner._get_market_timestamps(look_back=2, look_ahead=3)
    
    for ts in timestamps:
        readable = scanner._timestamp_to_readable(ts)
        diff = ts - now_utc
        
        if diff > 0:
            status = f"(starts in {diff}s)"
        elif diff > -900:
            status = f"(active, {-diff}s elapsed)"
        else:
            status = f"(ended {-diff}s ago)"
        
        print(f"   {readable} {status}")
    
    # Test main function
    print(f"\n📡 Testing find_active_market()...")
    market = scanner.find_active_market()
    
    if market:
        print(f"\n✅ MARKET FOUND!")
        print(f"   Title: {market['question'][:70]}")
        print(f"   Slug: {market['slug']}")
        print(f"   Status: active={market['active']}, closed={market['closed']}, accepting={market['accepting_orders']}")
        print(f"   YES: ${market['yes_price']:.4f}")
        print(f"   NO: ${market['no_price']:.4f}")
    else:
        print(f"\n⚠️ No active market found")
        print(f"\n💡 This is normal if:")
        print(f"   - Outside US trading hours (now is {scanner._timestamp_to_readable(now_utc)})")
        print(f"   - Low volatility period")
        print(f"   - Weekend/holiday")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    test_scanner()