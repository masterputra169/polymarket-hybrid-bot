"""
Pair Trader V5 - Uses CLOB Orderbook for Real-Time Prices
Fixes issue where Gamma API returns stale/mid prices instead of actual trading prices
"""
from typing import Optional, Dict
from datetime import datetime
from core.client import PolymarketClient
import requests
import json


class PairTrader:
    def __init__(self, client: PolymarketClient, config):
        self.client = client
        self.config = config
        
        self.market = None
        self.condition_id = None
        self.slug = None
        
        # Token IDs for orderbook lookup
        self.yes_token_id = None
        self.no_token_id = None
        
        # Trading state
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        self.trades = []
        
        # Daily PnL
        self.daily_pnl = 0.0
        self.start_of_day = datetime.now().date()
        
        # API endpoints
        self.clob_url = "https://clob.polymarket.com"
        self.gamma_url = "https://gamma-api.polymarket.com"
    
    def set_market(self, market: Dict):
        self.market = market
        self.condition_id = market.get('condition_id', '')
        self.slug = market.get('slug', '')
        self.yes_token_id = market.get('yes_token_id', '')
        self.no_token_id = market.get('no_token_id', '')
        
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        self.trades = []
        
        print(f"\n💰 Trader initialized for market:")
        print(f"   {market['title']}")
        print(f"   YES token: {self.yes_token_id[:20]}...")
        print(f"   NO token: {self.no_token_id[:20]}...")
    
    def _get_live_prices(self) -> Dict:
        """
        Get REAL-TIME prices from CLOB orderbook
        This gets actual trading prices (best ask), not mid-prices
        """
        
        yes_price = 0.5
        no_price = 0.5
        
        # Method 1: CLOB Orderbook (most accurate)
        if self.yes_token_id and self.no_token_id:
            clob_prices = self._fetch_clob_orderbook_prices()
            if clob_prices:
                yes_price = clob_prices.get('yes', 0.5)
                no_price = clob_prices.get('no', 0.5)
                
                # Validate prices are reasonable
                if 0.01 < yes_price < 0.99 and 0.01 < no_price < 0.99:
                    return {'yes': yes_price, 'no': no_price, 'source': 'CLOB'}
        
        # Method 2: Gamma API (fallback - less accurate)
        gamma_prices = self._fetch_gamma_prices()
        if gamma_prices:
            return {**gamma_prices, 'source': 'Gamma'}
        
        # Method 3: Initial market prices (last resort)
        return {
            'yes': self.market.get('yes_price', 0.5),
            'no': self.market.get('no_price', 0.5),
            'source': 'Cache'
        }
    
    def _fetch_clob_orderbook_prices(self) -> Optional[Dict]:
        """
        Fetch BEST ASK prices from CLOB orderbook
        This is the actual price you'd pay to buy
        """
        try:
            prices = {}
            
            # Debug: Print token IDs being used
            if not self.yes_token_id or not self.no_token_id:
                print(f"   ⚠️ Missing token IDs!")
                return None
            
            # Get YES orderbook
            yes_book = self._get_orderbook(self.yes_token_id)
            if yes_book:
                asks = yes_book.get('asks', [])
                bids = yes_book.get('bids', [])
                
                if asks:
                    prices['yes'] = float(asks[0].get('price', 0.5))
                elif bids:
                    # If no asks, use best bid + small premium
                    prices['yes'] = float(bids[0].get('price', 0.5))
            
            # Get NO orderbook  
            no_book = self._get_orderbook(self.no_token_id)
            if no_book:
                asks = no_book.get('asks', [])
                bids = no_book.get('bids', [])
                
                if asks:
                    prices['no'] = float(asks[0].get('price', 0.5))
                elif bids:
                    prices['no'] = float(bids[0].get('price', 0.5))
            
            if 'yes' in prices and 'no' in prices:
                return prices
            
            # If orderbook failed, try /price endpoint as backup
            return self._fetch_clob_price_endpoint()
            
        except Exception as e:
            print(f"   ⚠️ CLOB orderbook error: {e}")
            return None
    
    def _fetch_clob_price_endpoint(self) -> Optional[Dict]:
        """Backup: Use CLOB /price endpoint"""
        try:
            prices = {}
            
            # Get YES price
            response = requests.get(
                f"{self.clob_url}/price",
                params={'token_id': self.yes_token_id, 'side': 'BUY'},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                prices['yes'] = float(data.get('price', 0.5))
            
            # Get NO price
            response = requests.get(
                f"{self.clob_url}/price",
                params={'token_id': self.no_token_id, 'side': 'BUY'},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                prices['no'] = float(data.get('price', 0.5))
            
            if 'yes' in prices and 'no' in prices:
                return prices
            
            return None
            
        except Exception as e:
            return None
    
    def _get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook for a specific token"""
        try:
            url = f"{self.clob_url}/book"
            params = {'token_id': token_id}
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code != 200:
                return None
            
            return response.json()
            
        except Exception as e:
            return None
    
    def _fetch_gamma_prices(self) -> Optional[Dict]:
        """Fallback: Fetch prices from Gamma API"""
        try:
            # Try by slug first
            if self.slug:
                url = f"{self.gamma_url}/events/slug/{self.slug}"
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data:
                        data = data[0]
                    
                    markets = data.get('markets', [])
                    if markets:
                        return self._parse_gamma_prices(markets[0])
            
            # Try by condition_id
            if self.condition_id:
                url = f"{self.gamma_url}/markets"
                params = {'condition_id': self.condition_id}
                response = requests.get(url, params=params, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data:
                        return self._parse_gamma_prices(data[0])
            
            return None
            
        except Exception as e:
            return None
    
    def _parse_gamma_prices(self, market: Dict) -> Optional[Dict]:
        """Parse prices from Gamma market data"""
        try:
            outcome_prices = market.get('outcomePrices')
            
            if outcome_prices is None:
                return None
            
            if isinstance(outcome_prices, str):
                try:
                    outcome_prices = json.loads(outcome_prices.replace("'", '"'))
                except:
                    return None
            
            if not isinstance(outcome_prices, list) or len(outcome_prices) < 2:
                return None
            
            yes_price = float(outcome_prices[0])
            no_price = float(outcome_prices[1])
            
            # Check for swapped outcomes
            outcomes = market.get('outcomes', [])
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes.replace("'", '"'))
                except:
                    outcomes = []
            
            if outcomes and len(outcomes) >= 2:
                if 'down' in str(outcomes[0]).lower():
                    yes_price, no_price = no_price, yes_price
            
            return {'yes': yes_price, 'no': no_price}
            
        except:
            return None
    
    def execute_trading_cycle(self):
        """Execute one trading cycle with REAL orderbook prices"""
        if not self.market:
            return
        
        if self._check_daily_loss_limit():
            print("🛑 Daily loss limit reached")
            return
        
        # Get REAL prices from orderbook
        prices = self._get_live_prices()
        yes_price = prices['yes']
        no_price = prices['no']
        source = prices.get('source', 'Unknown')
        
        # SAFETY CHECK: Skip if prices are invalid
        if yes_price <= 0.01 or no_price <= 0.01:
            print(f"\n📊 Current State [{source}]:")
            print(f"   YES: ${yes_price:.4f} | NO: ${no_price:.4f}")
            print(f"   ⚠️ Invalid prices, skipping cycle")
            return
        
        if yes_price >= 0.99 or no_price >= 0.99:
            print(f"\n📊 Current State [{source}]:")
            print(f"   YES: ${yes_price:.4f} | NO: ${no_price:.4f}")
            print(f"   ⚠️ Market appears settled, skipping")
            return
        
        pair_cost = yes_price + no_price
        
        print(f"\n📊 Current State [{source}]:")
        print(f"   YES: ${yes_price:.4f} | Spent: ${self.yes_spent:.2f}")
        print(f"   NO:  ${no_price:.4f} | Spent: ${self.no_spent:.2f}")
        print(f"   Pair Cost: ${pair_cost:.4f}")
        
        if pair_cost >= self.config.TARGET_PAIR_COST:
            print(f"   ⏸️  Pair cost too high (>= ${self.config.TARGET_PAIR_COST})")
            return
        
        print(f"   ✅ Good pair cost (< ${self.config.TARGET_PAIR_COST})")
        
        if self._should_buy_yes(yes_price):
            self._execute_buy('yes', yes_price)
        
        if self._should_buy_no(no_price):
            self._execute_buy('no', no_price)
    
    def _should_buy_yes(self, price: float) -> bool:
        if price <= 0.01 or price >= 0.99:
            return False
        if self.yes_spent >= self.config.MAX_PER_SIDE:
            return False
        if price > self.config.MAX_PRICE_YES / 100:
            return False
        if self._calculate_imbalance() > self.config.MAX_IMBALANCE:
            if self.yes_shares > self.no_shares:
                return False
        return True
    
    def _should_buy_no(self, price: float) -> bool:
        if price <= 0.01 or price >= 0.99:
            return False
        if self.no_spent >= self.config.MAX_PER_SIDE:
            return False
        if price > self.config.MAX_PRICE_NO / 100:
            return False
        if self._calculate_imbalance() > self.config.MAX_IMBALANCE:
            if self.no_shares > self.yes_shares:
                return False
        return True
    
    def _execute_buy(self, side: str, price: float):
        """Execute a buy order"""
        
        if price <= 0:
            print(f"   ❌ Invalid price: {price}")
            return
        
        order_size = self.config.ORDER_SIZE_USD
        token_id = self.yes_token_id if side == 'yes' else self.no_token_id
        
        if not token_id:
            print(f"   ❌ Missing token ID for {side}")
            return
        
        shares = order_size / price
        
        print(f"   🔵 Buying {side.upper()}: {shares:.2f} shares @ ${price:.4f}")
        
        if self.config.DRY_RUN:
            print(f"   🔔 DRY RUN - simulating order")
            success = True
        else:
            success = self.client.buy_outcome(
                token_id=token_id,
                usd_amount=order_size,
                max_price=price * 1.02
            )
        
        if success:
            if side == 'yes':
                self.yes_spent += order_size
                self.yes_shares += shares
            else:
                self.no_spent += order_size
                self.no_shares += shares
            
            self.trades.append({
                'timestamp': datetime.now().timestamp(),
                'side': side.upper(),
                'type': 'BUY',
                'outcome': self.market['yes_outcome'] if side == 'yes' else self.market['no_outcome'],
                'price': price,
                'size': shares,
                'cost': order_size,
                'dry_run': self.config.DRY_RUN
            })
            
            status = 'simulated' if self.config.DRY_RUN else 'executed'
            print(f"   ✅ Order {status}")
            print(f"   📊 Total: YES ${self.yes_spent:.2f} | NO ${self.no_spent:.2f}")
        else:
            print(f"   ❌ Order failed")
    
    def _calculate_imbalance(self) -> float:
        total = self.yes_shares + self.no_shares
        if total == 0:
            return 0.0
        return abs(self.yes_shares - self.no_shares) / total
    
    def _check_daily_loss_limit(self) -> bool:
        today = datetime.now().date()
        if today != self.start_of_day:
            self.daily_pnl = 0.0
            self.start_of_day = today
        return self.daily_pnl < -self.config.MAX_DAILY_LOSS
    
    def get_current_position(self) -> Dict:
        total_spent = self.yes_spent + self.no_spent
        min_shares = min(self.yes_shares, self.no_shares)
        guaranteed_value = min_shares * 1.0
        potential_profit = guaranteed_value - total_spent
        
        return {
            'yes_spent': self.yes_spent,
            'no_spent': self.no_spent,
            'total_spent': total_spent,
            'yes_shares': self.yes_shares,
            'no_shares': self.no_shares,
            'min_shares': min_shares,
            'guaranteed_value': guaranteed_value,
            'potential_profit': potential_profit,
            'profit_margin': (potential_profit / total_spent * 100) if total_spent > 0 else 0,
            'imbalance': self._calculate_imbalance()
        }
    
    def get_trades(self) -> list:
        return self.trades
    
    def cleanup(self):
        print("\n💰 Trader cleanup...")
        pos = self.get_current_position()
        print(f"   Final position:")
        print(f"   YES: {pos['yes_shares']:.2f} shares (${pos['yes_spent']:.2f})")
        print(f"   NO: {pos['no_shares']:.2f} shares (${pos['no_spent']:.2f})")
        print(f"   Min shares: {pos['min_shares']:.2f}")
        print(f"   Potential profit: ${pos['potential_profit']:.2f}")


# ==========================================
# TEST: Verify orderbook prices work
# ==========================================

def test_orderbook_prices():
    """Test fetching real orderbook prices"""
    print("\n🧪 Testing CLOB Orderbook Price Fetching\n")
    
    # You need real token IDs for this test
    # These are example token IDs - replace with actual ones
    
    clob_url = "https://clob.polymarket.com"
    
    # First, let's find a real market
    import requests
    
    gamma_url = "https://gamma-api.polymarket.com"
    
    try:
        # Get BTC markets
        response = requests.get(
            f"{gamma_url}/markets",
            params={'limit': 10, 'closed': 'false', 'active': 'true'},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch markets: {response.status_code}")
            return
        
        markets = response.json()
        
        # Find BTC updown market
        for market in markets:
            slug = market.get('slug', '').lower()
            if 'btc-updown' in slug:
                print(f"Found market: {market.get('question', 'Unknown')[:60]}")
                print(f"Slug: {slug}")
                
                # Get token IDs
                clob_token_ids = market.get('clobTokenIds')
                if isinstance(clob_token_ids, str):
                    import json
                    clob_token_ids = json.loads(clob_token_ids.replace("'", '"'))
                
                if clob_token_ids and len(clob_token_ids) >= 2:
                    yes_token = clob_token_ids[0]
                    no_token = clob_token_ids[1]
                    
                    print(f"\nYES Token: {yes_token[:30]}...")
                    print(f"NO Token: {no_token[:30]}...")
                    
                    # Get orderbook for YES
                    print(f"\n📖 Fetching YES orderbook...")
                    yes_book = requests.get(
                        f"{clob_url}/book",
                        params={'token_id': yes_token},
                        timeout=5
                    ).json()
                    
                    if yes_book.get('asks'):
                        best_ask = float(yes_book['asks'][0]['price'])
                        print(f"   Best ASK (buy price): ${best_ask:.4f}")
                    else:
                        print(f"   No asks in orderbook")
                    
                    if yes_book.get('bids'):
                        best_bid = float(yes_book['bids'][0]['price'])
                        print(f"   Best BID (sell price): ${best_bid:.4f}")
                    
                    # Get orderbook for NO
                    print(f"\n📖 Fetching NO orderbook...")
                    no_book = requests.get(
                        f"{clob_url}/book",
                        params={'token_id': no_token},
                        timeout=5
                    ).json()
                    
                    if no_book.get('asks'):
                        best_ask = float(no_book['asks'][0]['price'])
                        print(f"   Best ASK (buy price): ${best_ask:.4f}")
                    else:
                        print(f"   No asks in orderbook")
                    
                    if no_book.get('bids'):
                        best_bid = float(no_book['bids'][0]['price'])
                        print(f"   Best BID (sell price): ${best_bid:.4f}")
                    
                    # Compare with Gamma prices
                    outcome_prices = market.get('outcomePrices')
                    if isinstance(outcome_prices, str):
                        outcome_prices = json.loads(outcome_prices.replace("'", '"'))
                    
                    if outcome_prices:
                        print(f"\n📊 Gamma API prices (may be stale):")
                        print(f"   YES: ${float(outcome_prices[0]):.4f}")
                        print(f"   NO: ${float(outcome_prices[1]):.4f}")
                    
                    break
        
        print("\n✅ Test complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_orderbook_prices()