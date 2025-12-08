"""
Market Scanner - FIXED VERSION with ASYNC support
Finds active BTC 15-minute markets using correct approach:
1. Scrape polymarket.com/crypto/15M for condition_ids
2. Query CLOB API with condition_id (ASYNC)
3. Cross-reference with Gamma for metadata (ASYNC)
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import aiohttp
import asyncio
import re
import time
from typing import Optional, Dict, List
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class MarketScanner:
    """Scans for active BTC 15-minute markets (ASYNC + SYNC support)"""
    
    def __init__(self):
        self.clob_url = "https://clob.polymarket.com/markets"
        self.gamma_url = "https://gamma-api.polymarket.com/markets"
        self.website_url = "https://polymarket.com/crypto/15M"
        
        # Cache condition IDs to avoid repeated scraping
        self._cached_condition_ids = []
        self._cache_time = 0
        self._cache_duration = 300  # 5 minutes
    
    # ==========================================
    # ASYNC METHODS (for main bot loop)
    # ==========================================
    
    async def find_active_market_async(self) -> Optional[Dict]:
        """
        Find currently active BTC 15-minute market (ASYNC version)
        
        Returns:
            Dict with market data or None
        """
        try:
            logger.info("🔍 Scanning for active BTC 15-minute market...")
            
            # Step 1: Get condition IDs from website (sync - fast enough)
            condition_ids = self._get_cached_condition_ids()
            
            if not condition_ids:
                logger.warning("❌ No condition IDs found on website")
                return None
            
            logger.info(f"✅ Found {len(condition_ids)} condition IDs in cache")
            
            # Step 2: Query CLOB API for each condition_id (ASYNC - parallel)
            markets = await self._fetch_markets_async(condition_ids[:20])
            
            # Step 3: Find first active market
            for market in markets:
                if market and self._is_market_active(market):
                    # Enrich with metadata
                    metadata = await self._get_market_metadata_async(
                        market['condition_id']
                    )
                    
                    if metadata:
                        market['question'] = metadata.get('question', 'Unknown')
                        market['slug'] = metadata.get('slug', 'Unknown')
                    
                    logger.info(f"✅ Found active market!")
                    logger.info(f"   Question: {market.get('question', 'N/A')[:80]}")
                    
                    return market
            
            logger.warning("⚠️  No active markets found")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error scanning markets: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def _fetch_markets_async(self, condition_ids: List[str]) -> List[Optional[Dict]]:
        """
        Fetch multiple markets concurrently (ASYNC)
        
        Args:
            condition_ids: List of condition IDs to fetch
            
        Returns:
            List of market dicts
        """
        async with aiohttp.ClientSession() as session:
            tasks = [
                self._get_market_from_clob_async(session, cid)
                for cid in condition_ids
            ]
            
            markets = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and None values
            return [m for m in markets if isinstance(m, dict)]
    
    async def _get_market_from_clob_async(
        self, 
        session: aiohttp.ClientSession,
        condition_id: str
    ) -> Optional[Dict]:
        """
        Get market data from CLOB API using condition_id (ASYNC)
        
        Args:
            session: aiohttp session
            condition_id: Market condition ID
            
        Returns:
            Market dict or None
        """
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
                
                # CLOB returns dict with 'data' key
                if isinstance(data, dict) and 'data' in data:
                    markets = data['data']
                else:
                    markets = data if isinstance(data, list) else []
                
                # Return first market if exists
                return markets[0] if markets else None
                
        except Exception as e:
            logger.debug(f"Error getting market from CLOB: {e}")
            return None
    
    async def _get_market_metadata_async(self, condition_id: str) -> Optional[Dict]:
        """
        Get market metadata from Gamma API (ASYNC)
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Metadata dict or None
        """
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
            logger.debug(f"Error getting metadata from Gamma: {e}")
            return None
    
    # ==========================================
    # SYNC METHODS (for compatibility)
    # ==========================================
    
    def find_active_market(self) -> Optional[Dict]:
        """
        Find currently active BTC 15-minute market (SYNC version)
        
        Returns:
            Dict with market data or None
        """
        try:
            logger.info("🔍 Scanning for active BTC 15-minute market...")
            
            # Step 1: Get condition IDs from website
            condition_ids = self._get_cached_condition_ids()
            
            if not condition_ids:
                logger.warning("❌ No condition IDs found on website")
                return None
            
            logger.info(f"✅ Found {len(condition_ids)} condition IDs")
            
            # Step 2: Query CLOB API for each condition_id
            for condition_id in condition_ids[:20]:  # Check first 20
                market = self._get_market_from_clob(condition_id)
                
                if market and self._is_market_active(market):
                    # Enrich with metadata from Gamma
                    metadata = self._get_market_metadata(condition_id)
                    
                    if metadata:
                        market['question'] = metadata.get('question', 'Unknown')
                        market['slug'] = metadata.get('slug', 'Unknown')
                    
                    logger.info(f"✅ Found active market!")
                    logger.info(f"   Question: {market.get('question', 'N/A')[:80]}")
                    logger.info(f"   Condition ID: {condition_id[:20]}...")
                    
                    return market
            
            logger.warning("⚠️  No active markets found")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error scanning markets: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _get_cached_condition_ids(self) -> List[str]:
        """
        Get condition IDs with caching to avoid repeated scraping
        
        Returns:
            List of condition_id strings
        """
        now = time.time()
        
        # Return cache if still fresh
        if self._cached_condition_ids and (now - self._cache_time) < self._cache_duration:
            return self._cached_condition_ids
        
        # Scrape fresh data
        condition_ids = self._scrape_condition_ids()
        
        if condition_ids:
            self._cached_condition_ids = condition_ids
            self._cache_time = now
        
        return condition_ids
    
    def _scrape_condition_ids(self) -> List[str]:
        """
        Scrape condition IDs from polymarket.com/crypto/15M
        
        Returns:
            List of condition_id strings
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(self.website_url, timeout=10, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch website: {response.status_code}")
                return []
            
            html = response.text
            
            # Extract condition IDs (0x followed by 64 hex chars)
            condition_ids = re.findall(r'0x[a-fA-F0-9]{64}', html)
            
            # Remove duplicates while preserving order
            unique_ids = []
            seen = set()
            
            for cid in condition_ids:
                if cid not in seen:
                    seen.add(cid)
                    unique_ids.append(cid)
            
            return unique_ids
            
        except Exception as e:
            logger.error(f"Error scraping condition IDs: {e}")
            return []
    
    def _get_market_from_clob(self, condition_id: str) -> Optional[Dict]:
        """
        Get market data from CLOB API using condition_id (SYNC)
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Market dict or None
        """
        try:
            params = {'condition_id': condition_id}
            
            response = requests.get(self.clob_url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # CLOB returns dict with 'data' key
            if isinstance(data, dict) and 'data' in data:
                markets = data['data']
            else:
                markets = data if isinstance(data, list) else []
            
            # Return first market if exists
            return markets[0] if markets else None
            
        except Exception as e:
            logger.debug(f"Error getting market from CLOB: {e}")
            return None
    
    def _get_market_metadata(self, condition_id: str) -> Optional[Dict]:
        """
        Get market metadata (question, slug) from Gamma API (SYNC)
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Metadata dict or None
        """
        try:
            params = {'condition_id': condition_id}
            
            response = requests.get(self.gamma_url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
            
            markets = response.json()
            
            return markets[0] if markets and len(markets) > 0 else None
            
        except Exception as e:
            logger.debug(f"Error getting metadata from Gamma: {e}")
            return None
    
    def _is_market_active(self, market: Dict) -> bool:
        """
        Check if market is valid for trading
        
        Criteria:
        - Active
        - Not closed
        - Accepting orders
        - Has 2 outcomes (YES/NO or UP/DOWN)
        """
        # Must be active
        if not market.get('active', False):
            return False
        
        # Must not be closed
        if market.get('closed', False):
            return False
        
        # Must accept orders
        if not market.get('accepting_orders', False):
            return False
        
        # Must have 2 tokens
        tokens = market.get('tokens', [])
        if len(tokens) != 2:
            return False
        
        return True
    
    def get_market_prices(self, condition_id: str) -> Optional[Dict]:
        """
        Get current market prices (SYNC)
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Dict with YES/NO prices or None
        """
        market = self._get_market_from_clob(condition_id)
        
        if not market:
            return None
        
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
    
    async def get_market_prices_async(self, condition_id: str) -> Optional[Dict]:
        """
        Get current market prices (ASYNC)
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Dict with YES/NO prices or None
        """
        async with aiohttp.ClientSession() as session:
            market = await self._get_market_from_clob_async(session, condition_id)
        
        if not market:
            return None
        
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
    
    def wait_for_market(self, max_wait: int = 300, check_interval: int = 30) -> Optional[Dict]:
        """
        Wait for an active market to appear (SYNC)
        
        Args:
            max_wait: Maximum seconds to wait
            check_interval: Seconds between checks
            
        Returns:
            Market dict or None
        """
        start_time = time.time()
        check_count = 0
        
        while (time.time() - start_time) < max_wait:
            check_count += 1
            
            logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] Check #{check_count}: Scanning for active market...")
            
            market = self.find_active_market()
            
            if market:
                return market
            
            logger.info(f"   ⏳ No active market, retrying in {check_interval}s...")
            time.sleep(check_interval)
        
        logger.warning(f"❌ No market found after {max_wait}s")
        return None


# Test function
def test_scanner():
    """Test the market scanner"""
    
    print("\n🧪 TESTING MARKET SCANNER")
    print("="*80)
    
    scanner = MarketScanner()
    
    # Test 1: Scrape condition IDs
    print("\n1️⃣ Testing condition ID scraping...")
    condition_ids = scanner._scrape_condition_ids()
    print(f"   Found {len(condition_ids)} condition IDs")
    
    if condition_ids:
        print(f"   First 3: {condition_ids[:3]}")
    
    # Test 2: Find active market (SYNC)
    print("\n2️⃣ Testing market finding (SYNC)...")
    market = scanner.find_active_market()
    
    if market:
        print("\n✅ SUCCESS! Found market:")
        print(f"   Question: {market.get('question', 'N/A')}")
        print(f"   Active: {market.get('active')}")
        print(f"   Accepting Orders: {market.get('accepting_orders')}")
        
        # Show tokens
        tokens = market.get('tokens', [])
        print(f"\n   Outcomes:")
        for token in tokens:
            print(f"      {token.get('outcome')}: ${token.get('price')}")
    else:
        print("\n⚠️  No active market found")
        print("   This is normal if markets are between rounds")
    
    # Test 3: Test ASYNC version
    print("\n3️⃣ Testing market finding (ASYNC)...")
    
    async def test_async():
        market = await scanner.find_active_market_async()
        if market:
            print(f"   ✅ ASYNC found: {market.get('question', 'N/A')[:50]}")
        else:
            print(f"   ⚠️  ASYNC: No market found")
    
    asyncio.run(test_async())
    
    print("\n" + "="*80)
    print("✅ Test complete!")


if __name__ == "__main__":
    test_scanner()