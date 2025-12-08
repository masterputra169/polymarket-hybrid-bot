"""
Pair Trader Module
Implements gabagool22's pair trading strategy
"""
from typing import Optional, Dict
from datetime import datetime
from core.client import PolymarketClient


class PairTrader:
    """
    Pair trading strategy:
    - Buy both YES and NO when pair cost < target
    - Multiple small orders ($0.50-$1.00 each)
    - Max $10 per side (total $20 exposure)
    - Maintain balance between YES/NO
    """
    
    def __init__(self, client: PolymarketClient, config):
        """
        Initialize trader
        
        Args:
            client: Polymarket client instance
            config: Bot configuration
        """
        self.client = client
        self.config = config
        
        # Current market
        self.market = None
        
        # Trading state
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        
        # Trade history
        self.trades = []
        
        # Daily PnL tracking
        self.daily_pnl = 0.0
        self.start_of_day = datetime.now().date()
    
    def set_market(self, market: Dict):
        """
        Set the market to trade on
        
        Args:
            market: Market info dict from MarketFinder
        """
        self.market = market
        
        # Reset state for new market
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        self.trades = []
        
        print(f"\n💰 Trader initialized for market:")
        print(f"   {market['title']}")
        print(f"   YES token: {market['yes_token_id'][:10]}...")
        print(f"   NO token: {market['no_token_id'][:10]}...")
    
    def execute_trading_cycle(self):
        """
        Execute one trading cycle
        
        This is called every POLLING_INTERVAL seconds
        Checks if conditions are good and places orders
        """
        if not self.market:
            return
        
        # 1. Check daily loss limit
        if self._check_daily_loss_limit():
            print("🛑 Daily loss limit reached - stopping trades")
            return
        
        # 2. Get current prices
        yes_price = self._get_current_price('yes')
        no_price = self._get_current_price('no')
        
        if yes_price is None or no_price is None:
            print("⚠️ Could not get prices")
            return
        
        # 3. Calculate pair cost
        pair_cost = yes_price + no_price
        
        print(f"\n📊 Current State:")
        print(f"   YES: ${yes_price:.4f} | Spent: ${self.yes_spent:.2f}")
        print(f"   NO:  ${no_price:.4f} | Spent: ${self.no_spent:.2f}")
        print(f"   Pair Cost: ${pair_cost:.4f}")
        
        # 4. Check if pair cost is attractive
        if pair_cost >= self.config.TARGET_PAIR_COST:
            print(f"   ⏸️  Pair cost too high (>= ${self.config.TARGET_PAIR_COST})")
            return
        
        print(f"   ✅ Good pair cost (< ${self.config.TARGET_PAIR_COST})")
        
        # 5. Check if we should buy YES
        if self._should_buy_yes(yes_price):
            self._execute_buy('yes', yes_price)
        
        # 6. Check if we should buy NO
        if self._should_buy_no(no_price):
            self._execute_buy('no', no_price)
    
    def _should_buy_yes(self, price: float) -> bool:
        """Check if we should buy YES"""
        
        # Check budget
        if self.yes_spent >= self.config.MAX_PER_SIDE:
            return False
        
        # Check price limit
        if price > self.config.MAX_PRICE_YES / 100:  # Convert cents to dollars
            return False
        
        # Check imbalance
        if self._calculate_imbalance() > self.config.MAX_IMBALANCE:
            # Only buy YES if we have more NO
            if self.yes_shares > self.no_shares:
                return False
        
        return True
    
    def _should_buy_no(self, price: float) -> bool:
        """Check if we should buy NO"""
        
        # Check budget
        if self.no_spent >= self.config.MAX_PER_SIDE:
            return False
        
        # Check price limit
        if price > self.config.MAX_PRICE_NO / 100:  # Convert cents to dollars
            return False
        
        # Check imbalance
        if self._calculate_imbalance() > self.config.MAX_IMBALANCE:
            # Only buy NO if we have more YES
            if self.no_shares > self.yes_shares:
                return False
        
        return True
    
    def _execute_buy(self, side: str, price: float):
        """
        Execute a buy order
        
        Args:
            side: 'yes' or 'no'
            price: Current price
        """
        # Determine order size
        order_size = self.config.ORDER_SIZE_USD
        
        # Get token ID
        token_id = self.market['yes_token_id'] if side == 'yes' else self.market['no_token_id']
        
        # Calculate shares
        shares = order_size / price
        
        print(f"   🔵 Buying {side.upper()}: {shares:.2f} shares @ ${price:.4f}")
        
        # Execute order
        success = self.client.buy_outcome(
            token_id=token_id,
            usd_amount=order_size,
            max_price=price * 1.02  # Allow 2% slippage
        )
        
        if success:
            # Update state
            if side == 'yes':
                self.yes_spent += order_size
                self.yes_shares += shares
            else:
                self.no_spent += order_size
                self.no_shares += shares
            
            # Record trade
            trade = {
                'timestamp': datetime.now().timestamp(),
                'side': side.upper(),
                'type': 'BUY',
                'outcome': self.market['yes_outcome'] if side == 'yes' else self.market['no_outcome'],
                'price': price,
                'size': shares,
                'cost': order_size,
                'title': self.market['title'],
                'conditionId': self.market['condition_id']
            }
            self.trades.append(trade)
            
            print(f"   ✅ Order executed successfully")
            print(f"   📊 Total spent: YES ${self.yes_spent:.2f} | NO ${self.no_spent:.2f}")
        else:
            print(f"   ❌ Order failed")
    
    def _get_current_price(self, side: str) -> Optional[float]:
        """Get current price for YES or NO"""
        try:
            if side == 'yes':
                token_id = self.market['yes_token_id']
            else:
                token_id = self.market['no_token_id']
            
            price = self.client.get_mid_price(token_id)
            return price
            
        except Exception as e:
            print(f"⚠️ Error getting {side} price: {e}")
            return None
    
    def _calculate_imbalance(self) -> float:
        """
        Calculate position imbalance
        
        Returns:
            Imbalance ratio (0 = perfectly balanced, 1 = completely imbalanced)
        """
        total_shares = self.yes_shares + self.no_shares
        
        if total_shares == 0:
            return 0.0
        
        difference = abs(self.yes_shares - self.no_shares)
        imbalance = difference / total_shares
        
        return imbalance
    
    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit exceeded"""
        today = datetime.now().date()
        
        # Reset if new day
        if today != self.start_of_day:
            self.daily_pnl = 0.0
            self.start_of_day = today
        
        # Check limit
        return self.daily_pnl < -self.config.MAX_DAILY_LOSS
    
    def get_current_position(self) -> Dict:
        """Get current position summary"""
        total_spent = self.yes_spent + self.no_spent
        min_shares = min(self.yes_shares, self.no_shares)
        
        # Potential profit if we win both sides equally
        guaranteed_value = min_shares * 1.0  # Each share pays $1
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
        """Get all trades for this market"""
        return self.trades
    
    def cleanup(self):
        """Cleanup and close positions if needed"""
        print("\n💰 Trader cleanup...")
        
        position = self.get_current_position()
        
        print(f"   Final position:")
        print(f"   YES: {position['yes_shares']:.2f} shares (${position['yes_spent']:.2f})")
        print(f"   NO: {position['no_shares']:.2f} shares (${position['no_spent']:.2f})")
        print(f"   Min shares: {position['min_shares']:.2f}")
        print(f"   Potential profit: ${position['potential_profit']:.2f}")
        
        # Optional: Could implement auto-sell logic here
        # For now, just report


# ==========================================
# TESTING
# ==========================================

def test_trader():
    """Test trader logic (without actual orders)"""
    
    print("🧪 Testing Pair Trader...\n")
    
    # Mock config
    class MockConfig:
        TARGET_PAIR_COST = 0.98
        ORDER_SIZE_USD = 0.75
        MAX_PER_SIDE = 10.0
        MAX_IMBALANCE = 0.20
        MAX_PRICE_YES = 60.0
        MAX_PRICE_NO = 60.0
        MAX_DAILY_LOSS = 50.0
    
    # Mock client
    class MockClient:
        def get_mid_price(self, token_id):
            return 0.48  # Mock price
        
        def buy_outcome(self, token_id, usd_amount, max_price):
            print(f"   [MOCK] Would buy {usd_amount} at {max_price}")
            return True
    
    # Mock market
    mock_market = {
        'title': 'Test Market',
        'condition_id': '0x123',
        'yes_token_id': '0xYES',
        'no_token_id': '0xNO',
        'yes_outcome': 'Up',
        'no_outcome': 'Down'
    }
    
    # Create trader
    trader = PairTrader(MockClient(), MockConfig())
    trader.set_market(mock_market)
    
    # Simulate trading cycles
    for i in range(3):
        print(f"\n--- Cycle {i+1} ---")
        trader.execute_trading_cycle()
    
    # Show final position
    print("\n📊 Final Position:")
    pos = trader.get_current_position()
    for key, value in pos.items():
        print(f"   {key}: {value}")


if __name__ == "__main__":
    test_trader()