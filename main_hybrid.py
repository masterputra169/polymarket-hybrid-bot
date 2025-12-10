"""
Polymarket Hybrid Trading Bot V2 - Fixed time remaining calculation
"""

import os
import sys
import asyncio
import signal
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from core.client import PolymarketClient
from core.market_scanner import MarketScanner
from core.pair_trader import PairTrader
from core.last_second_sniper import LastSecondSniper
from core.monitor import TradeMonitor
from utils.logger import setup_logger
from config import Config

load_dotenv()


class HybridTradingBot:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger("HybridBot")
        self.running = False
        
        self.client = None
        self.scanner = None
        self.pair_trader = None
        self.sniper = None
        self.monitor = None
        
        self.current_market = None
        self.trading_mode = None
        self.markets_traded = 0
        
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)
    
    def initialize(self):
        self.logger.info("🚀 Initializing Hybrid Trading Bot...")
        
        try:
            self.logger.info("📡 Connecting to Polymarket...")
            self.client = PolymarketClient(
                private_key=self.config.PRIVATE_KEY,
                proxy_address=self.config.PROXY_ADDRESS,
                chain_id=self.config.CHAIN_ID
            )
            self.logger.info("✅ Connected to Polymarket")
            
            skip_allowance = os.getenv("SKIP_ALLOWANCE_CHECK", "false").lower() == "true"
            if not skip_allowance:
                self.logger.info("🔐 Checking USDC allowance...")
                if not self.client.check_allowance():
                    self.logger.warning("⚠️ Could not verify allowance")
                else:
                    self.logger.info("✅ Allowance OK")
            else:
                self.logger.info("⏭️ Skipping allowance check")
            
            self.logger.info(f"🔍 Initializing market scanner...")
            self.logger.info(f"   Asset: {self.config.ASSET}")
            self.logger.info(f"   Duration: {self.config.MARKET_DURATION} minutes")
            
            self.scanner = MarketScanner(
                asset=self.config.ASSET,
                duration=self.config.MARKET_DURATION
            )
            self.logger.info("✅ Scanner ready")
            
            self.logger.info("💰 Initializing pair trader...")
            self.pair_trader = PairTrader(
                client=self.client,
                config=self.config
            )
            self.logger.info("✅ Pair trader ready")
            
            self.logger.info("🎯 Initializing sniper...")
            self.sniper = LastSecondSniper(
                client=self.client,
                config=self.config
            )
            self.logger.info("✅ Sniper ready")
            
            self.logger.info("📊 Initializing monitor...")
            self.monitor = TradeMonitor(
                config=self.config,
                pair_trader=self.pair_trader,
                sniper=self.sniper
            )
            self.logger.info("✅ Monitor ready")
            
            self.logger.info("✨ All systems initialized!\n")
            
        except Exception as e:
            self.logger.error(f"❌ Initialization failed: {e}")
            raise
    
    def print_banner(self):
        banner = f"""
╔═══════════════════════════════════════════════════════════════╗
║           POLYMARKET HYBRID TRADING BOT V2                    ║
║                                                               ║
║  Strategy 1: Pair Trading (gabagool22)                       ║
║  Strategy 2: Last-Second Sniping                             ║
╚═══════════════════════════════════════════════════════════════╝

📊 Configuration:
   Asset:              {self.config.ASSET}
   Duration:           {self.config.MARKET_DURATION} minutes

💰 Pair Trading Mode (0-14 min):
   Target Pair Cost:   < ${self.config.TARGET_PAIR_COST}
   Order Size:         ${self.config.ORDER_SIZE_USD}
   Max Per Side:       ${self.config.MAX_PER_SIDE}

🎯 Sniping Mode (Last {self.config.SNIPE_TRIGGER_SECONDS}s):
   Min Price:          ${self.config.SNIPE_MIN_PRICE}
   Max Price:          ${self.config.SNIPE_MAX_PRICE}
   Snipe Size:         ${self.config.SNIPE_SIZE_USD}

⚙️  Settings:
   Dry Run:            {self.config.DRY_RUN}
   Polling:            {self.config.POLLING_INTERVAL}s

🔐 Wallet:
   Address:            {self.config.PROXY_ADDRESS[:10]}...{self.config.PROXY_ADDRESS[-8:]}

{'='*67}
"""
        print(banner)
    
    async def run(self):
        self.running = True
        self.print_banner()
        
        self.logger.info("🏁 Bot started - scanning for markets...")
        
        check_count = 0
        
        try:
            while self.running:
                check_count += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                # Find market
                if not self.current_market:
                    self.logger.info(f"[{now}] Check #{check_count}: Scanning...")
                    
                    try:
                        market = await self.scanner.find_active_market_async()
                    except Exception as e:
                        self.logger.error(f"Scanner error: {e}")
                        await asyncio.sleep(30)
                        continue
                    
                    if market:
                        self.current_market = market
                        self.markets_traded += 1
                        
                        self.logger.info(f"🎯 MARKET #{self.markets_traded} FOUND!")
                        self.logger.info(f"   {market['question'][:60]}")
                        self.logger.info(f"   Slug: {market.get('slug', 'N/A')}")
                        self.logger.info(f"   Time Remaining: {market.get('time_remaining', 'N/A')}s")
                        self.logger.info(f"   YES: ${market['yes_price']:.4f}")
                        self.logger.info(f"   NO: ${market['no_price']:.4f}")
                        
                        pair_cost = market['yes_price'] + market['no_price']
                        self.logger.info(f"   Pair Cost: ${pair_cost:.4f}")
                        
                        self.pair_trader.set_market(market)
                        await self.sniper.set_market(market)
                        self.monitor.start_monitoring(market)
                    else:
                        self.logger.info(f"   ⏳ No active market, retry in 30s...")
                        await asyncio.sleep(30)
                        continue
                
                # Get time remaining from market data
                time_remaining = self.current_market.get('time_remaining', 0)
                
                # Recalculate based on elapsed time since market was found
                # This is a simple approach - could be improved
                if time_remaining <= 0:
                    self.logger.info("📊 Market ended - generating report...")
                    self.monitor.generate_final_report()
                    self.current_market = None
                    self.trading_mode = None
                    await asyncio.sleep(10)
                    continue
                
                # Determine mode
                if time_remaining <= self.config.SNIPE_TRIGGER_SECONDS:
                    if self.trading_mode != 'SNIPING':
                        self.logger.info(f"\n🎯 SNIPING MODE ({time_remaining}s remaining)")
                        self.trading_mode = 'SNIPING'
                        self.pair_trader.cleanup()
                    
                    await self.sniper.execute_snipe()
                else:
                    if self.trading_mode != 'PAIR_TRADING':
                        self.logger.info(f"\n💰 PAIR TRADING MODE ({time_remaining}s remaining)")
                        self.trading_mode = 'PAIR_TRADING'
                    
                    self.pair_trader.execute_trading_cycle()
                
                # Decrement time remaining
                self.current_market['time_remaining'] = time_remaining - self.config.POLLING_INTERVAL
                
                self.monitor.update()
                await asyncio.sleep(self.config.POLLING_INTERVAL)
                
        except KeyboardInterrupt:
            self.logger.info("\n⚠️ Stopped by user")
        except Exception as e:
            self.logger.error(f"❌ Error: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    def shutdown_handler(self, signum, frame):
        self.logger.info("\n🛑 Shutdown signal received")
        self.running = False
    
    async def shutdown(self):
        self.logger.info("\n📊 Shutting down...")
        
        if self.monitor and self.current_market:
            self.logger.info("📈 Generating final report...")
            self.monitor.generate_final_report()
        
        if self.pair_trader:
            self.logger.info("💰 Closing positions...")
            self.pair_trader.cleanup()
        
        if self.sniper:
            self.logger.info("🎯 Closing sniper...")
            await self.sniper.cleanup()
        
        self.logger.info(f"\n📊 Session Summary:")
        self.logger.info(f"   Markets Traded: {self.markets_traded}")
        self.logger.info("✅ Shutdown complete. Goodbye! 👋\n")


def main():
    print("\n" + "="*60)
    print("🚀 POLYMARKET HYBRID BOT V2")
    print("="*60 + "\n")
    
    required = ['PRIVATE_KEY', 'PROXY_ADDRESS']
    missing = [v for v in required if not os.getenv(v)]
    
    if missing:
        print(f"❌ Missing: {', '.join(missing)}")
        sys.exit(1)
    
    bot = HybridTradingBot()
    
    try:
        bot.initialize()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n⚠️ Stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()