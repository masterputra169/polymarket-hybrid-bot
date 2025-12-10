"""
Pair Trader V4 - Fixed division by zero & better price fetching
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
        
        # Trading state
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        self.trades = []
        
        # Daily PnL
        self.daily_pnl = 0.0
        self.start_of_day = datetime.now().date()
        
        # API
        self.gamma_url = "https://gamma-api.polymarket.com"
    
    def set_market(self, market: Dict):
        self.market = market
        self.condition_id = market.get('condition_id', '')
        self.slug = market.get('slug', '')
        
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        self.trades = []
        
        print(f"\n💰 Trader initialized for market:")
        print(f"   {market['title']}")
        print(f"   YES token: {market['yes_token_id'][:10]}...")
        print(f"   NO token: {market['no_token_id'][:10]}...")
    
    def _get_live_prices(self) -> Dict:
        """Get live prices with multiple fallbacks"""
        
        # Method 1: Try Gamma API with slug
        if self.slug:
            prices = self._fetch_prices_by_slug()
            if prices and prices['yes'] > 0 and prices['no'] > 0:
                return prices
        
        # Method 2: Try Gamma API with condition_id
        if self.condition_id:
            prices = self._fetch_prices_by_condition()
            if prices and prices['yes'] > 0 and prices['no'] > 0:
                return prices
        
        # Method 3: Fallback to initial market prices
        yes_price = self.market.get('yes_price', 0.5)
        no_price = self.market.get('no_price', 0.5)
        
        # Ensure prices are valid
        if yes_price <= 0:
            yes_price = 0.5
        if no_price <= 0:
            no_price = 0.5
        
        return {'yes': yes_price, 'no': no_price}
    
    def _fetch_prices_by_slug(self) -> Optional[Dict]:
        """Fetch prices using event slug"""
        try:
            url = f"{self.gamma_url}/events/slug/{self.slug}"
            response = requests.get(url, timeout=5)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if isinstance(data, list) and data:
                data = data[0]
            
            markets = data.get('markets', [])
            if not markets:
                return None
            
            market = markets[0]
            return self._parse_prices(market)
            
        except Exception as e:
            return None
    
    def _fetch_prices_by_condition(self) -> Optional[Dict]:
        """Fetch prices using condition_id"""
        try:
            url = f"{self.gamma_url}/markets"
            params = {'condition_id': self.condition_id}
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if isinstance(data, list) and data:
                market = data[0]
            elif isinstance(data, dict):
                market = data
            else:
                return None
            
            return self._parse_prices(market)
            
        except Exception as e:
            return None
    
    def _parse_prices(self, market: Dict) -> Optional[Dict]:
        """Parse prices from market data"""
        try:
            outcome_prices = market.get('outcomePrices')
            
            if outcome_prices is None:
                return None
            
            # Handle string JSON
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
        """Execute one trading cycle"""
        if not self.market:
            return
        
        if self._check_daily_loss_limit():
            print("🛑 Daily loss limit reached")
            return
        
        # Get prices with fallbacks
        prices = self._get_live_prices()
        yes_price = prices['yes']
        no_price = prices['no']
        
        # SAFETY CHECK: Skip if prices are invalid
        if yes_price <= 0.01 or no_price <= 0.01:
            print(f"\n📊 Current State:")
            print(f"   YES: ${yes_price:.4f} | NO: ${no_price:.4f}")
            print(f"   ⚠️ Invalid prices, skipping cycle")
            return
        
        if yes_price >= 0.99 or no_price >= 0.99:
            print(f"\n📊 Current State:")
            print(f"   YES: ${yes_price:.4f} | NO: ${no_price:.4f}")
            print(f"   ⚠️ Market appears settled, skipping")
            return
        
        pair_cost = yes_price + no_price
        
        print(f"\n📊 Current State:")
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
        """Execute a buy order with safety checks"""
        
        # SAFETY: Prevent division by zero
        if price <= 0:
            print(f"   ❌ Invalid price: {price}")
            return
        
        order_size = self.config.ORDER_SIZE_USD
        token_id = self.market['yes_token_id'] if side == 'yes' else self.market['no_token_id']
        
        # SAFETY: Check token_id exists
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