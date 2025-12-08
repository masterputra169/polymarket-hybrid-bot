"""
Market Finder Module
Discovers and validates 15-minute BTC/ETH markets
"""
from typing import Optional, Dict, List
from datetime import datetime
from core.client import MarketDataAPI


class MarketFinder:
    """
    Find active 15-minute crypto markets
    Based on gabagool22's target markets
    """
    
    def __init__(self, asset: str = "BTC", duration: int = 15):
        """
        Initialize market finder
        
        Args:
            asset: Crypto asset (BTC, ETH, SOL, XRP)
            duration: Market duration in minutes (typically 15)
        """
        self.asset = asset.upper()
        self.duration = duration
        
        # Build search queries
        self.search_queries = self._build_search_queries()
    
    def _build_search_queries(self) -> List[str]:
        """Build search query variations"""
        asset_variations = {
            'BTC': ['BTC', 'Bitcoin'],
            'ETH': ['ETH', 'Ethereum'],
            'SOL': ['SOL', 'Solana'],
            'XRP': ['XRP', 'Ripple']
        }
        
        asset_terms = asset_variations.get(self.asset, [self.asset])
        
        queries = []
        
        for asset_term in asset_terms:
            # Try different query patterns
            queries.extend([
                f"{asset_term} {self.duration} minute",
                f"{asset_term} {self.duration}min",
                f"{asset_term} up or down {self.duration}",
                f"{asset_term} higher lower {self.duration}min",
                f"{asset_term} price {self.duration} minute"
            ])
        
        return queries
    
    def find_active_market(self) -> Optional[Dict]:
        """
        Find an active market accepting orders
        
        Returns:
            Market info dict or None if not found
        """
        # Try each search query
        for query in self.search_queries:
            market = MarketDataAPI.search_market(query)
            
            if market:
                # Validate market
                if self._is_valid_market(market):
                    return self._extract_market_info(market)
        
        # If search fails, try fetching all markets and filtering
        return self._find_in_all_markets()
    
    def _find_in_all_markets(self) -> Optional[Dict]:
        """
        Fallback: fetch all active markets and filter
        """
        markets = MarketDataAPI.get_markets(limit=100, active=True)
        
        # Handle both list and dict responses
        if isinstance(markets, dict):
            markets = markets.get('data', [])
        elif not isinstance(markets, list):
            print(f"⚠️ Unexpected markets type: {type(markets)}")
            return None
        
        for market in markets:
            if self._is_valid_market(market):
                # Check if it matches our criteria
                question = market.get('question', '').lower()
                
                # Must contain asset name
                asset_match = self.asset.lower() in question or \
                             self._get_asset_full_name().lower() in question
                
                # Must contain duration keywords
                duration_match = any(kw in question for kw in [
                    f"{self.duration} minute",
                    f"{self.duration}min",
                    "up or down",
                    "higher or lower"
                ])
                
                if asset_match and duration_match:
                    return self._extract_market_info(market)
        
        return None
    
    def _is_valid_market(self, market: Dict) -> bool:
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
        
        # Must have 2 outcomes
        outcomes = market.get('outcomes', [])
        if len(outcomes) != 2:
            return False
        
        return True
    
    def _extract_market_info(self, market: Dict) -> Dict:
        """
        Extract and format market information
        
        Returns:
            Standardized market info dict
        """
        outcomes = market.get('outcomes', [])
        outcome_prices = market.get('outcomePrices', [])
        
        # Determine which outcome is YES/UP and which is NO/DOWN
        yes_idx = 0
        no_idx = 1
        
        # Try to detect based on outcome names
        for i, outcome in enumerate(outcomes):
            outcome_lower = outcome.lower()
            if any(kw in outcome_lower for kw in ['yes', 'up', 'higher', 'above']):
                yes_idx = i
                no_idx = 1 - i
                break
        
        return {
            'condition_id': market.get('conditionId', ''),
            'title': market.get('question') or market.get('title', 'Unknown'),
            'slug': market.get('slug', ''),
            'active': market.get('active', False),
            'closed': market.get('closed', False),
            'accepting_orders': market.get('accepting_orders', False),
            'outcomes': outcomes,
            'outcome_prices': outcome_prices,
            'yes_token_id': market.get('tokens', [{}])[yes_idx].get('token_id', ''),
            'no_token_id': market.get('tokens', [{}])[no_idx].get('token_id', ''),
            'yes_outcome': outcomes[yes_idx] if outcomes else 'Yes',
            'no_outcome': outcomes[no_idx] if outcomes else 'No',
            'yes_price': float(outcome_prices[yes_idx]) if outcome_prices else 0.5,
            'no_price': float(outcome_prices[no_idx]) if outcome_prices else 0.5,
            'volume': market.get('volume', 0),
            'liquidity': market.get('liquidity', 0),
            'end_date': market.get('end_date_iso', ''),
        }
    
    def is_market_still_active(self, market: Dict) -> bool:
        """
        Check if a market is still active
        
        Args:
            market: Market info dict
        
        Returns:
            True if still active and accepting orders
        """
        # Re-fetch market data
        condition_id = market.get('condition_id')
        
        if not condition_id:
            return False
        
        # Search for updated market data
        fresh_market = MarketDataAPI.search_market(market.get('title', ''))
        
        if not fresh_market:
            return False
        
        # Check if still active
        return self._is_valid_market(fresh_market)
    
    def _get_asset_full_name(self) -> str:
        """Get full name of asset"""
        names = {
            'BTC': 'Bitcoin',
            'ETH': 'Ethereum',
            'SOL': 'Solana',
            'XRP': 'Ripple'
        }
        return names.get(self.asset, self.asset)
    
    def get_current_pair_cost(self, market: Dict) -> float:
        """
        Calculate current pair cost (YES price + NO price)
        
        This is the key metric for gabagool22's strategy:
        - If pair cost < $0.98, there's arbitrage opportunity
        - Lower pair cost = higher profit margin
        
        Args:
            market: Market info dict
        
        Returns:
            Pair cost in dollars
        """
        yes_price = market.get('yes_price', 0.5)
        no_price = market.get('no_price', 0.5)
        
        return yes_price + no_price
    
    def is_good_entry(self, market: Dict, target_pair_cost: float = 0.98) -> bool:
        """
        Check if current prices offer good entry point
        
        Args:
            market: Market info dict
            target_pair_cost: Maximum acceptable pair cost
        
        Returns:
            True if pair cost is below target
        """
        current_pair_cost = self.get_current_pair_cost(market)
        
        return current_pair_cost < target_pair_cost


