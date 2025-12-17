"""
Asymmetric Trader - HYBRID REAL-TIME VERSION
Combines CLOB orderbook (best) with fallback methods
Based on both official examples and spike bot patterns
"""

from typing import Dict, Optional, List
from datetime import datetime
from collections import deque
import statistics
import requests
from core.client import PolymarketClient


class AsymmetricTrader:
    """
    Gabagool22's Asymmetric Arbitrage Strategy - HYBRID REAL-TIME
    
    Price fetching priority:
    1. CLOB orderbook (most accurate, < 1s latency)
    2. CLOB /price endpoint (backup)
    3. Positions API (fallback for our own positions)
    """
    
    def __init__(self, client: PolymarketClient, config):
        self.client = client
        self.config = config
        
        # Market info
        self.market = None
        self.yes_token_id = None
        self.no_token_id = None
        
        # Position tracking
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        self.trades = []
        
        # Price history
        self.yes_price_history = deque(maxlen=100)
        self.no_price_history = deque(maxlen=100)
        
        # Thresholds
        self.cheap_threshold = float(config.CHEAP_THRESHOLD)
        
        # API endpoints
        self.clob_url = "https://clob.polymarket.com"
        self.data_api = "https://data-api.polymarket.com"
    
    def set_market(self, market: Dict):
        """Initialize for a new market"""
        self.market = market
        self.yes_token_id = market.get('yes_token_id', '')
        self.no_token_id = market.get('no_token_id', '')
        
        # Reset state
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        self.trades = []
        self.yes_price_history.clear()
        self.no_price_history.clear()
        
        print(f"\n💰 Asymmetric Trader initialized")
        print(f"   Market: {market['title'][:60]}...")
        print(f"   Strategy: Buy when unusually cheap (>{self.cheap_threshold*100}% below avg)")
    
    def _get_price_via_clob_orderbook(self, token_id: str) -> Optional[float]:
        """
        Method 1: Get price from CLOB orderbook (BEST - most accurate)
        """
        try:
            book = self.client.get_orderbook(token_id)
            
            if not book:
                return None
            
            # Get best ask
            if hasattr(book, 'asks') and book.asks:
                best_ask = book.asks[0]
                
                if isinstance(best_ask, dict):
                    price = float(best_ask.get('price', 0))
                elif hasattr(best_ask, 'price'):
                    price = float(best_ask.price)
                else:
                    return None
                
                if 0.01 < price < 0.99:
                    return price
            
            return None
            
        except Exception:
            return None
    
    def _get_price_via_clob_endpoint(self, token_id: str) -> Optional[float]:
        """
        Method 2: Get price from CLOB /price endpoint (backup)
        """
        try:
            response = requests.get(
                f"{self.clob_url}/price",
                params={'token_id': token_id, 'side': 'BUY'},
                timeout=3
            )
            
            if response.status_code == 200:
                data = response.json()
                price = float(data.get('price', 0))
                
                if 0.01 < price < 0.99:
                    return price
            
            return None
            
        except Exception:
            return None
    
    def _get_live_prices(self) -> Dict:
        """
        Get REAL-TIME prices with smart fallback
        
        Priority:
        1. CLOB orderbook (best - actual trading prices)
        2. CLOB /price endpoint (good - calculated prices)
        3. Skip cycle if both fail (safer than stale data)
        """
        
        yes_price = None
        no_price = None
        source = "Unknown"
        
        # Try Method 1: CLOB Orderbook
        yes_price = self._get_price_via_clob_orderbook(self.yes_token_id)
        no_price = self._get_price_via_clob_orderbook(self.no_token_id)
        
        if yes_price and no_price:
            source = "CLOB Orderbook"
        else:
            # Try Method 2: CLOB /price endpoint
            if not yes_price:
                yes_price = self._get_price_via_clob_endpoint(self.yes_token_id)
            if not no_price:
                no_price = self._get_price_via_clob_endpoint(self.no_token_id)
            
            if yes_price and no_price:
                source = "CLOB Price API"
        
        # If we still don't have both prices, return error
        if not yes_price or not no_price:
            return {
                'yes': 0.0,
                'no': 0.0,
                'source': 'Failed',
                'error': True
            }
        
        return {
            'yes': yes_price,
            'no': no_price,
            'source': source,
            'error': False
        }
    
    def _verify_execution_price(self, token_id: str, expected_price: float) -> Optional[float]:
        """
        Double-check price right before order execution
        """
        # Try orderbook first
        real_price = self._get_price_via_clob_orderbook(token_id)
        
        # Fallback to /price endpoint
        if real_price is None:
            real_price = self._get_price_via_clob_endpoint(token_id)
        
        if real_price is None:
            print(f"   ⚠️ Could not verify price (no data available)")
            return None
        
        # Check if price moved too much
        price_diff = abs(real_price - expected_price) / expected_price
        
        if price_diff > 0.15:  # 15% tolerance
            print(f"   ⚠️ PRICE MOVED TOO MUCH!")
            print(f"      Expected: ${expected_price:.4f}")
            print(f"      Actual:   ${real_price:.4f}")
            print(f"      Diff:     {price_diff*100:.1f}%")
            return None
        
        return real_price
    
    def _is_unusually_cheap(self, current_price: float, price_history: deque) -> bool:
        """Determine if current price is unusually cheap"""
        
        if len(price_history) < 10:
            return False
        
        avg_price = statistics.mean(price_history)
        threshold_price = avg_price * (1 - self.cheap_threshold)
        is_cheap = current_price < threshold_price
        
        if is_cheap:
            drop_pct = ((avg_price - current_price) / avg_price) * 100
            print(f"   🎯 CHEAP DETECTED! Current: ${current_price:.4f} | Avg: ${avg_price:.4f} | Drop: {drop_pct:.1f}%")
        
        return is_cheap
    
    def execute_trading_cycle(self):
        """Execute one trading cycle"""
        
        if not self.market:
            return
        
        # Get current prices
        price_data = self._get_live_prices()
        
        # If prices unavailable, skip cycle
        if price_data.get('error', False):
            print(f"\n📊 Current State: PRICE DATA UNAVAILABLE")
            print(f"   ⚠️ Skipping cycle (waiting for orderbook)")
            return
        
        yes_price = price_data['yes']
        no_price = price_data['no']
        source = price_data.get('source', 'Unknown')
        
        # Validate prices
        if yes_price <= 0.01 or no_price <= 0.01:
            print(f"\n📊 Current State [{source}]:")
            print(f"   YES: ${yes_price:.4f} | NO: ${no_price:.4f}")
            print(f"   ⚠️ Invalid prices, skipping")
            return
        
        # Skip if market too lopsided (>95%)
        if yes_price >= 0.95 or no_price >= 0.95:
            print(f"\n📊 Current State [{source}]:")
            print(f"   YES: ${yes_price:.4f} | NO: ${no_price:.4f}")
            print(f"   ⚠️ Market heavily lopsided, skipping pair trading")
            return
        
        # Skip if market imbalanced (>80%)
        if yes_price >= 0.80 or no_price >= 0.80:
            print(f"\n📊 Current State [{source}]:")
            print(f"   YES: ${yes_price:.4f} | NO: ${no_price:.4f}")
            print(f"   ⚠️ Market too imbalanced, waiting for sniping mode")
            return
        
        # Add to history
        self.yes_price_history.append(yes_price)
        self.no_price_history.append(no_price)
        
        # Calculate averages
        yes_avg = statistics.mean(self.yes_price_history) if len(self.yes_price_history) >= 10 else yes_price
        no_avg = statistics.mean(self.no_price_history) if len(self.no_price_history) >= 10 else no_price
        
        print(f"\n📊 Current State [{source}]:")
        print(f"   YES: ${yes_price:.4f} (avg: ${yes_avg:.4f}) | Spent: ${self.yes_spent:.2f}")
        print(f"   NO:  ${no_price:.4f} (avg: ${no_avg:.4f}) | Spent: ${self.no_spent:.2f}")
        
        # Show average pair cost
        if self.yes_spent + self.no_spent > 0:
            min_shares = min(self.yes_shares, self.no_shares)
            if min_shares > 0:
                yes_cost_per_pair = (self.yes_spent / self.yes_shares * min_shares) if self.yes_shares > 0 else 0
                no_cost_per_pair = (self.no_spent / self.no_shares * min_shares) if self.no_shares > 0 else 0
                avg_pair_cost = (yes_cost_per_pair + no_cost_per_pair) / min_shares
                print(f"   Avg Pair Cost: ${avg_pair_cost:.4f}")
        
        # ASYMMETRIC LOGIC
        
        # Check YES
        if self._should_buy_yes(yes_price):
            if len(self.yes_price_history) < 10:
                if yes_price < 0.50:
                    self._execute_buy('yes', yes_price)
            else:
                if self._is_unusually_cheap(yes_price, self.yes_price_history):
                    self._execute_buy('yes', yes_price)
        
        # Check NO
        if self._should_buy_no(no_price):
            if len(self.no_price_history) < 10:
                if no_price < 0.50:
                    self._execute_buy('no', no_price)
            else:
                if self._is_unusually_cheap(no_price, self.no_price_history):
                    self._execute_buy('no', no_price)
    
    def _should_buy_yes(self, price: float) -> bool:
        """Check if we should buy YES"""
        
        if self.yes_spent >= self.config.MAX_PER_SIDE:
            return False
        
        if price > self.config.MAX_PRICE_YES / 100:
            return False
        
        imbalance = self._calculate_imbalance()
        
        if self.yes_shares > self.no_shares * 1.5:
            return False
        
        if imbalance > 0.40 and self.yes_shares > self.no_shares:
            if len(self.yes_price_history) >= 10:
                avg = sum(self.yes_price_history) / len(self.yes_price_history)
                if price >= avg * 0.85:
                    return False
        
        return True
    
    def _should_buy_no(self, price: float) -> bool:
        """Check if we should buy NO"""
        
        if self.no_spent >= self.config.MAX_PER_SIDE:
            return False
        
        if price > self.config.MAX_PRICE_NO / 100:
            return False
        
        imbalance = self._calculate_imbalance()
        
        if self.no_shares > self.yes_shares * 1.5:
            return False
        
        if imbalance > 0.40 and self.no_shares > self.yes_shares:
            if len(self.no_price_history) >= 10:
                avg = sum(self.no_price_history) / len(self.no_price_history)
                if price >= avg * 0.85:
                    return False
        
        return True
    
    def _execute_buy(self, side: str, price: float):
        """Execute buy order with real-time verification"""
        
        if price <= 0:
            print(f"   ❌ Invalid price: {price}")
            return
        
        token_id = self.yes_token_id if side == 'yes' else self.no_token_id
        
        if not token_id:
            print(f"   ❌ Missing token ID for {side}")
            return
        
        # Verify price right before ordering
        real_price = self._verify_execution_price(token_id, price)
        
        if real_price is None:
            print(f"   ❌ Price verification failed, skipping order")
            return
        
        price = real_price
        order_size = self.config.ORDER_SIZE_USD
        shares = order_size / price
        
        print(f"   🔵 BUYING {side.upper()}: {shares:.2f} shares @ ${price:.4f}")
        print(f"      Reason: Unusually cheap opportunity detected")
        
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
            
            # Show position
            min_shares = min(self.yes_shares, self.no_shares)
            total_spent = self.yes_spent + self.no_spent
            potential_profit = min_shares - total_spent
            
            print(f"   📊 Position: YES ${self.yes_spent:.2f} ({self.yes_shares:.2f} sh) | NO ${self.no_spent:.2f} ({self.no_shares:.2f} sh)")
            print(f"      Min shares: {min_shares:.2f} | Profit: ${potential_profit:.2f}")
            
            if potential_profit < 0:
                imbalance = self._calculate_imbalance()
                print(f"   ⚠️ WARNING: Position at LOSS! Imbalance: {imbalance*100:.1f}%")
        else:
            print(f"   ❌ Order failed")
    
    def _calculate_imbalance(self) -> float:
        """Calculate position imbalance"""
        total = self.yes_shares + self.no_shares
        if total == 0:
            return 0.0
        return abs(self.yes_shares - self.no_shares) / total
    
    def get_current_position(self) -> Dict:
        """Get current position summary"""
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
    
    def get_trades(self) -> List[Dict]:
        """Get all trades"""
        return self.trades
    
    def cleanup(self):
        """Cleanup and print final summary"""
        print("\n💰 Asymmetric Trader cleanup...")
        pos = self.get_current_position()
        print(f"   Final position:")
        print(f"   YES: {pos['yes_shares']:.2f} shares (${pos['yes_spent']:.2f})")
        print(f"   NO: {pos['no_shares']:.2f} shares (${pos['no_spent']:.2f})")
        print(f"   Min shares: {pos['min_shares']:.2f}")
        print(f"   Potential profit: ${pos['potential_profit']:.2f} ({pos['profit_margin']:.2f}%)")