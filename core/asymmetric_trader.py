"""
Asymmetric Trader - Gabagool22's TRUE Strategy
Based on: https://medium.com/@michalstefanow.marek/inside-the-mind-of-a-polymarket-bot-3184e9481f0a

KEY INSIGHT:
Gabagool DOESN'T buy YES+NO together.
He buys them ASYMMETRICALLY - at different timestamps when one side becomes "unusually cheap"

Strategy:
1. Track historical average prices for YES and NO
2. When YES price drops significantly below its average → BUY YES
3. When NO price drops significantly below its average → BUY NO
4. Eventually both sides get filled at cheap prices
5. Guaranteed profit because total spent < $1.00 per matched pair
"""

from typing import Dict, Optional, List
from datetime import datetime
from collections import deque
import statistics
from core.client import PolymarketClient


class AsymmetricTrader:
    """
    Gabagool22's Asymmetric Arbitrage Strategy
    
    Unlike pair trading (buy both at once), this strategy:
    - Buys YES when YES becomes unusually cheap
    - Buys NO when NO becomes unusually cheap
    - Waits for market to temporarily misprice each side
    - Builds position gradually over time
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
        
        # Price history for detecting "cheap" opportunities
        # gabagool looks for prices that are unusually LOW compared to recent history
        self.yes_price_history = deque(maxlen=100)  # Last 100 price samples
        self.no_price_history = deque(maxlen=100)
        
        # Thresholds for what counts as "unusually cheap"
        # If current price is X% below recent average, it's a buy signal
        self.cheap_threshold = float(config.CHEAP_THRESHOLD)  # e.g., 0.05 = 5% below average
        
        # API endpoints
        self.clob_url = "https://clob.polymarket.com"
    
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
    
    def _get_live_prices(self) -> Dict:
        """
        Get real-time prices with smart fallback logic
        
        Priority:
        1. CLOB /price endpoint (most accurate for trading)
        2. CLOB orderbook (if spread is reasonable)
        3. Gamma API prices (last resort)
        """
        import requests
        
        prices = {}
        source = "Unknown"
        
        try:
            # METHOD 1: Try CLOB /price endpoint (BEST for actual trading)
            yes_price_endpoint = None
            no_price_endpoint = None
            
            if self.yes_token_id:
                try:
                    response = requests.get(
                        f"{self.clob_url}/price",
                        params={'token_id': self.yes_token_id, 'side': 'BUY'},
                        timeout=3
                    )
                    if response.status_code == 200:
                        data = response.json()
                        yes_price_endpoint = float(data.get('price', 0))
                except:
                    pass
            
            if self.no_token_id:
                try:
                    response = requests.get(
                        f"{self.clob_url}/price",
                        params={'token_id': self.no_token_id, 'side': 'BUY'},
                        timeout=3
                    )
                    if response.status_code == 200:
                        data = response.json()
                        no_price_endpoint = float(data.get('price', 0))
                except:
                    pass
            
            # If /price endpoint worked for both, use it
            if yes_price_endpoint and no_price_endpoint:
                # Validate prices are reasonable
                if 0.01 < yes_price_endpoint < 0.99 and 0.01 < no_price_endpoint < 0.99:
                    return {
                        'yes': yes_price_endpoint,
                        'no': no_price_endpoint,
                        'source': 'CLOB /price'
                    }
            
            # METHOD 2: Try orderbook (with spread check)
            yes_book_price = None
            no_book_price = None
            
            if self.yes_token_id:
                try:
                    response = requests.get(
                        f"{self.clob_url}/book",
                        params={'token_id': self.yes_token_id},
                        timeout=3
                    )
                    if response.status_code == 200:
                        book = response.json()
                        if book.get('asks'):
                            ask_price = float(book['asks'][0]['price'])
                            # Only use if not extreme
                            if 0.02 < ask_price < 0.98:
                                yes_book_price = ask_price
                except:
                    pass
            
            if self.no_token_id:
                try:
                    response = requests.get(
                        f"{self.clob_url}/book",
                        params={'token_id': self.no_token_id},
                        timeout=3
                    )
                    if response.status_code == 200:
                        book = response.json()
                        if book.get('asks'):
                            ask_price = float(book['asks'][0]['price'])
                            if 0.02 < ask_price < 0.98:
                                no_book_price = ask_price
                except:
                    pass
            
            # If orderbook worked for both, use it
            if yes_book_price and no_book_price:
                return {
                    'yes': yes_book_price,
                    'no': no_book_price,
                    'source': 'CLOB orderbook'
                }
            
            # METHOD 3: Use /price endpoint even if only one side
            # Mix with market data for other side
            if yes_price_endpoint or no_price_endpoint:
                market_yes = float(self.market.get('yes_price', 0.5))
                market_no = float(self.market.get('no_price', 0.5))
                
                return {
                    'yes': yes_price_endpoint if yes_price_endpoint else market_yes,
                    'no': no_price_endpoint if no_price_endpoint else market_no,
                    'source': 'CLOB /price + Gamma'
                }
            
            # METHOD 4: Fallback to Gamma API
            market_yes = float(self.market.get('yes_price', 0.5))
            market_no = float(self.market.get('no_price', 0.5))
            
            # Validate Gamma prices
            if 0.01 < market_yes < 0.99 and 0.01 < market_no < 0.99:
                return {
                    'yes': market_yes,
                    'no': market_no,
                    'source': 'Gamma API'
                }
            
            # METHOD 5: Last resort - default
            return {
                'yes': 0.50,
                'no': 0.50,
                'source': 'Default'
            }
            
        except Exception as e:
            print(f"   ⚠️ Price fetch error: {e}")
            # Final fallback
            return {
                'yes': float(self.market.get('yes_price', 0.50)),
                'no': float(self.market.get('no_price', 0.50)),
                'source': 'Error fallback'
            }
    
    def _is_unusually_cheap(self, current_price: float, price_history: deque) -> bool:
        """
        Determine if current price is "unusually cheap"
        
        gabagool's logic:
        - Track recent price history
        - Calculate average price
        - If current < average * (1 - threshold), it's cheap
        
        Example:
        - Recent avg YES price: $0.50
        - Threshold: 5%
        - Trigger if current < $0.475 (5% below average)
        """
        
        # Need at least 10 samples for reliable average
        if len(price_history) < 10:
            return False
        
        # Calculate recent average
        avg_price = statistics.mean(price_history)
        
        # Calculate threshold price
        threshold_price = avg_price * (1 - self.cheap_threshold)
        
        # Is current price below threshold?
        is_cheap = current_price < threshold_price
        
        if is_cheap:
            drop_pct = ((avg_price - current_price) / avg_price) * 100
            print(f"   🎯 CHEAP DETECTED! Current: ${current_price:.4f} | Avg: ${avg_price:.4f} | Drop: {drop_pct:.1f}%")
        
        return is_cheap
    
    def execute_trading_cycle(self):
        """
        Execute one trading cycle using asymmetric strategy
        
        Logic:
        1. Get current prices
        2. Add to price history
        3. Check if YES is unusually cheap → BUY YES
        4. Check if NO is unusually cheap → BUY NO
        5. Respect position limits
        """
        
        if not self.market:
            return
        
        # Get current prices
        price_data = self._get_live_prices()
        yes_price = price_data['yes']
        no_price = price_data['no']
        source = price_data.get('source', 'Unknown')
        
        # Validate prices
        if yes_price <= 0.01 or no_price <= 0.01:
            print(f"   ⚠️ Invalid prices (too low), skipping")
            return
        
        # Check if market appears settled (one side is extremely high)
        # BUT be more lenient - sometimes markets start at 0.99/0.01
        if yes_price >= 0.99 and no_price <= 0.01:
            print(f"   ⚠️ Market appears settled (YES won), skipping")
            return
        
        if no_price >= 0.99 and yes_price <= 0.01:
            print(f"   ⚠️ Market appears settled (NO won), skipping")
            return
        
        # If both prices are reasonable (0.02 - 0.98), market is active
        # Allow trading even if prices are imbalanced at start
        
        # Add to price history
        self.yes_price_history.append(yes_price)
        self.no_price_history.append(no_price)
        
        # Calculate averages if we have enough history
        yes_avg = statistics.mean(self.yes_price_history) if len(self.yes_price_history) >= 10 else yes_price
        no_avg = statistics.mean(self.no_price_history) if len(self.no_price_history) >= 10 else no_price
        
        print(f"\n📊 Current State [{source}]:")
        print(f"   YES: ${yes_price:.4f} (avg: ${yes_avg:.4f}) | Spent: ${self.yes_spent:.2f}")
        print(f"   NO:  ${no_price:.4f} (avg: ${no_avg:.4f}) | Spent: ${self.no_spent:.2f}")
        
        # Calculate weighted average cost (what we've paid on average)
        if self.yes_spent + self.no_spent > 0:
            min_shares = min(self.yes_shares, self.no_shares)
            total_cost_for_pairs = (self.yes_spent / self.yes_shares * min_shares if self.yes_shares > 0 else 0) + \
                                  (self.no_spent / self.no_shares * min_shares if self.no_shares > 0 else 0)
            avg_pair_cost = total_cost_for_pairs / min_shares if min_shares > 0 else 0
            print(f"   Avg Pair Cost: ${avg_pair_cost:.4f}")
        
        # ASYMMETRIC LOGIC: Check each side independently
        
        # Check YES for unusual cheapness
        if self._should_buy_yes(yes_price):
            if self._is_unusually_cheap(yes_price, self.yes_price_history):
                self._execute_buy('yes', yes_price)
            else:
                # Even if not "unusually cheap", buy if price is good
                # and we're building position
                if len(self.yes_price_history) < 10:  # Early in market
                    if yes_price < 0.50:  # Reasonable price
                        self._execute_buy('yes', yes_price)
        
        # Check NO for unusual cheapness
        if self._should_buy_no(no_price):
            if self._is_unusually_cheap(no_price, self.no_price_history):
                self._execute_buy('no', no_price)
            else:
                # Same logic for NO
                if len(self.no_price_history) < 10:
                    if no_price < 0.50:
                        self._execute_buy('no', no_price)
    
    def _should_buy_yes(self, price: float) -> bool:
        """Check if we should buy YES (position limits, etc.)"""
        
        # Don't buy if already at max position
        if self.yes_spent >= self.config.MAX_PER_SIDE:
            return False
        
        # Don't buy if price is too high
        if price > self.config.MAX_PRICE_YES / 100:
            return False
        
        # STRICT imbalance control for asymmetric
        imbalance = self._calculate_imbalance()
        
        # If we have way more YES than NO, be very strict
        if self.yes_shares > self.no_shares * 1.5:  # 50% more YES than NO
            return False
        
        # If imbalance > 40%, only buy if price is REALLY cheap
        if imbalance > 0.40:
            if self.yes_shares > self.no_shares:
                # Need price to be at least 10% below average
                if len(self.yes_price_history) >= 10:
                    avg = sum(self.yes_price_history) / len(self.yes_price_history)
                    if price >= avg * 0.90:  # Not cheap enough
                        return False
        
        return True
    
    def _should_buy_no(self, price: float) -> bool:
        """Check if we should buy NO (position limits, etc.)"""
        
        if self.no_spent >= self.config.MAX_PER_SIDE:
            return False
        
        if price > self.config.MAX_PRICE_NO / 100:
            return False
        
        # STRICT imbalance control
        imbalance = self._calculate_imbalance()
        
        # If we have way more NO than YES, be very strict
        if self.no_shares > self.yes_shares * 1.5:  # 50% more NO than YES
            return False
        
        # If imbalance > 40%, only buy if price is REALLY cheap
        if imbalance > 0.40:
            if self.no_shares > self.yes_shares:
                # Need price to be at least 10% below average
                if len(self.no_price_history) >= 10:
                    avg = sum(self.no_price_history) / len(self.no_price_history)
                    if price >= avg * 0.90:  # Not cheap enough
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
            
            # Show position summary
            min_shares = min(self.yes_shares, self.no_shares)
            total_spent = self.yes_spent + self.no_spent
            potential_profit = min_shares - total_spent
            
            print(f"   📊 Position: YES ${self.yes_spent:.2f} ({self.yes_shares:.2f} sh) | NO ${self.no_spent:.2f} ({self.no_shares:.2f} sh)")
            print(f"      Min shares: {min_shares:.2f} | Profit: ${potential_profit:.2f}")
            
            # WARNING if position is at loss
            if potential_profit < 0:
                imbalance = self._calculate_imbalance()
                print(f"   ⚠️ WARNING: Position at LOSS! Imbalance: {imbalance*100:.1f}%")
                print(f"      Need to buy more of the other side!")
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


# ==========================================
# TEST
# ==========================================

def test_asymmetric_trader():
    """Test the asymmetric trader logic"""
    
    print("\n🧪 Testing Asymmetric Trader (Gabagool's True Strategy)\n")
    
    class MockConfig:
        ORDER_SIZE_USD = 1.0
        MAX_PER_SIDE = 10.0
        MAX_PRICE_YES = 60.0
        MAX_PRICE_NO = 60.0
        CHEAP_THRESHOLD = 0.05  # 5% below average
        DRY_RUN = True
    
    class MockClient:
        def buy_outcome(self, token_id, usd_amount, max_price):
            return True
    
    trader = AsymmetricTrader(MockClient(), MockConfig())
    
    mock_market = {
        'title': 'BTC Up or Down - Test Market',
        'yes_token_id': 'mock_yes_token',
        'no_token_id': 'mock_no_token',
        'yes_outcome': 'Up',
        'no_outcome': 'Down',
        'yes_price': 0.50,
        'no_price': 0.50
    }
    
    trader.set_market(mock_market)
    
    # Simulate price movements
    print("Simulating 20 price cycles...\n")
    
    import random
    
    for i in range(20):
        # Simulate random price movements
        # Sometimes YES drops, sometimes NO drops
        
        if random.random() < 0.3:  # 30% chance YES drops
            yes_price = 0.45 + random.random() * 0.03  # $0.45-0.48
            no_price = 0.50 + random.random() * 0.05   # $0.50-0.55
        elif random.random() < 0.3:  # 30% chance NO drops
            yes_price = 0.50 + random.random() * 0.05
            no_price = 0.45 + random.random() * 0.03
        else:  # 40% normal fluctuation
            yes_price = 0.48 + random.random() * 0.04
            no_price = 0.48 + random.random() * 0.04
        
        # Update market
        trader.market['yes_price'] = yes_price
        trader.market['no_price'] = no_price
        
        print(f"Cycle {i+1}/20:")
        trader.execute_trading_cycle()
        print()
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL RESULTS:")
    print("="*60)
    pos = trader.get_current_position()
    
    for key, value in pos.items():
        print(f"   {key}: {value}")
    
    print(f"\n   Total trades: {len(trader.get_trades())}")
    
    yes_trades = [t for t in trader.get_trades() if t['side'] == 'YES']
    no_trades = [t for t in trader.get_trades() if t['side'] == 'NO']
    
    print(f"   YES trades: {len(yes_trades)}")
    print(f"   NO trades: {len(no_trades)}")
    
    if yes_trades:
        avg_yes = sum(t['price'] for t in yes_trades) / len(yes_trades)
        print(f"   Avg YES price: ${avg_yes:.4f}")
    
    if no_trades:
        avg_no = sum(t['price'] for t in no_trades) / len(no_trades)
        print(f"   Avg NO price: ${avg_no:.4f}")


if __name__ == "__main__":
    test_asymmetric_trader()