# ==========================================
# TESTING & UTILITIES
# ==========================================

def test_market_finder():
    """Test the market finder"""
    print("🔍 Testing Market Finder...\n")
    
    # Test for BTC 15-minute markets
    finder = MarketFinder(asset="BTC", duration=15)
    
    print(f"📊 Search queries:")
    for i, query in enumerate(finder.search_queries, 1):
        print(f"   {i}. {query}")
    
    print(f"\n🎯 Searching for active market...")
    market = finder.find_active_market()
    
    if market:
        print(f"\n✅ MARKET FOUND!")
        print(f"   Title: {market['title']}")
        print(f"   ID: {market['condition_id']}")
        print(f"   Outcomes: {market['outcomes']}")
        print(f"   YES: {market['yes_outcome']} @ ${market['yes_price']:.2f}")
        print(f"   NO: {market['no_outcome']} @ ${market['no_price']:.2f}")
        print(f"   Pair Cost: ${finder.get_current_pair_cost(market):.2f}")
        print(f"   Good Entry: {finder.is_good_entry(market)}")
        print(f"   Volume: ${market['volume']:,.2f}")
        print(f"   Liquidity: ${market['liquidity']:,.2f}")
    else:
        print(f"\n❌ No active market found")
        print(f"\n💡 This might mean:")
        print(f"   - Markets only available during US trading hours")
        print(f"   - No 15-minute markets currently running")
        print(f"   - Try different search terms")


if __name__ == "__main__":
    test_market_finder()