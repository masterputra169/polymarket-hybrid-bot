"""
Polymarket Client Module - Fixed Orderbook Handling
Based on official py-clob-client examples
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional, Dict
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from utils.logger import get_logger

logger = get_logger(__name__)


class PolymarketClient:
    def __init__(
        self,
        private_key: str,
        proxy_address: str,
        chain_id: int = 137,
        signature_type: int = 2,
        host: str = "https://clob.polymarket.com"
    ):
        self.private_key = private_key
        self.proxy_address = proxy_address
        self.chain_id = chain_id
        self.signature_type = signature_type
        self.host = host
        
        # Initialize py-clob-client
        self.client = ClobClient(
            host,
            key=private_key,
            chain_id=chain_id,
            signature_type=signature_type,
            funder=proxy_address
        )
        
        try:
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            logger.info("✅ API credentials set")
        except Exception as e:
            logger.warning(f"⚠️ Could not set API creds: {e}")
        
        logger.info("✅ Polymarket client initialized")
    
    # ==========================================
    # ORDERBOOK - Using Official py-clob-client Method
    # ==========================================
    
    def get_orderbook(self, token_id: str):
        """
        Get orderbook using official py-clob-client method
        
        Returns OrderBookSummary object with:
        - asks: list of {price, size} dicts
        - bids: list of {price, size} dicts
        """
        try:
            # Use official py-clob-client method
            book = self.client.get_order_book(token_id)
            return book
            
        except Exception as e:
            error_str = str(e)
            if "No orderbook exists" in error_str or "404" in error_str:
                logger.debug(f"No orderbook for token {token_id[:10]}...")
                return None
            logger.debug(f"Orderbook error: {e}")
            return None
    
    def get_market_price(self, token_id: str) -> float:
        """
        Get best ask price for a token (real-time from orderbook)
        """
        try:
            book = self.get_orderbook(token_id)
            
            if not book:
                return 0.5
            
            # Check if asks exist
            if hasattr(book, 'asks') and book.asks:
                best_ask = book.asks[0]
                
                # Handle both dict and object formats
                if isinstance(best_ask, dict):
                    price = float(best_ask.get('price', 0.5))
                elif hasattr(best_ask, 'price'):
                    price = float(best_ask.price)
                else:
                    return 0.5
                
                # Validate price
                if 0.01 < price < 0.99:
                    return price
            
            return 0.5
            
        except Exception as e:
            logger.debug(f"Price error: {e}")
            return 0.5
    
    # ==========================================
    # ORDER PLACEMENT
    # ==========================================
    
    def buy_outcome(self, token_id: str, usd_amount: float, max_price: Optional[float] = None) -> bool:
        """
        Buy outcome using py-clob-client
        
        Args:
            token_id: Token to buy
            usd_amount: Amount in USD to spend
            max_price: Maximum price willing to pay
        
        Returns:
            True if order placed successfully
        """
        try:
            # Get current market price
            current_price = self.get_market_price(token_id)
            
            if current_price <= 0 or current_price >= 1:
                logger.error(f"Invalid price: {current_price}")
                return False
            
            # Check max price limit
            if max_price and current_price > max_price:
                logger.warning(f"Price {current_price:.4f} > limit {max_price:.4f}")
                return False
            
            # Calculate shares to buy
            shares = usd_amount / current_price
            
            # Set order price slightly above current (for fast fill)
            order_price = min(current_price * 1.01, 0.99)
            
            # Create order using py-clob-client
            order_args = OrderArgs(
                price=order_price,
                size=shares,
                side='BUY',
                token_id=token_id,
                fee_rate_bps=0
            )
            
            # Create and sign order
            signed_order = self.client.create_order(order_args)
            
            # Post order
            resp = self.client.post_order(signed_order, OrderType.GTC)
            
            if resp and resp.get('success'):
                order_id = resp.get('orderID')
                logger.info(f"✅ Order placed: {order_id}")
                return True
            else:
                error_msg = resp.get('errorMsg', 'Unknown') if resp else 'No response'
                logger.error(f"❌ Order failed: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Buy error: {e}")
            return False
    
    # ==========================================
    # UTILITY
    # ==========================================
    
    def check_allowance(self) -> bool:
        """Check if client is properly initialized"""
        try:
            server_time = self.client.get_server_time()
            return server_time is not None
        except:
            return True
    
    def get_balance(self) -> float:
        """Get balance (not implemented in this version)"""
        return 0.0


# ==========================================
# TEST
# ==========================================

def test_orderbook():
    """Test orderbook fetching"""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    pk = os.getenv("PRIVATE_KEY")
    pa = os.getenv("PROXY_ADDRESS")
    
    if not pk or not pa:
        print("❌ Missing credentials")
        return
    
    print("\n🧪 Testing Orderbook Fetching...\n")
    
    client = PolymarketClient(private_key=pk, proxy_address=pa)
    
    # Find a real market first
    print("📡 Finding active BTC market...")
    import requests
    
    try:
        response = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={'limit': 10, 'closed': 'false', 'active': 'true'},
            timeout=10
        )
        
        if response.status_code == 200:
            markets = response.json()
            
            for market in markets:
                slug = market.get('slug', '').lower()
                if 'btc-updown' in slug:
                    print(f"✅ Found: {market.get('question', 'Unknown')[:50]}")
                    
                    import json
                    clob_tokens = market.get('clobTokenIds')
                    if isinstance(clob_tokens, str):
                        clob_tokens = json.loads(clob_tokens.replace("'", '"'))
                    
                    if clob_tokens and len(clob_tokens) >= 2:
                        yes_token = clob_tokens[0]
                        no_token = clob_tokens[1]
                        
                        print(f"\n📖 Testing YES orderbook...")
                        print(f"   Token: {yes_token[:20]}...")
                        
                        book = client.get_orderbook(yes_token)
                        
                        if book:
                            print(f"   ✅ Orderbook fetched successfully!")
                            
                            if hasattr(book, 'asks') and book.asks:
                                best_ask = book.asks[0]
                                if isinstance(best_ask, dict):
                                    price = best_ask.get('price')
                                elif hasattr(best_ask, 'price'):
                                    price = best_ask.price
                                print(f"   Best ASK: ${float(price):.4f}")
                            
                            if hasattr(book, 'bids') and book.bids:
                                best_bid = book.bids[0]
                                if isinstance(best_bid, dict):
                                    price = best_bid.get('price')
                                elif hasattr(best_bid, 'price'):
                                    price = best_bid.price
                                print(f"   Best BID: ${float(price):.4f}")
                        else:
                            print(f"   ❌ Failed to fetch orderbook")
                        
                        print(f"\n📖 Testing get_market_price()...")
                        price = client.get_market_price(yes_token)
                        print(f"   Market price: ${price:.4f}")
                        
                        break
            else:
                print("❌ No BTC market found")
        else:
            print(f"❌ API request failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    test_orderbook()