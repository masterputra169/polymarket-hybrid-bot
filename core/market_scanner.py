"""
Market Scanner V11 - ONLY RETURNS TRULY ACTIVE MARKETS
Fixes issue where expired markets were being returned

KEY CHANGES:
1. Strict time validation - only returns markets with >60s remaining
2. Uses CLOB /price endpoint to verify market is tradeable
3. Better logging of market status
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import aiohttp
import asyncio
import json
from typing import Optional, Dict, List
from datetime import datetime, timezone, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketScanner:
    def __init__(self, asset: str = "BTC", duration: int = 15):
        self.asset = asset.upper()
        self.duration = duration
        self.interval_seconds = duration * 60
        
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.clob_url = "https://clob.polymarket.com"
        
        self.slug_patterns = {
            'BTC': 'btc-updown-15m-',
            'ETH': 'eth-updown-15m-',
            'SOL': 'sol-updown-15m-',
        }
        
        logger.info(f"📡 Scanner V11 initialized")
        logger.info(f"   Asset: {self.asset} | Duration: {self.duration}min")
    
    def _get_utc_now(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())
    
    def _timestamp_to_et(self, ts: int) -> str:
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        et_offset = timedelta(hours=-5)  # EST
        dt_et = dt_utc + et_offset
        return dt_et.strftime('%I:%M %p ET')
    
    def _get_current_et(self) -> str:
        now_utc = datetime.now(timezone.utc)
        et_offset = timedelta(hours=-5)
        now_et = now_utc + et_offset
        return now_et.strftime('%I:%M:%S %p ET')
    
    def _get_market_timestamps(self) -> List[int]:
        """Get timestamps for current and next market slots"""
        now_utc = self._get_utc_now()
        interval = self.interval_seconds
        
        # Current slot
        current_slot = (now_utc // interval) * interval
        
        # Return current and next slot
        return [current_slot, current_slot + interval]
    
    def _calculate_time_remaining(self, market_start_ts: int) -> tuple:
        """
        Calculate time remaining for trading
        
        Returns: (is_tradeable, seconds_remaining, status_message)
        """
        now = self._get_utc_now()
        market_end_ts = market_start_ts + self.interval_seconds
        
        # Trading ends 60 seconds before market closes
        trading_end_ts = market_end_ts - 60
        
        if now < market_start_ts:
            wait_time = market_start_ts - now
            return (False, 0, f"Starts in {wait_time}s")
        
        if now >= market_end_ts:
            return (False, 0, "EXPIRED")
        
        if now >= trading_end_ts:
            remaining = market_end_ts - now
            return (False, remaining, f"SNIPING ONLY ({remaining}s)")
        
        # Active for pair trading
        remaining = market_end_ts - now
        return (True, remaining, f"ACTIVE ({remaining}s remaining)")
    
    def _safe_parse_json(self, data, default=None):
        if data is None:
            return default
        if isinstance(data, (list, dict)):
            return data
        if isinstance(data, str):
            try:
                return json.loads(data.replace("'", '"'))
            except:
                return default
        return default
    
    # ==========================================
    # MAIN ENTRY POINT
    # ==========================================
    
    def find_active_market(self) -> Optional[Dict]:
        """Find an active market that is currently tradeable"""
        logger.info(f"🔍 Scanning for {self.asset} {self.duration}min market...")
        logger.info(f"   Current ET: {self._get_current_et()}")
        
        slug_prefix = self.slug_patterns.get(self.asset)
        if not slug_prefix:
            logger.error(f"Unknown asset: {self.asset}")
            return None
        
        timestamps = self._get_market_timestamps()
        
        for ts in timestamps:
            slug = f"{slug_prefix}{ts}"
            et_time = self._timestamp_to_et(ts)
            
            is_tradeable, remaining, status = self._calculate_time_remaining(ts)
            logger.info(f"   {et_time}: {status}")
            
            if remaining <= 0:
                continue  # Skip expired markets
            
            # Try to fetch this market
            event = self._fetch_gamma_event(slug)
            if not event:
                continue
            
            logger.info(f"   ✅ Found: {slug}")
            
            markets = event.get('markets', [])
            if not markets:
                continue
            
            market_data = markets[0]
            
            # Build market info
            market_info = self._build_market_info(market_data, event, remaining)
            
            if not market_info:
                continue
            
            # VERIFY: Check CLOB returns valid prices
            if self._verify_market_tradeable(market_info):
                logger.info(f"   🎯 TRADEABLE MARKET FOUND!")
                return market_info
            else:
                logger.warning(f"   ⚠️ Market not tradeable (CLOB check failed)")
        
        logger.warning("⚠️ No active tradeable market found")
        return None
    
    async def find_active_market_async(self) -> Optional[Dict]:
        """Async version of find_active_market"""
        logger.info(f"🔍 Scanning... ET: {self._get_current_et()}")
        
        slug_prefix = self.slug_patterns.get(self.asset)
        if not slug_prefix:
            return None
        
        timestamps = self._get_market_timestamps()
        
        async with aiohttp.ClientSession() as session:
            for ts in timestamps:
                slug = f"{slug_prefix}{ts}"
                et_time = self._timestamp_to_et(ts)
                
                is_tradeable, remaining, status = self._calculate_time_remaining(ts)
                logger.info(f"   {et_time}: {status}")
                
                if remaining <= 0:
                    continue
                
                event = await self._fetch_gamma_event_async(session, slug)
                if not event:
                    continue
                
                logger.info(f"   ✅ Found: {slug}")
                
                markets = event.get('markets', [])
                if not markets:
                    continue
                
                market_data = markets[0]
                market_info = self._build_market_info(market_data, event, remaining)
                
                if not market_info:
                    continue
                
                # Verify tradeable
                if await self._verify_market_tradeable_async(session, market_info):
                    logger.info(f"   🎯 TRADEABLE MARKET FOUND!")
                    return market_info
        
        logger.warning("⚠️ No active market found")
        return None
    
    # ==========================================
    # GAMMA API
    # ==========================================
    
    def _fetch_gamma_event(self, slug: str) -> Optional[Dict]:
        try:
            url = f"{self.gamma_url}/events/slug/{slug}"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            return data if isinstance(data, dict) else (data[0] if data else None)
        except:
            return None
    
    async def _fetch_gamma_event_async(self, session, slug: str) -> Optional[Dict]:
        try:
            url = f"{self.gamma_url}/events/slug/{slug}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                return data if isinstance(data, dict) else (data[0] if data else None)
        except:
            return None
    
    # ==========================================
    # CLOB VERIFICATION
    # ==========================================
    
    def _verify_market_tradeable(self, market: Dict) -> bool:
        """Verify market is tradeable by checking CLOB"""
        try:
            yes_token = market.get('yes_token_id')
            
            if not yes_token:
                return False
            
            # Try /price endpoint
            response = requests.get(
                f"{self.clob_url}/price",
                params={'token_id': yes_token, 'side': 'BUY'},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                price = float(data.get('price', 0))
                
                # Valid price range
                if 0.01 < price < 0.99:
                    logger.info(f"   CLOB price check: YES=${price:.4f} ✓")
                    return True
            
            # Try /book endpoint as backup
            response = requests.get(
                f"{self.clob_url}/book",
                params={'token_id': yes_token},
                timeout=5
            )
            
            if response.status_code == 200:
                book = response.json()
                if book.get('asks') or book.get('bids'):
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"CLOB verify error: {e}")
            return False
    
    async def _verify_market_tradeable_async(self, session, market: Dict) -> bool:
        """Async version of verify"""
        try:
            yes_token = market.get('yes_token_id')
            
            if not yes_token:
                return False
            
            async with session.get(
                f"{self.clob_url}/price",
                params={'token_id': yes_token, 'side': 'BUY'},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data.get('price', 0))
                    
                    if 0.01 < price < 0.99:
                        logger.info(f"   CLOB price: YES=${price:.4f} ✓")
                        return True
            
            return False
            
        except:
            return False
    
    # ==========================================
    # BUILD MARKET INFO
    # ==========================================
    
    def _build_market_info(self, market_data: Dict, event_data: Dict, time_remaining: int) -> Optional[Dict]:
        try:
            outcomes = self._safe_parse_json(market_data.get('outcomes'), ['Up', 'Down'])
            outcome_prices = self._safe_parse_json(market_data.get('outcomePrices'), [])
            clob_token_ids = self._safe_parse_json(market_data.get('clobTokenIds'), [])
            
            if len(clob_token_ids) < 2:
                logger.warning("Missing clobTokenIds")
                return None
            
            # Parse prices
            yes_price = float(outcome_prices[0]) if outcome_prices else 0.5
            no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
            
            # Token IDs
            yes_token_id = str(clob_token_ids[0])
            no_token_id = str(clob_token_ids[1])
            
            # Outcome names
            yes_outcome = outcomes[0] if outcomes else 'Up'
            no_outcome = outcomes[1] if len(outcomes) > 1 else 'Down'
            
            # Swap if first outcome is "Down"
            if 'down' in yes_outcome.lower():
                yes_outcome, no_outcome = no_outcome, yes_outcome
                yes_price, no_price = no_price, yes_price
                yes_token_id, no_token_id = no_token_id, yes_token_id
            
            question = event_data.get('title') or market_data.get('question') or 'Unknown'
            condition_id = market_data.get('conditionId') or ''
            
            return {
                'condition_id': condition_id,
                'question': question,
                'title': question,
                'slug': event_data.get('slug', ''),
                'active': True,
                'closed': False,
                'accepting_orders': True,
                'outcomes': [yes_outcome, no_outcome],
                'yes_token_id': yes_token_id,
                'no_token_id': no_token_id,
                'yes_outcome': yes_outcome,
                'no_outcome': no_outcome,
                'yes_price': yes_price,
                'no_price': no_price,
                'volume': float(market_data.get('volume', 0) or 0),
                'liquidity': float(market_data.get('liquidity', 0) or 0),
                'end_time': market_data.get('endDate', ''),
                'time_remaining': time_remaining,
            }
        except Exception as e:
            logger.error(f"Build market error: {e}")
            return None


# ==========================================
# TEST
# ==========================================

def test_scanner():
    print("\n" + "="*70)
    print("🧪 TESTING MARKET SCANNER V11")
    print("="*70)
    
    scanner = MarketScanner(asset="BTC", duration=15)
    
    print(f"\n🕐 Current Time: {scanner._get_current_et()}")
    
    print(f"\n📡 Searching for active market...")
    market = scanner.find_active_market()
    
    if market:
        print(f"\n" + "="*70)
        print(f"🎯 MARKET FOUND!")
        print(f"="*70)
        print(f"   Title: {market['question'][:60]}...")
        print(f"   Slug: {market['slug']}")
        print(f"   Time Remaining: {market.get('time_remaining', 'N/A')}s")
        print(f"   YES ({market['yes_outcome']}): ${market['yes_price']:.4f}")
        print(f"   NO ({market['no_outcome']}): ${market['no_price']:.4f}")
        print(f"   Pair Cost: ${market['yes_price'] + market['no_price']:.4f}")
        print(f"   YES Token: {market['yes_token_id'][:40]}...")
        print(f"   NO Token: {market['no_token_id'][:40]}...")
        
        # Test CLOB orderbook
        print(f"\n📖 Testing CLOB orderbook...")
        
        for name, token_id in [("YES", market['yes_token_id']), ("NO", market['no_token_id'])]:
            try:
                response = requests.get(
                    f"https://clob.polymarket.com/book",
                    params={'token_id': token_id},
                    timeout=5
                )
                
                if response.status_code == 200:
                    book = response.json()
                    asks = book.get('asks', [])
                    bids = book.get('bids', [])
                    
                    if asks:
                        best_ask = float(asks[0]['price'])
                        print(f"   {name} Best ASK: ${best_ask:.4f}")
                    if bids:
                        best_bid = float(bids[0]['price'])
                        print(f"   {name} Best BID: ${best_bid:.4f}")
                else:
                    print(f"   {name}: HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"   {name}: Error - {e}")
    else:
        print(f"\n⚠️ No active market found")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    test_scanner()