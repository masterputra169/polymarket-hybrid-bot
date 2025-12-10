"""
Market Scanner V10 - CORRECT TOKEN MATCHING
Fixes issue where wrong tokens were being returned

KEY FIXES:
1. Get tokens directly from Gamma API market data (not CLOB)
2. Verify token outcomes match "Up"/"Down" not random sports teams
3. Better validation of market data
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


def get_et_offset() -> int:
    now = datetime.now(timezone.utc)
    month = now.month
    return -4 if 3 <= month <= 10 else -5

ET_OFFSET_HOURS = get_et_offset()
ET_OFFSET = timedelta(hours=ET_OFFSET_HOURS)


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
        
        logger.info(f"📡 Scanner V10 initialized")
        logger.info(f"   Asset: {self.asset} | Duration: {self.duration}min")
    
    def _get_utc_now(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())
    
    def _timestamp_to_et(self, ts: int) -> str:
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_et = dt_utc + ET_OFFSET
        tz_name = "EST" if ET_OFFSET_HOURS == -5 else "EDT"
        return dt_et.strftime(f'%I:%M %p {tz_name}')
    
    def _get_current_et(self) -> str:
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc + ET_OFFSET
        tz_name = "EST" if ET_OFFSET_HOURS == -5 else "EDT"
        return now_et.strftime(f'%I:%M:%S %p {tz_name}')
    
    def _get_market_timestamps(self, look_back: int = 1, look_ahead: int = 2) -> List[int]:
        now_utc = self._get_utc_now()
        interval = self.interval_seconds
        current = (now_utc // interval) * interval
        
        return [current + (i * interval) for i in range(-look_back, look_ahead + 1)]
    
    def _is_timestamp_in_trading_window(self, market_start_ts: int) -> tuple:
        now = self._get_utc_now()
        market_end_ts = market_start_ts + self.interval_seconds
        trading_end_ts = market_end_ts - 60
        
        if now < market_start_ts:
            return (False, market_start_ts - now, f"Starts in {market_start_ts - now}s")
        elif now >= market_end_ts:
            return (False, 0, "Market ended")
        elif now >= trading_end_ts:
            return (False, market_end_ts - now, f"Final {market_end_ts - now}s")
        else:
            return (True, market_end_ts - now, f"ACTIVE - {market_end_ts - now}s remaining")
    
    def _safe_parse_json_field(self, data, default=None):
        """Safely parse a field that might be JSON string or already parsed"""
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
    
    def _validate_updown_market(self, market_data: Dict) -> bool:
        """Validate that this is actually an Up/Down market"""
        outcomes = self._safe_parse_json_field(market_data.get('outcomes'), [])
        
        # Must have exactly 2 outcomes
        if len(outcomes) != 2:
            return False
        
        # Outcomes must be Up/Down or Yes/No variants
        valid_yes = ['up', 'yes', 'higher']
        valid_no = ['down', 'no', 'lower']
        
        outcome_lower = [o.lower() for o in outcomes]
        
        has_yes = any(v in outcome_lower[0] for v in valid_yes)
        has_no = any(v in outcome_lower[1] for v in valid_no)
        
        # Or reversed
        if not (has_yes and has_no):
            has_yes = any(v in outcome_lower[1] for v in valid_yes)
            has_no = any(v in outcome_lower[0] for v in valid_no)
        
        return has_yes or has_no or ('up' in str(outcomes).lower() and 'down' in str(outcomes).lower())
    
    # ==========================================
    # MAIN
    # ==========================================
    
    def find_active_market(self) -> Optional[Dict]:
        logger.info(f"🔍 Scanning for {self.asset} {self.duration}min market...")
        logger.info(f"   Current ET: {self._get_current_et()}")
        
        # Method 1: Direct Gamma event lookup by slug
        market = self._find_by_gamma_event()
        if market:
            return market
        
        # Method 2: Search Gamma markets
        market = self._find_via_gamma_markets()
        if market:
            return market
        
        logger.warning("⚠️ No active market found")
        return None
    
    async def find_active_market_async(self) -> Optional[Dict]:
        logger.info(f"🔍 Scanning... ET: {self._get_current_et()}")
        
        market = await self._find_by_gamma_event_async()
        if market:
            return market
        
        market = await self._find_via_gamma_markets_async()
        if market:
            return market
        
        logger.warning("⚠️ No active market found")
        return None
    
    # ==========================================
    # METHOD 1: Gamma Event by Slug
    # ==========================================
    
    def _find_by_gamma_event(self) -> Optional[Dict]:
        """Find market using Gamma events API - gets correct token data"""
        slug_prefix = self.slug_patterns.get(self.asset)
        if not slug_prefix:
            return None
        
        timestamps = self._get_market_timestamps(look_back=1, look_ahead=2)
        logger.info(f"   Method 1: Checking {len(timestamps)} timestamps...")
        
        for ts in timestamps:
            slug = f"{slug_prefix}{ts}"
            et_time = self._timestamp_to_et(ts)
            
            is_tradeable, remaining, status_msg = self._is_timestamp_in_trading_window(ts)
            logger.info(f"   {et_time}: {status_msg}")
            
            if not is_tradeable:
                continue
            
            # Get event from Gamma API
            event = self._get_gamma_event(slug)
            if not event:
                continue
            
            logger.info(f"   ✅ Found event: {slug}")
            
            # Get market from event
            markets = event.get('markets', [])
            if not markets:
                continue
            
            market_data = markets[0]
            
            # VALIDATE: Check this is actually an Up/Down market
            if not self._validate_updown_market(market_data):
                logger.warning(f"   ⚠️ Invalid market type, skipping")
                continue
            
            # Build market info from Gamma data (NOT CLOB)
            market_info = self._build_from_gamma_event(market_data, event, remaining)
            
            if market_info and market_info.get('yes_token_id'):
                # Verify prices are reasonable (not settled)
                if market_info['yes_price'] > 0.01 and market_info['yes_price'] < 0.99:
                    logger.info(f"   🎯 TRADEABLE MARKET FOUND!")
                    return market_info
                elif market_info['no_price'] > 0.01 and market_info['no_price'] < 0.99:
                    logger.info(f"   🎯 TRADEABLE MARKET FOUND!")
                    return market_info
                else:
                    logger.info(f"   ⚠️ Market appears settled (prices at extremes)")
        
        return None
    
    async def _find_by_gamma_event_async(self) -> Optional[Dict]:
        """Async version"""
        slug_prefix = self.slug_patterns.get(self.asset)
        if not slug_prefix:
            return None
        
        timestamps = self._get_market_timestamps(look_back=1, look_ahead=2)
        logger.info(f"   Method 1: Checking {len(timestamps)} timestamps...")
        
        async with aiohttp.ClientSession() as session:
            for ts in timestamps:
                slug = f"{slug_prefix}{ts}"
                et_time = self._timestamp_to_et(ts)
                
                is_tradeable, remaining, status_msg = self._is_timestamp_in_trading_window(ts)
                logger.info(f"   {et_time}: {status_msg}")
                
                if not is_tradeable:
                    continue
                
                event = await self._get_gamma_event_async(session, slug)
                if not event:
                    continue
                
                logger.info(f"   ✅ Found event: {slug}")
                
                markets = event.get('markets', [])
                if not markets:
                    continue
                
                market_data = markets[0]
                
                if not self._validate_updown_market(market_data):
                    logger.warning(f"   ⚠️ Invalid market type")
                    continue
                
                market_info = self._build_from_gamma_event(market_data, event, remaining)
                
                if market_info and market_info.get('yes_token_id'):
                    if 0.01 < market_info['yes_price'] < 0.99 or 0.01 < market_info['no_price'] < 0.99:
                        logger.info(f"   🎯 TRADEABLE MARKET FOUND!")
                        return market_info
        
        return None
    
    def _get_gamma_event(self, slug: str) -> Optional[Dict]:
        """Get event from Gamma API"""
        try:
            url = f"{self.gamma_url}/events/slug/{slug}"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            return data if isinstance(data, dict) else (data[0] if data else None)
        except Exception as e:
            logger.debug(f"Gamma event error: {e}")
            return None
    
    async def _get_gamma_event_async(self, session, slug: str) -> Optional[Dict]:
        """Async version"""
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
    # METHOD 2: Gamma Markets Search
    # ==========================================
    
    def _find_via_gamma_markets(self) -> Optional[Dict]:
        """Search Gamma markets API"""
        logger.info(f"   Method 2: Gamma markets search...")
        
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
            pattern = f"{asset_lower}-updown-{self.duration}m"
            
            for market in markets:
                slug = market.get('slug', '').lower()
                
                if pattern not in slug:
                    continue
                
                # Extract timestamp and validate
                try:
                    ts = int(slug.split('-')[-1])
                    is_tradeable, remaining, _ = self._is_timestamp_in_trading_window(ts)
                    
                    if not is_tradeable:
                        continue
                    
                    if not self._validate_updown_market(market):
                        continue
                    
                    logger.info(f"   ✅ Found via Gamma markets: {market.get('slug')}")
                    
                    market_info = self._build_from_gamma_market(market, remaining)
                    
                    if market_info and market_info.get('yes_token_id'):
                        if 0.01 < market_info['yes_price'] < 0.99 or 0.01 < market_info['no_price'] < 0.99:
                            return market_info
                except:
                    continue
            
            return None
        except Exception as e:
            logger.error(f"   Gamma markets error: {e}")
            return None
    
    async def _find_via_gamma_markets_async(self) -> Optional[Dict]:
        """Async version"""
        logger.info(f"   Method 2: Gamma markets search...")
        
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
                    pattern = f"{asset_lower}-updown-{self.duration}m"
                    
                    for market in markets:
                        slug = market.get('slug', '').lower()
                        
                        if pattern not in slug:
                            continue
                        
                        try:
                            ts = int(slug.split('-')[-1])
                            is_tradeable, remaining, _ = self._is_timestamp_in_trading_window(ts)
                            
                            if not is_tradeable:
                                continue
                            
                            if not self._validate_updown_market(market):
                                continue
                            
                            logger.info(f"   ✅ Found via Gamma!")
                            
                            market_info = self._build_from_gamma_market(market, remaining)
                            
                            if market_info and market_info.get('yes_token_id'):
                                if 0.01 < market_info['yes_price'] < 0.99:
                                    return market_info
                        except:
                            continue
                    
                    return None
        except Exception as e:
            logger.error(f"   Async Gamma error: {e}")
            return None
    
    # ==========================================
    # BUILD MARKET INFO
    # ==========================================
    
    def _build_from_gamma_event(self, market_data: Dict, event_data: Dict, time_remaining: int) -> Optional[Dict]:
        """Build market info from Gamma event data"""
        try:
            # Get outcomes
            outcomes = self._safe_parse_json_field(market_data.get('outcomes'), ['Up', 'Down'])
            
            # Get prices
            outcome_prices = self._safe_parse_json_field(market_data.get('outcomePrices'), [])
            if outcome_prices and len(outcome_prices) >= 2:
                yes_price = float(outcome_prices[0])
                no_price = float(outcome_prices[1])
            else:
                yes_price = 0.5
                no_price = 0.5
            
            # Get token IDs from clobTokenIds field
            clob_token_ids = self._safe_parse_json_field(market_data.get('clobTokenIds'), [])
            
            if len(clob_token_ids) < 2:
                logger.warning("Missing clobTokenIds")
                return None
            
            yes_token_id = str(clob_token_ids[0])
            no_token_id = str(clob_token_ids[1])
            
            # Determine which outcome is YES/UP
            yes_outcome = outcomes[0] if outcomes else 'Up'
            no_outcome = outcomes[1] if len(outcomes) > 1 else 'Down'
            
            # Swap if needed (if first outcome is "Down")
            if 'down' in yes_outcome.lower() or 'no' in yes_outcome.lower():
                yes_outcome, no_outcome = no_outcome, yes_outcome
                yes_price, no_price = no_price, yes_price
                yes_token_id, no_token_id = no_token_id, yes_token_id
            
            question = event_data.get('title') or market_data.get('question') or 'Unknown'
            condition_id = market_data.get('conditionId') or market_data.get('condition_id', '')
            
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
            logger.error(f"Build from gamma event error: {e}")
            return None
    
    def _build_from_gamma_market(self, market_data: Dict, time_remaining: int) -> Optional[Dict]:
        """Build from Gamma market data"""
        try:
            outcomes = self._safe_parse_json_field(market_data.get('outcomes'), ['Up', 'Down'])
            outcome_prices = self._safe_parse_json_field(market_data.get('outcomePrices'), [])
            clob_token_ids = self._safe_parse_json_field(market_data.get('clobTokenIds'), [])
            
            if len(clob_token_ids) < 2:
                return None
            
            yes_price = float(outcome_prices[0]) if outcome_prices else 0.5
            no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
            
            yes_token_id = str(clob_token_ids[0])
            no_token_id = str(clob_token_ids[1])
            
            yes_outcome = outcomes[0] if outcomes else 'Up'
            no_outcome = outcomes[1] if len(outcomes) > 1 else 'Down'
            
            if 'down' in yes_outcome.lower():
                yes_outcome, no_outcome = no_outcome, yes_outcome
                yes_price, no_price = no_price, yes_price
                yes_token_id, no_token_id = no_token_id, yes_token_id
            
            return {
                'condition_id': market_data.get('conditionId') or market_data.get('condition_id', ''),
                'question': market_data.get('question', 'Unknown'),
                'title': market_data.get('question', 'Unknown'),
                'slug': market_data.get('slug', ''),
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
            logger.error(f"Build from gamma market error: {e}")
            return None
    
    def get_market_prices(self, condition_id: str) -> Optional[Dict]:
        """Get fresh prices from Gamma API"""
        try:
            url = f"{self.gamma_url}/markets"
            params = {'condition_id': condition_id}
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return None
            
            markets = response.json()
            if not markets:
                return None
            
            market = markets[0] if isinstance(markets, list) else markets
            
            outcome_prices = self._safe_parse_json_field(market.get('outcomePrices'), [])
            clob_token_ids = self._safe_parse_json_field(market.get('clobTokenIds'), [])
            
            if len(outcome_prices) < 2 or len(clob_token_ids) < 2:
                return None
            
            return {
                'prices': {
                    'YES': float(outcome_prices[0]),
                    'NO': float(outcome_prices[1])
                },
                'token_ids': {
                    'YES': str(clob_token_ids[0]),
                    'NO': str(clob_token_ids[1])
                }
            }
        except:
            return None


def test_scanner():
    print("\n" + "="*70)
    print("🧪 TESTING MARKET SCANNER V10 (CORRECT TOKEN MATCHING)")
    print("="*70)
    
    scanner = MarketScanner(asset="BTC", duration=15)
    
    print(f"\n🕐 Current Time: {scanner._get_current_et()}")
    
    print(f"\n📅 Market Windows:")
    timestamps = scanner._get_market_timestamps(look_back=1, look_ahead=2)
    
    for ts in timestamps:
        et_time = scanner._timestamp_to_et(ts)
        is_tradeable, remaining, status = scanner._is_timestamp_in_trading_window(ts)
        slug = f"btc-updown-15m-{ts}"
        
        icon = "✅" if is_tradeable else "❌"
        print(f"   {icon} {et_time}: {status}")
        print(f"      Slug: {slug}")
    
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
        
        # Validate outcomes are correct
        print(f"\n🔍 Validation:")
        if 'up' in market['yes_outcome'].lower() or 'yes' in market['yes_outcome'].lower():
            print(f"   ✅ YES outcome is correct: {market['yes_outcome']}")
        else:
            print(f"   ❌ YES outcome might be wrong: {market['yes_outcome']}")
        
        if 'down' in market['no_outcome'].lower() or 'no' in market['no_outcome'].lower():
            print(f"   ✅ NO outcome is correct: {market['no_outcome']}")
        else:
            print(f"   ❌ NO outcome might be wrong: {market['no_outcome']}")
    else:
        print(f"\n⚠️ No active market found")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    test_scanner()