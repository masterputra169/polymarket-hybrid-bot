"""
COMPLETE POLYMARKET BOT
Based on Official Polymarket Repositories:
- https://github.com/Polymarket/py-clob-client
- https://github.com/Polymarket/agents

This is the DEFINITIVE working version!
"""

import os
import sys
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dotenv import load_dotenv

# Official Polymarket client
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.constants import POLYGON

import requests
from utils.logger import setup_logger

load_dotenv()


class PolymarketBot:
    """
    Complete Polymarket Trading Bot
    Based on official Polymarket repositories
    """
    
    def __init__(self):
        self.logger = setup_logger("PolymarketBot")
        
        # Load config
        self.private_key = os.getenv("PRIVATE_KEY")
        self.proxy_address = os.getenv("PROXY_ADDRESS")
        
        if not self.private_key or not self.proxy_address:
            raise ValueError("PRIVATE_KEY and PROXY_ADDRESS required in .env")
        
        # Trading params
        self.target_pair_cost = float(os.getenv("TARGET_PAIR_COST", "0.98"))
        self.order_size_usd = float(os.getenv("ORDER_SIZE_USD", "0.75"))
        self.max_per_side = float(os.getenv("MAX_PER_SIDE", "5.0"))
        self.dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        
        # Initialize client
        self.client = None
        self.current_market = None
        
        # Trading state
        self.yes_spent = 0.0
        self.no_spent = 0.0
        self.yes_shares = 0.0
        self.no_shares = 0.0
        
        self.logger.info("🤖 Bot initialized")
    
    def connect(self):
        """Initialize Polymarket client"""
        try:
            self.logger.info("📡 Connecting to Polymarket...")
            
            # Initialize client (official method)
            self.client = ClobClient(
                "https://clob.polymarket.com",
                key=self.private_key,
                chain_id=POLYGON,
                signature_type=2  # EOA/MetaMask style
            )
            
            # Set API credentials (REQUIRED)
            creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(creds)
            
            self.logger.info("✅ Connected successfully")
            
            # Test connection
            try:
                server_time = self.client.get_server_time()
                self.logger.info(f"   Server time: {server_time}")
            except:
                pass
            
        except Exception as e:
            self.logger.error(f"❌ Connection failed: {e}")
            raise
    
    def find_market(self) -> Optional[Dict]:
        """
        Find BTC 15-minute market
        Using official Gamma API approach
        """
        try:
            self.logger.info("🔍 Searching for BTC 15-minute market...")
            
            # Query Gamma API (official endpoint)
            params = {
                "limit": 100,
                "closed": False  # Only open markets
            }
            
            response = requests.get(
                "https://gamma-api.polymarket.com/markets",
                params=params,
                timeout=15
            )
            
            if response.status_code != 200:
                self.logger.error(f"Gamma API error: {response.status_code}")
                return None
            
            markets = response.json()
            
            if not isinstance(markets, list):
                self.logger.error("Invalid Gamma response")
                return None
            
            self.logger.info(f"📊 Found {len(markets)} open markets")
            
            # Find BTC 15-minute market
            for market in markets:
                question = market.get('question', '').lower()
                
                # Check for BTC + 15-minute
                has_btc = any(kw in question for kw in ['btc', 'bitcoin'])
                has_15m = any(kw in question for kw in [
                    '15 minute', '15min', '15-minute', '15m'
                ])
                
                if has_btc and has_15m:
                    self.logger.info(f"✅ Found: {market['question']}")
                    
                    # Get live CLOB data
                    condition_id = market['condition_id']
                    
                    clob_market = self.client.get_market(condition_id)
                    
                    if clob_market:
                        # Merge data
                        market['clob_data'] = clob_market
                        return market
            
            self.logger.warning("⚠️  No BTC 15M market found")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Error finding market: {e}")
            return None
    
    def is_market_tradeable(self, market: Dict) -> bool:
        """Check if market is ready for trading"""
        clob_data = market.get('clob_data')
        
        if not clob_data:
            return False
        
        # Check status
        if not clob_data.get('active', False):
            return False
        
        if clob_data.get('closed', False):
            return False
        
        if not clob_data.get('accepting_orders', False):
            return False
        
        tokens = clob_data.get('tokens', [])
        if len(tokens) != 2:
            return False
        
        return True
    
    def get_market_prices(self, market: Dict) -> Optional[Dict]:
        """Get current YES/NO prices"""
        clob_data = market.get('clob_data')
        
        if not clob_data:
            return None
        
        tokens = clob_data.get('tokens', [])
        
        prices = {}
        token_ids = {}
        
        for token in tokens:
            outcome = token.get('outcome', '').upper()
            price = float(token.get('price', 0))
            token_id = token.get('token_id')
            
            if any(kw in outcome for kw in ['YES', 'UP', 'HIGHER']):
                prices['YES'] = price
                token_ids['YES'] = token_id
            elif any(kw in outcome for kw in ['NO', 'DOWN', 'LOWER']):
                prices['NO'] = price
                token_ids['NO'] = token_id
        
        return {
            'prices': prices,
            'token_ids': token_ids
        }
    
    def execute_trade(self, side: str, token_id: str, price: float):
        """
        Execute a trade
        
        Args:
            side: 'YES' or 'NO'
            token_id: Token ID to buy
            price: Current price
        """
        try:
            # Calculate shares
            shares = self.order_size_usd / price
            
            self.logger.info(f"💰 Trading: {side} | {shares:.2f} shares @ ${price:.4f}")
            
            if self.dry_run:
                self.logger.info("   🔔 DRY RUN - No real order placed")
                
                # Track dry run state
                if side == 'YES':
                    self.yes_spent += self.order_size_usd
                    self.yes_shares += shares
                else:
                    self.no_spent += self.order_size_usd
                    self.no_shares += shares
                
                return True
            
            # Create order (official method)
            order_args = OrderArgs(
                price=price,
                size=shares,
                side="BUY",
                token_id=token_id,
                fee_rate_bps=0  # No maker fee
            )
            
            # Sign order
            signed_order = self.client.create_order(order_args)
            
            # Post order
            resp = self.client.post_order(signed_order, OrderType.GTC)
            
            if resp and resp.get('success'):
                order_id = resp.get('orderID')
                self.logger.info(f"   ✅ Order placed: {order_id}")
                
                # Track state
                if side == 'YES':
                    self.yes_spent += self.order_size_usd
                    self.yes_shares += shares
                else:
                    self.no_spent += self.order_size_usd
                    self.no_shares += shares
                
                return True
            else:
                self.logger.error(f"   ❌ Order failed: {resp}")
                return False
            
        except Exception as e:
            self.logger.error(f"❌ Trade error: {e}")
            return False
    
    def run_trading_cycle(self, market: Dict):
        """Execute one trading cycle"""
        
        # Get current prices
        price_data = self.get_market_prices(market)
        
        if not price_data:
            self.logger.warning("⚠️  Could not get prices")
            return
        
        prices = price_data['prices']
        token_ids = price_data['token_ids']
        
        yes_price = prices.get('YES', 0.5)
        no_price = prices.get('NO', 0.5)
        
        pair_cost = yes_price + no_price
        
        self.logger.info(f"\n📊 Market State:")
        self.logger.info(f"   YES: ${yes_price:.4f} | Spent: ${self.yes_spent:.2f}")
        self.logger.info(f"   NO:  ${no_price:.4f} | Spent: ${self.no_spent:.2f}")
        self.logger.info(f"   Pair Cost: ${pair_cost:.4f}")
        
        # Check if pair cost is good
        if pair_cost >= self.target_pair_cost:
            self.logger.info(f"   ⏸️  Pair cost too high (>= ${self.target_pair_cost})")
            return
        
        self.logger.info(f"   ✅ Good pair cost (< ${self.target_pair_cost})")
        
        # Buy YES if budget allows
        if self.yes_spent < self.max_per_side:
            if yes_price < 0.60:  # Safety limit
                self.execute_trade('YES', token_ids['YES'], yes_price)
        
        # Buy NO if budget allows
        if self.no_spent < self.max_per_side:
            if no_price < 0.60:  # Safety limit
                self.execute_trade('NO', token_ids['NO'], no_price)
    
    def print_summary(self):
        """Print trading summary"""
        total_spent = self.yes_spent + self.no_spent
        min_shares = min(self.yes_shares, self.no_shares)
        guaranteed_value = min_shares * 1.0
        profit = guaranteed_value - total_spent
        profit_pct = (profit / total_spent * 100) if total_spent > 0 else 0
        
        print("\n" + "="*70)
        print("📊 TRADING SUMMARY")
        print("="*70)
        print(f"YES Shares: {self.yes_shares:.2f} (${self.yes_spent:.2f})")
        print(f"NO Shares:  {self.no_shares:.2f} (${self.no_spent:.2f})")
        print(f"Total Spent: ${total_spent:.2f}")
        print(f"Min Shares: {min_shares:.2f}")
        print(f"Guaranteed Value: ${guaranteed_value:.2f}")
        print(f"Potential Profit: ${profit:.2f} ({profit_pct:.2f}%)")
        print("="*70)
    
    def run(self):
        """Main bot loop"""
        
        print("\n" + "="*70)
        print("🚀 POLYMARKET BOT - OFFICIAL VERSION")
        print("="*70)
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE TRADING'}")
        print(f"Target Pair Cost: < ${self.target_pair_cost}")
        print(f"Order Size: ${self.order_size_usd}")
        print(f"Max Per Side: ${self.max_per_side}")
        print("="*70)
        
        # Connect
        self.connect()
        
        try:
            while True:
                # Find market
                if not self.current_market:
                    market = self.find_market()
                    
                    if market:
                        self.current_market = market
                        self.logger.info(f"🎯 Trading: {market['question']}")
                    else:
                        self.logger.info("⏳ No market found, waiting 30s...")
                        time.sleep(30)
                        continue
                
                # Check if still tradeable
                if not self.is_market_tradeable(self.current_market):
                    self.logger.info("⏸️  Market not tradeable yet, waiting...")
                    time.sleep(10)
                    
                    # Refresh market data
                    condition_id = self.current_market['condition_id']
                    clob_data = self.client.get_market(condition_id)
                    
                    if clob_data:
                        self.current_market['clob_data'] = clob_data
                    
                    continue
                
                # Execute trading
                self.run_trading_cycle(self.current_market)
                
                # Check if done
                if self.yes_spent >= self.max_per_side and self.no_spent >= self.max_per_side:
                    self.logger.info("✅ Max budget reached!")
                    self.print_summary()
                    break
                
                # Wait before next cycle
                time.sleep(5)
        
        except KeyboardInterrupt:
            self.logger.info("\n⚠️  Stopped by user")
            self.print_summary()
        except Exception as e:
            self.logger.error(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            self.print_summary()


def main():
    """Entry point"""
    bot = PolymarketBot()
    bot.run()


if __name__ == "__main__":
    main()