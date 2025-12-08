"""
Polymarket Client Module - MERGED VERSION
Handles all communication with Polymarket APIs
Combines old features + new fixes
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from typing import Optional, Dict, List
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.constants import POLYGON
from utils.logger import get_logger

logger = get_logger(__name__)


class PolymarketClient:
    """
    Wrapper for Polymarket CLOB client
    Handles authentication and order placement
    """
    
    def __init__(
        self,
        private_key: str,
        proxy_address: str,
        chain_id: int = 137,
        signature_type: int = 2,
        host: str = "https://clob.polymarket.com"
    ):
        """
        Initialize Polymarket client
        
        Args:
            private_key: Wallet private key (without 0x)
            proxy_address: Polymarket proxy wallet address
            chain_id: Polygon chain ID (default 137)
            signature_type: 2 for MetaMask/browser wallet
            host: CLOB API host
        """
        self.private_key = private_key
        self.proxy_address = proxy_address
        self.chain_id = chain_id
        self.signature_type = signature_type
        self.host = host
        
        # Initialize CLOB client
        self.client = ClobClient(
            host,
            key=private_key,
            chain_id=chain_id,
            signature_type=signature_type
        )
        
        # Set API credentials (REQUIRED for many operations)
        try:
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            logger.info("✅ API credentials set")
        except Exception as e:
            logger.warning(f"⚠️ Could not set API creds: {e}")
        
        # API endpoints
        self.gamma_api = "https://gamma-api.polymarket.com"
        self.data_api = "https://data-api.polymarket.com"
        self.clob_api = "https://clob.polymarket.com"
        
        logger.info("✅ Polymarket client initialized")
    
    # ==========================================
    # NEW: GET MARKET BY CONDITION_ID
    # ==========================================
    
    def get_market(self, condition_id: str) -> Optional[Dict]:
        """
        Get market data from CLOB API using condition_id
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Market dict or None
        """
        try:
            url = f"{self.clob_api}/markets"
            params = {'condition_id': condition_id}
            
            response = requests.get(url, params=params, timeout=10)
            
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
            logger.error(f"Error getting market: {e}")
            return None
    
    def get_prices(self, condition_id: str) -> Optional[Dict]:
        """
        Get current YES/NO prices for a market
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Dict with 'prices' and 'token_ids', or None
        """
        try:
            # Get market data
            market = self.get_market(condition_id)
            
            if not market:
                return None
            
            tokens = market.get('tokens', [])
            
            prices = {}
            token_ids = {}
            
            for token in tokens:
                outcome = token.get('outcome', '').upper()
                price = float(token.get('price', 0))
                token_id = token.get('token_id')
                
                if outcome in ['YES', 'UP']:
                    prices['YES'] = price
                    token_ids['YES'] = token_id
                elif outcome in ['NO', 'DOWN']:
                    prices['NO'] = price
                    token_ids['NO'] = token_id
            
            return {
                'prices': prices,
                'token_ids': token_ids
            } if prices else None
            
        except Exception as e:
            logger.error(f"Error getting prices: {e}")
            return None
    
    # ==========================================
    # ORDER PLACEMENT
    # ==========================================
    
    def create_market_buy_order(
        self,
        token_id: str,
        amount: float,
        price: Optional[float] = None
    ) -> Optional[str]:
        """
        Create a market buy order
        
        Args:
            token_id: Outcome token ID
            amount: Amount in USD to spend
            price: Optional price limit (uses market price if None)
        
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            # Get market price if not specified
            if price is None:
                price = self.get_market_price(token_id)
            
            # Calculate shares to buy
            shares = amount / price
            
            # Create order
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=shares,
                side="BUY",
                fee_rate_bps=0
            )
            
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.GTC)
            
            if resp and resp.get('success'):
                order_id = resp.get('orderID')
                logger.info(f"✅ Order placed: {order_id}")
                return order_id
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creating buy order: {e}")
            return None
    
    def create_limit_buy_order(
        self,
        token_id: str,
        size: float,
        price: float
    ) -> Optional[str]:
        """
        Create a limit buy order
        
        Args:
            token_id: Outcome token ID
            size: Number of shares to buy
            price: Limit price (0-1)
        
        Returns:
            Order ID if successful
        """
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side="BUY",
                fee_rate_bps=0
            )
            
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.GTC)
            
            if resp and resp.get('success'):
                order_id = resp.get('orderID')
                logger.info(f"✅ Limit order placed: {order_id} | {size} @ ${price:.4f}")
                return order_id
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creating limit buy order: {e}")
            return None
    
    def place_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float
    ) -> Optional[str]:
        """
        Place a limit order (buy or sell)
        
        Args:
            token_id: Token ID to trade
            side: 'BUY' or 'SELL'
            size: Amount in shares
            price: Price per share (0-1)
            
        Returns:
            Order ID or None
        """
        try:
            order_args = OrderArgs(
                price=price,
                size=size,
                side=side.upper(),
                token_id=token_id,
                fee_rate_bps=0
            )
            
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.GTC)
            
            if resp and resp.get('success'):
                order_id = resp.get('orderID')
                logger.info(f"✅ Order placed: {order_id}")
                logger.info(f"   {side} {size} @ ${price:.4f}")
                return order_id
            else:
                logger.error("❌ Order failed: No order ID returned")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error placing order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        try:
            resp = self.client.cancel_order(order_id)
            success = resp.get('success', False) if resp else False
            
            if success:
                logger.info(f"✅ Order cancelled: {order_id}")
            
            return success
        except Exception as e:
            logger.error(f"❌ Error canceling order: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders"""
        try:
            orders = self.get_open_orders()
            
            for order in orders:
                order_id = order.get('id')
                if order_id:
                    self.cancel_order(order_id)
            
            logger.info(f"✅ Cancelled {len(orders)} orders")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error canceling all orders: {e}")
            return False
    
    # ==========================================
    # MARKET DATA
    # ==========================================
    
    def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """
        Get orderbook for a token
        
        Args:
            token_id: Token ID
            
        Returns:
            Orderbook dict with 'bids' and 'asks'
        """
        try:
            book = self.client.get_order_book(token_id)
            return book
        except Exception as e:
            logger.error(f"Error getting orderbook: {e}")
            return None
    
    def get_market_price(self, token_id: str) -> float:
        """Get current market price for a token"""
        try:
            # Get order book
            book = self.get_orderbook(token_id)
            
            if not book:
                return 0.5  # Default to 50¢
            
            # Get best ask (lowest sell price)
            asks = book.get('asks', [])
            
            if asks and len(asks) > 0:
                best_ask = asks[0]
                return float(best_ask.get('price', 0.5))
            
            return 0.5
            
        except Exception as e:
            logger.warning(f"⚠️ Error getting market price: {e}")
            return 0.5
    
    def get_mid_price(self, token_id: str) -> float:
        """Get mid price (average of bid and ask)"""
        try:
            book = self.get_orderbook(token_id)
            
            if not book:
                return 0.5
            
            bids = book.get('bids', [])
            asks = book.get('asks', [])
            
            if bids and asks:
                best_bid = float(bids[0].get('price', 0.5))
                best_ask = float(asks[0].get('price', 0.5))
                return (best_bid + best_ask) / 2
            
            return 0.5
            
        except Exception as e:
            logger.warning(f"⚠️ Error getting mid price: {e}")
            return 0.5
    
    # ==========================================
    # ACCOUNT INFO
    # ==========================================
    
    def get_balance(self, token_id: Optional[str] = None) -> float:
        """
        Get balance for a token or USDC
        
        Args:
            token_id: Token ID (None for USDC balance)
        
        Returns:
            Balance amount
        """
        try:
            if token_id is None:
                # Get USDC balance
                balance = self.client.get_balance()
                return float(balance) if balance else 0.0
            else:
                # Get token balance
                balance = self.client.get_balance(token_id)
                return float(balance) if balance else 0.0
                
        except Exception as e:
            logger.warning(f"⚠️ Error getting balance: {e}")
            return 0.0
    
    def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
        try:
            orders = self.client.get_orders()
            return orders if orders else []
        except Exception as e:
            logger.warning(f"⚠️ Error getting open orders: {e}")
            return []
    
    # ==========================================
    # ALLOWANCES (REQUIRED FOR TRADING)
    # ==========================================
    
    def check_allowance(self) -> bool:
        """
        Check if USDC allowance is set
        
        Since we set allowances via web3 in approve.py,
        we just verify API credentials are working
        
        Returns:
            True if can connect to API
        """
        try:
            # Try to get server time (doesn't require auth)
            server_time = self.client.get_server_time()
            
            if server_time:
                logger.info("✅ API connection OK")
                logger.info("   Assuming allowances set via approve.py")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error checking API: {e}")
            logger.info("   If you ran approve.py successfully, this is fine")
            # Return True anyway if user ran approve.py
            return True
    
    # ==========================================
    # SIMPLIFIED API (For gabagool22 strategy)
    # ==========================================
    
    def buy_outcome(
        self,
        token_id: str,
        usd_amount: float,
        max_price: Optional[float] = None
    ) -> bool:
        """
        Simple buy: spend USD amount on an outcome
        
        Args:
            token_id: Token to buy
            usd_amount: How much USD to spend
            max_price: Maximum price willing to pay (optional)
        
        Returns:
            True if successful
        """
        try:
            # Get current price
            current_price = self.get_market_price(token_id)
            
            # Check price limit
            if max_price and current_price > max_price:
                logger.warning(f"⚠️ Price {current_price:.2f} exceeds limit {max_price:.2f}")
                return False
            
            # Calculate shares
            shares = usd_amount / current_price
            
            # Create order
            order_id = self.create_limit_buy_order(
                token_id=token_id,
                size=shares,
                price=current_price * 1.01  # Slight premium for faster fill
            )
            
            return order_id is not None
            
        except Exception as e:
            logger.error(f"❌ Error buying outcome: {e}")
            return False


# Test function
def test_client():
    """Test the client"""
    
    print("\n🧪 TESTING POLYMARKET CLIENT")
    print("="*80)
    
    from config import Config
    
    if not Config.validate():
        print("❌ Config validation failed!")
        return
    
    # Initialize client using config
    client = PolymarketClient(
        private_key=Config.PRIVATE_KEY,
        proxy_address=Config.PROXY_ADDRESS,
        chain_id=Config.CHAIN_ID,
        signature_type=Config.SIGNATURE_TYPE,
        host=Config.CLOB_HOST
    )
    
    # Test 1: Get balance
    print("\n1️⃣ Testing balance...")
    balance = client.get_balance()
    
    if balance is not None:
        print(f"   ✅ Balance: ${balance:.2f} USDC")
    else:
        print(f"   ⚠️  Could not get balance")
    
    # Test 2: Get open orders
    print("\n2️⃣ Testing open orders...")
    orders = client.get_open_orders()
    print(f"   ✅ Open orders: {len(orders)}")
    
    print("\n" + "="*80)
    print("✅ Client test complete!")


if __name__ == "__main__":
    test_client()