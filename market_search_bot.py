"""
Polymarket Bot - SEARCH-BASED Market Discovery
User inputs market name → Bot finds and trades it!
"""

import os
import time
import requests
from typing import Optional, Dict, List
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.constants import POLYGON

load_dotenv()


class SearchBasedBot:
    """
    Bot that searches markets by name
    Much simpler and more reliable!
    """
    
    def __init__(self):
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.private_key = os.getenv("PRIVATE_KEY")
        self.proxy_address = os.getenv("PROXY_ADDRESS")
        
        # Trading params
        self.target_pair_cost = float(os.getenv("TARGET_PAIR_COST", "0.98"))
        self.order_size_usd = float(os.getenv("ORDER_SIZE_USD", "1.0"))
        self.max_per_side = float(os.getenv("MAX_PER_SIDE", "5.0"))
        self.dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        
        # Client
        self.client = None
        
        print("🤖 Search-Based Bot initialized")
    
    def connect(self):
        """Connect to Polymarket"""
        try:
            print("📡 Connecting to Polymarket...")
            
            self.client = ClobClient(
                "https://clob.polymarket.com",
                key=self.private_key,
                chain_id=POLYGON,
                signature_type=2
            )
            
            # Set credentials
            creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(creds)
            
            print("✅ Connected!")
            
        except Exception as e:
            print(f"❌ Connection error: {e}")
            raise
    
    def search_markets(self, query: str) -> List[Dict]:
        """
        Search markets by name/keywords
        
        Args:
            query: Search query (e.g. "BTC 15", "Bitcoin 15 minute")
        
        Returns:
            List of matching markets
        """
        try:
            print(f"\n🔍 Searching for: '{query}'")
            
            # Method 1: Try Gamma search endpoint
            search_url = f"{self.gamma_url}/search"
            
            params = {
                'query': query,
                'limit': 20
            }
            
            response = requests.get(search_url, params=params, timeout=10)
            
            if response.status_code == 200:
                results = response.json()
                
                if isinstance(results, list) and results:
                    print(f"✅ Found {len(results)} markets via search")
                    return results
            
            # Method 2: Get all markets and filter
            print("   Trying fallback method...")
            
            markets_url = f"{self.gamma_url}/markets"
            
            params = {
                'limit': 100,
                'closed': False
            }
            
            response = requests.get(markets_url, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ API error: {response.status_code}")
                return []
            
            all_markets = response.json()
            
            if not isinstance(all_markets, list):
                return []
            
            # Filter by query keywords
            query_lower = query.lower()
            keywords = query_lower.split()
            
            matches = []
            
            for market in all_markets:
                question = market.get('question', '').lower()
                
                # Check if ALL keywords present
                if all(kw in question for kw in keywords):
                    matches.append(market)
            
            print(f"✅ Found {len(matches)} matching markets")
            return matches
            
        except Exception as e:
            print(f"❌ Search error: {e}")
            return []
    
    def display_markets(self, markets: List[Dict]):
        """Display markets for user selection"""
        
        print("\n" + "="*80)
        print("📋 AVAILABLE MARKETS")
        print("="*80)
        
        for i, market in enumerate(markets, 1):
            question = market.get('question', 'Unknown')
            volume = market.get('volume', 0)
            closed = market.get('closed', False)
            
            status = "🔴 CLOSED" if closed else "🟢 OPEN"
            
            print(f"\n{i}. {status} {question}")
            print(f"   Volume: ${volume:,.0f}")
            print(f"   ID: {market.get('condition_id', 'N/A')[:30]}...")
        
        print("\n" + "="*80)
    
    def select_market(self, markets: List[Dict]) -> Optional[Dict]:
        """Let user select a market"""
        
        if not markets:
            print("❌ No markets found")
            return None
        
        if len(markets) == 1:
            print(f"\n✅ Auto-selecting only market: {markets[0]['question']}")
            return markets[0]
        
        self.display_markets(markets)
        
        while True:
            try:
                choice = input(f"\nSelect market (1-{len(markets)}) or 'q' to quit: ").strip()
                
                if choice.lower() == 'q':
                    return None
                
                idx = int(choice) - 1
                
                if 0 <= idx < len(markets):
                    selected = markets[idx]
                    print(f"\n✅ Selected: {selected['question']}")
                    return selected
                else:
                    print(f"❌ Invalid choice. Enter 1-{len(markets)}")
            
            except ValueError:
                print("❌ Invalid input. Enter a number or 'q'")
            except KeyboardInterrupt:
                print("\n⚠️  Cancelled")
                return None
    
    def get_market_details(self, market: Dict) -> Optional[Dict]:
        """Get detailed market info from CLOB"""
        
        condition_id = market.get('condition_id')
        
        if not condition_id:
            print("❌ No condition_id")
            return None
        
        try:
            print(f"\n📊 Getting market details...")
            
            clob_market = self.client.get_market(condition_id)
            
            if not clob_market:
                print("❌ Could not get CLOB data")
                return None
            
            # Merge Gamma + CLOB data
            market['clob_data'] = clob_market
            
            # Extract token info
            tokens = clob_market.get('tokens', [])
            
            for token in tokens:
                outcome = token.get('outcome', '').upper()
                
                if any(kw in outcome for kw in ['YES', 'UP', 'HIGHER']):
                    market['yes_token_id'] = token.get('token_id')
                    market['yes_price'] = float(token.get('price', 0.5))
                elif any(kw in outcome for kw in ['NO', 'DOWN', 'LOWER']):
                    market['no_token_id'] = token.get('token_id')
                    market['no_price'] = float(token.get('price', 0.5))
            
            # Market status
            market['accepting_orders'] = clob_market.get('accepting_orders', False)
            market['active'] = clob_market.get('active', False)
            market['closed'] = clob_market.get('closed', False)
            
            # Display info
            print(f"\n📈 Market Details:")
            print(f"   Active: {market['active']}")
            print(f"   Closed: {market['closed']}")
            print(f"   Accepting Orders: {market['accepting_orders']}")
            print(f"   YES: ${market.get('yes_price', 0):.4f}")
            print(f"   NO:  ${market.get('no_price', 0):.4f}")
            
            pair_cost = market.get('yes_price', 0.5) + market.get('no_price', 0.5)
            print(f"   Pair Cost: ${pair_cost:.4f}")
            
            return market
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def trade_pair(self, market: Dict):
        """Execute pair trading on selected market"""
        
        if not market.get('accepting_orders'):
            print("\n⚠️  Market not accepting orders yet!")
            
            wait = input("Wait for market to open? (y/n): ").strip().lower()
            
            if wait == 'y':
                print("⏳ Waiting for market to accept orders...")
                
                while True:
                    time.sleep(10)
                    
                    # Refresh market
                    market = self.get_market_details(market)
                    
                    if not market:
                        print("❌ Could not refresh market")
                        return
                    
                    if market.get('accepting_orders'):
                        print("✅ Market is now accepting orders!")
                        break
                    
                    print("   Still waiting...")
            else:
                return
        
        # Trading loop
        yes_spent = 0.0
        no_spent = 0.0
        
        print("\n" + "="*70)
        print("🚀 STARTING PAIR TRADING")
        print("="*70)
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE TRADING'}")
        print(f"Order Size: ${self.order_size_usd}")
        print(f"Max Per Side: ${self.max_per_side}")
        print("="*70)
        
        try:
            while yes_spent < self.max_per_side or no_spent < self.max_per_side:
                
                # Refresh prices
                market = self.get_market_details(market)
                
                if not market:
                    break
                
                yes_price = market.get('yes_price', 0.5)
                no_price = market.get('no_price', 0.5)
                pair_cost = yes_price + no_price
                
                print(f"\n💹 YES: ${yes_price:.4f} | NO: ${no_price:.4f} | Pair: ${pair_cost:.4f}")
                
                # Check pair cost
                if pair_cost >= self.target_pair_cost:
                    print(f"   ⏸️  Pair cost too high, waiting...")
                    time.sleep(5)
                    continue
                
                print(f"   ✅ Good pair cost!")
                
                # Buy YES
                if yes_spent < self.max_per_side:
                    if self.dry_run:
                        print(f"   🔔 [DRY RUN] Buy YES ${self.order_size_usd} @ ${yes_price:.4f}")
                        yes_spent += self.order_size_usd
                    else:
                        # Real order
                        shares = self.order_size_usd / yes_price
                        
                        order = OrderArgs(
                            price=yes_price,
                            size=shares,
                            side="BUY",
                            token_id=market['yes_token_id']
                        )
                        
                        signed = self.client.create_order(order)
                        resp = self.client.post_order(signed, OrderType.GTC)
                        
                        if resp and resp.get('success'):
                            print(f"   ✅ YES order: {resp.get('orderID')}")
                            yes_spent += self.order_size_usd
                        else:
                            print(f"   ❌ YES order failed")
                
                # Buy NO
                if no_spent < self.max_per_side:
                    if self.dry_run:
                        print(f"   🔔 [DRY RUN] Buy NO ${self.order_size_usd} @ ${no_price:.4f}")
                        no_spent += self.order_size_usd
                    else:
                        # Real order
                        shares = self.order_size_usd / no_price
                        
                        order = OrderArgs(
                            price=no_price,
                            size=shares,
                            side="BUY",
                            token_id=market['no_token_id']
                        )
                        
                        signed = self.client.create_order(order)
                        resp = self.client.post_order(signed, OrderType.GTC)
                        
                        if resp and resp.get('success'):
                            print(f"   ✅ NO order: {resp.get('orderID')}")
                            no_spent += self.order_size_usd
                        else:
                            print(f"   ❌ NO order failed")
                
                print(f"   💰 Spent: YES ${yes_spent:.2f} | NO ${no_spent:.2f}")
                
                # Check if done
                if yes_spent >= self.max_per_side and no_spent >= self.max_per_side:
                    print(f"\n✅ Max budget reached!")
                    break
                
                time.sleep(5)
        
        except KeyboardInterrupt:
            print("\n⚠️  Stopped by user")
        
        # Summary
        print("\n" + "="*70)
        print("📊 TRADING SUMMARY")
        print("="*70)
        print(f"YES Spent: ${yes_spent:.2f}")
        print(f"NO Spent:  ${no_spent:.2f}")
        print(f"Total:     ${yes_spent + no_spent:.2f}")
        print("="*70)
    
    def run(self):
        """Main bot flow"""
        
        print("\n" + "="*70)
        print("🔍 POLYMARKET BOT - SEARCH MODE")
        print("="*70)
        
        # Connect
        self.connect()
        
        # Get search query
        print("\n💡 Examples:")
        print("   - 'BTC 15'")
        print("   - 'Bitcoin 15 minute'")
        print("   - 'Ethereum up or down'")
        
        query = input("\n📝 Enter market search query: ").strip()
        
        if not query:
            print("❌ No query provided")
            return
        
        # Search
        markets = self.search_markets(query)
        
        if not markets:
            print("❌ No markets found. Try different keywords.")
            return
        
        # Select market
        market = self.select_market(markets)
        
        if not market:
            print("❌ No market selected")
            return
        
        # Get details
        market = self.get_market_details(market)
        
        if not market:
            return
        
        # Confirm
        print(f"\n🎯 Ready to trade: {market['question']}")
        
        confirm = input("Start trading? (y/n): ").strip().lower()
        
        if confirm == 'y':
            self.trade_pair(market)
        else:
            print("❌ Cancelled")


def main():
    """Entry point"""
    bot = SearchBasedBot()
    bot.run()


if __name__ == "__main__":
    main()