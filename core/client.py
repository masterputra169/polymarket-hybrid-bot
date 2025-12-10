"""
Polymarket Client Module V3 - Fixed OrderBookSummary handling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from typing import Optional, Dict, List
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
        
        self.clob_api = "https://clob.polymarket.com"
        self.gamma_api = "https://gamma-api.polymarket.com"
        
        logger.info("✅ Polymarket client initialized")
    
    # ==========================================
    # ORDERBOOK - Fixed for OrderBookSummary object
    # ==========================================
    
    def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """
        Get orderbook - handles both dict and OrderBookSummary object
        """
        try:
            book = self.client.get_order_book(token_id)
            
            if book is None:
                return None
            
            # If it's already a dict, return it
            if isinstance(book, dict):
                return book
            
            # If it's an OrderBookSummary object, convert to dict
            # The object has attributes: bids, asks, hash, market, asset_id, timestamp
            result = {
                'bids': [],
                'asks': []
            }
            
            # Try to access as object attributes
            if hasattr(book, 'bids'):
                bids = book.bids
                if bids:
                    for bid in bids:
                        if hasattr(bid, 'price') and hasattr(bid, 'size'):
                            result['bids'].append({
                                'price': str(bid.price),
                                'size': str(bid.size)
                            })
                        elif isinstance(bid, dict):
                            result['bids'].append(bid)
            
            if hasattr(book, 'asks'):
                asks = book.asks
                if asks:
                    for ask in asks:
                        if hasattr(ask, 'price') and hasattr(ask, 'size'):
                            result['asks'].append({
                                'price': str(ask.price),
                                'size': str(ask.size)
                            })
                        elif isinstance(ask, dict):
                            result['asks'].append(ask)
            
            return result
            
        except Exception as e:
            error_str = str(e)
            if "No orderbook exists" in error_str or "404" in error_str:
                return None
            logger.debug(f"Orderbook error: {e}")
            return None
    
    def get_orderbook_via_rest(self, token_id: str) -> Optional[Dict]:
        """Get orderbook via direct REST API"""
        try:
            url = f"{self.clob_api}/book"
            params = {'token_id': token_id}
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code != 200:
                return None
            
            return response.json()
        except:
            return None
    
    def get_market_price(self, token_id: str) -> float:
        """Get best ask price for a token"""
        try:
            # Method 1: py-clob-client
            book = self.get_orderbook(token_id)
            
            if book and book.get('asks'):
                asks = book['asks']
                if asks:
                    first_ask = asks[0]
                    if isinstance(first_ask, dict):
                        return float(first_ask.get('price', 0.5))
                    elif hasattr(first_ask, 'price'):
                        return float(first_ask.price)
            
            # Method 2: REST API
            book = self.get_orderbook_via_rest(token_id)
            
            if book and book.get('asks'):
                asks = book['asks']
                if asks:
                    return float(asks[0].get('price', 0.5))
            
            # Method 3: Get from market data
            return self._get_price_from_market(token_id)
            
        except Exception as e:
            logger.debug(f"Price error: {e}")
            return 0.5
    
    def get_mid_price(self, token_id: str) -> float:
        """Get mid price (average of bid and ask)"""
        try:
            book = self.get_orderbook(token_id)
            
            if not book:
                book = self.get_orderbook_via_rest(token_id)
            
            if not book:
                return self._get_price_from_market(token_id)
            
            bids = book.get('bids', [])
            asks = book.get('asks', [])
            
            best_bid = 0.0
            best_ask = 1.0
            
            if bids:
                first_bid = bids[0]
                if isinstance(first_bid, dict):
                    best_bid = float(first_bid.get('price', 0))
                elif hasattr(first_bid, 'price'):
                    best_bid = float(first_bid.price)
            
            if asks:
                first_ask = asks[0]
                if isinstance(first_ask, dict):
                    best_ask = float(first_ask.get('price', 1))
                elif hasattr(first_ask, 'price'):
                    best_ask = float(first_ask.price)
            
            if best_bid > 0 and best_ask < 1:
                return (best_bid + best_ask) / 2
            elif best_ask < 1:
                return best_ask
            elif best_bid > 0:
                return best_bid
            
            return self._get_price_from_market(token_id)
            
        except Exception as e:
            logger.debug(f"Mid price calc error: {e}")
            return 0.5
    
    def _get_price_from_market(self, token_id: str) -> float:
        """Fallback: get price from market data"""
        try:
            # Search for market containing this token
            url = f"{self.clob_api}/markets"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                return 0.5
            
            data = response.json()
            
            if isinstance(data, dict) and 'data' in data:
                markets = data['data']
            elif isinstance(data, list):
                markets = data
            else:
                return 0.5
            
            for market in markets:
                tokens = market.get('tokens', [])
                for token in tokens:
                    if token.get('token_id') == token_id:
                        return float(token.get('price', 0.5))
            
            return 0.5
        except:
            return 0.5
    
    # ==========================================
    # MARKET DATA
    # ==========================================
    
    def get_market(self, condition_id: str) -> Optional[Dict]:
        try:
            url = f"{self.clob_api}/markets"
            params = {'condition_id': condition_id}
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if isinstance(data, dict) and 'data' in data:
                markets = data['data']
            elif isinstance(data, list):
                markets = data
            else:
                return None
            
            return markets[0] if markets else None
        except:
            return None
    
    def get_prices(self, condition_id: str) -> Optional[Dict]:
        try:
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
                
                if any(kw in outcome for kw in ['YES', 'UP']):
                    prices['YES'] = price
                    token_ids['YES'] = token_id
                elif any(kw in outcome for kw in ['NO', 'DOWN']):
                    prices['NO'] = price
                    token_ids['NO'] = token_id
            
            return {'prices': prices, 'token_ids': token_ids} if prices else None
        except:
            return None
    
    # ==========================================
    # ORDER PLACEMENT
    # ==========================================
    
    def place_order(self, token_id: str, side: str, size: float, price: float) -> Optional[str]:
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
                return order_id
            else:
                error_msg = resp.get('errorMsg', 'Unknown') if resp else 'No response'
                logger.error(f"❌ Order failed: {error_msg}")
                return None
        except Exception as e:
            logger.error(f"❌ Order error: {e}")
            return None
    
    def create_limit_buy_order(self, token_id: str, size: float, price: float) -> Optional[str]:
        return self.place_order(token_id, "BUY", size, price)
    
    def cancel_order(self, order_id: str) -> bool:
        try:
            resp = self.client.cancel(order_id)
            return resp.get('canceled', False) if resp else False
        except:
            return False
    
    def cancel_all_orders(self) -> bool:
        try:
            self.client.cancel_all()
            return True
        except:
            return False
    
    # ==========================================
    # ACCOUNT
    # ==========================================
    
    def get_balance(self) -> float:
        return 0.0
    
    def get_open_orders(self) -> List[Dict]:
        try:
            orders = self.client.get_orders()
            return orders if orders else []
        except:
            return []
    
    def check_allowance(self) -> bool:
        try:
            server_time = self.client.get_server_time()
            return server_time is not None
        except:
            return True
    
    # ==========================================
    # SIMPLIFIED API
    # ==========================================
    
    def buy_outcome(self, token_id: str, usd_amount: float, max_price: Optional[float] = None) -> bool:
        try:
            current_price = self.get_market_price(token_id)
            
            if current_price <= 0 or current_price >= 1:
                logger.error(f"Invalid price: {current_price}")
                return False
            
            if max_price and current_price > max_price:
                logger.warning(f"Price {current_price:.4f} > limit {max_price:.4f}")
                return False
            
            shares = usd_amount / current_price
            order_price = min(current_price * 1.01, 0.99)
            
            order_id = self.create_limit_buy_order(token_id, shares, order_price)
            return order_id is not None
        except Exception as e:
            logger.error(f"Buy error: {e}")
            return False


def test_client():
    print("\n🧪 TESTING CLIENT V3")
    print("="*60)
    
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    pk = os.getenv("PRIVATE_KEY")
    pa = os.getenv("PROXY_ADDRESS")
    
    if not pk or not pa:
        print("❌ Missing credentials")
        return
    
    client = PolymarketClient(private_key=pk, proxy_address=pa)
    print("✅ Client OK")


if __name__ == "__main__":
    test_client()