"""
Market Scanner - FIXED VERSION
Finds active BTC 15-minute markets using correct approach:
1. Scrape polymarket.com/crypto/15M for condition_ids
2. Query CLOB API with condition_id
3. Cross-reference with Gamma for metadata
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import re
import time
from typing import Optional, Dict, List
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class MarketScanner:
    """Scans for active BTC 15-minute markets"""
    
    def __init__(self):
        self.clob_url = "https://clob.polymarket.com/markets"
        self.gamma_url = "https://gamma-api.polymarket.com/markets"
        self.website_url = "https://polymarket.com/crypto/15M"
        
    def find_active_market(self) -> Optional[Dict]:
        """
        Find currently active BTC 15-minute market
        
        Returns:
            Dict with market data or None
        """
        try:
            logger.info("🔍 Scanning for active BTC 15-minute market...")
            
            # Step 1: Get condition IDs from website
            condition_ids = self._scrape_condition_ids()
            
            if not condition_ids:
                logger.warning("❌ No condition IDs found on website")
                return None
            
            logger.info(f"✅ Found {len(condition_ids)} condition IDs")
            
            # Step 2: Query CLOB API for each condition_id
            for condition_id in condition_ids[:20]:  # Check first 20
                market = self._get_market_from_clob(condition_id)
                
                if market:
                    # Check if market is active and accepting orders
                    if (market.get('active') and 
                        not market.get('closed') and 
                        market.get('accepting_orders')):
                        
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
        Get market data from CLOB API using condition_id
        
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
        Get market metadata (question, slug) from Gamma API
        
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
    
    def get_market_prices(self, condition_id: str) -> Optional[Dict]:
        """
        Get current market prices
        
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
    
    def wait_for_market(self, max_wait: int = 300, check_interval: int = 30) -> Optional[Dict]:
        """
        Wait for an active market to appear
        
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
    
    # Test 2: Find active market
    print("\n2️⃣ Testing market finding...")
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
    
    print("\n" + "="*80)
    print("✅ Test complete!")


if __name__ == "__main__":
    test_scanner()