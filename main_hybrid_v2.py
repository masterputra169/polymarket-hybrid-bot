"""
Polymarket Hybrid Trading Bot V2 - Asymmetric Strategy - FIXED VERSION

FIXES:
- Added market warmup period (15s wait after finding new market)
- Better time remaining calculation
- Improved error handling
- More conservative trading approach
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
from core.asymmetric_trader import AsymmetricTrader
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
        self.trader = None  # Can be PairTrader or AsymmetricTrader
        self.sniper = None
        self.monitor = None
        
        self.current_market = None
        self.market_start_time = None  # Track when we found the market
        self.trading_mode = None
        self.markets_traded = 0
        
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)
    
    def initialize(self):
        self.logger.info("🚀 Initializing Hybrid Trading Bot V2...")
        
        try:
            # Connect to Polymarket
            self.logger.info("📡 Connecting to Polymarket...")
            self.client = PolymarketClient(
                private_key=self.config.PRIVATE_KEY,
                proxy_address=self.config.PROXY_ADDRESS,
                chain_id=self.config.CHAIN_ID
            )
            self.logger.info("✅ Connected to Polymarket")
            
            # Check allowance
            skip_allowance = os.getenv("SKIP_ALLOWANCE_CHECK", "false").lower() == "true"
            if not skip_allowance:
                self.logger.info("🔐 Checking USDC allowance...")
                if not self.client.check_allowance():
                    self.logger.warning("⚠️ Could not verify allowance")
                else:
                    self.logger.info("✅ Allowance OK")
            else:
                self.logger.info("⏭️ Skipping allowance check")
            
            # Initialize market scanner
            self.logger.info(f"🔍 Initializing market scanner...")
            self.logger.info(f"   Asset: {self.config.ASSET}")
            self.logger.info(f"   Duration: {self.config.MARKET_DURATION} minutes")
            
            self.scanner = MarketScanner(
                asset=self.config.ASSET,
                duration=self.config.MARKET_DURATION
            )
            self.logger.info("✅ Scanner ready")
            
            # Initialize trader based on strategy type
            if self.config.STRATEGY_TYPE == "ASYMMETRIC":
                self.logger.info("💰 Initializing ASYMMETRIC trader (Gabagool's real strategy)...")
                self.logger.info(f"   Buy when price < avg × {1 - self.config.CHEAP_THRESHOLD}")
                self.trader = AsymmetricTrader(
                    client=self.client,
                    config=self.config
                )
                self.logger.info("✅ Asymmetric trader ready")
            else:
                self.logger.info("💰 Initializing PAIR trader (old symmetric strategy)...")
                self.logger.info(f"   Buy both when pair cost < ${self.config.TARGET_PAIR_COST}")
                self.trader = PairTrader(
                    client=self.client,
                    config=self.config
                )
                self.logger.info("✅ Pair trader ready")
            
            # Initialize sniper
            self.logger.info("🎯 Initializing sniper...")
            self.sniper = LastSecondSniper(
                client=self.client,
                config=self.config
            )
            self.logger.info("✅ Sniper ready")
            
            # Initialize monitor
            self.logger.info("📊 Initializing monitor...")
            self.monitor = TradeMonitor(
                config=self.config,
                pair_trader=self.trader if isinstance(self.trader, PairTrader) else None,
                sniper=self.sniper
            )
            # Hack: If using asymmetric, we still need to pass it as pair_trader for monitor
            if isinstance(self.trader, AsymmetricTrader):
                self.monitor.pair_trader = self.trader
            
            self.logger.info("✅ Monitor ready")
            
            self.logger.info("✨ All systems initialized!\n")
            
        except Exception as e:
            self.logger.error(f"❌ Initialization failed: {e}")
            raise
    
    def print_banner(self):
        strategy_name = "ASYMMETRIC (Gabagool's Real Strategy)" if self.config.STRATEGY_TYPE == "ASYMMETRIC" else "PAIR TRADING (Old Symmetric)"
        
        banner = f"""
╔═══════════════════════════════════════════════════════════════╗
║           POLYMARKET HYBRID TRADING BOT V2                    ║
║                                                               ║
║  Primary: {strategy_name:44s} ║
║  Secondary: Last-Second Sniping                              ║
╚═══════════════════════════════════════════════════════════════╝

📊 Configuration:
   Asset:              {self.config.ASSET}
   Duration:           {self.config.MARKET_DURATION} minutes
   Strategy:           {self.config.STRATEGY_TYPE}
"""

        if self.config.STRATEGY_TYPE == "ASYMMETRIC":
            banner += f"""
💰 Asymmetric Trading Mode (Gabagool's Way):
   Cheap Threshold:    {self.config.CHEAP_THRESHOLD * 100}% below average
   Buy Logic:          Buy YES when YES is cheap (independently)
                      Buy NO when NO is cheap (independently)
   Max Imbalance:      {self.config.MAX_IMBALANCE * 100}% (flexible)
   Order Size:         ${self.config.ORDER_SIZE_USD}
   Max Per Side:       ${self.config.MAX_PER_SIDE}
"""
        else:
            banner += f"""
💰 Pair Trading Mode (Old Symmetric):
   Target Pair Cost:   < ${self.config.TARGET_PAIR_COST}
   Buy Logic:          Buy YES + NO together when cheap
   Max Imbalance:      {self.config.MAX_IMBALANCE * 100}%
   Order Size:         ${self.config.ORDER_SIZE_USD}
   Max Per Side:       ${self.config.MAX_PER_SIDE}
"""

        banner += f"""
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
                        self.market_start_time = datetime.now()
                        self.markets_traded += 1
                        
                        self.logger.info(f"🎯 MARKET #{self.markets_traded} FOUND!")
                        self.logger.info(f"   {market['question'][:60]}")
                        self.logger.info(f"   Slug: {market.get('slug', 'N/A')}")
                        self.logger.info(f"   Time Remaining: {market.get('time_remaining', 'N/A')}s")
                        self.logger.info(f"   YES: ${market['yes_price']:.4f}")
                        self.logger.info(f"   NO: ${market['no_price']:.4f}")
                        
                        pair_cost = market['yes_price'] + market['no_price']
                        self.logger.info(f"   Pair Cost: ${pair_cost:.4f}")
                        
                        # WAIT for market to stabilize (15 seconds)
                        remaining = market.get('time_remaining', 0)
                        if remaining > 800:  # More than 13 min remaining (market just started)
                            self.logger.info(f"\n⏳ WARMUP: Waiting 15s for orderbook to stabilize...")
                            self.logger.info(f"   This prevents failed orders due to stale prices")
                            await asyncio.sleep(15)
                            self.logger.info(f"   ✅ Warmup complete, starting trading...\n")
                        
                        # Initialize trader and sniper
                        self.trader.set_market(market)
                        await self.sniper.set_market(market)
                        self.monitor.start_monitoring(market)
                    else:
                        self.logger.info(f"   ⏳ No active market, retry in 30s...")
                        await asyncio.sleep(30)
                        continue
                
                # Calculate actual time remaining
                if self.market_start_time:
                    elapsed = (datetime.now() - self.market_start_time).total_seconds()
                    time_remaining = max(0, self.current_market.get('time_remaining', 0) - elapsed)
                else:
                    time_remaining = self.current_market.get('time_remaining', 0)
                
                # Check if market ended
                if time_remaining <= 0:
                    self.logger.info("\n📊 Market ended - generating report...")
                    self.monitor.generate_final_report()
                    self.current_market = None
                    self.market_start_time = None
                    self.trading_mode = None
                    await asyncio.sleep(10)
                    continue
                
                # Determine mode
                if time_remaining <= self.config.SNIPE_TRIGGER_SECONDS:
                    if self.trading_mode != 'SNIPING':
                        self.logger.info(f"\n🎯 SNIPING MODE ({int(time_remaining)}s remaining)")
                        self.trading_mode = 'SNIPING'
                        self.trader.cleanup()
                    
                    await self.sniper.execute_snipe()
                else:
                    if self.trading_mode != 'TRADING':
                        strategy_desc = "ASYMMETRIC ARBITRAGE" if self.config.STRATEGY_TYPE == "ASYMMETRIC" else "PAIR TRADING"
                        self.logger.info(f"\n💰 {strategy_desc} MODE ({int(time_remaining)}s remaining)")
                        self.trading_mode = 'TRADING'
                    
                    # Execute trading cycle
                    try:
                        self.trader.execute_trading_cycle()
                    except Exception as e:
                        self.logger.error(f"Trading cycle error: {e}")
                
                # Update monitor
                try:
                    self.monitor.update()
                except Exception as e:
                    self.logger.error(f"Monitor error: {e}")
                
                # Wait before next cycle
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
            try:
                self.monitor.generate_final_report()
            except Exception as e:
                self.logger.error(f"Report generation error: {e}")
        
        if self.trader:
            self.logger.info("💰 Closing positions...")
            try:
                self.trader.cleanup()
            except Exception as e:
                self.logger.error(f"Trader cleanup error: {e}")
        
        if self.sniper:
            self.logger.info("🎯 Closing sniper...")
            try:
                await self.sniper.cleanup()
            except Exception as e:
                self.logger.error(f"Sniper cleanup error: {e}")
        
        self.logger.info(f"\n📊 Session Summary:")
        self.logger.info(f"   Strategy Used: {self.config.STRATEGY_TYPE}")
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
        print(f"\n💡 Please create .env file with required variables")
        sys.exit(1)
    
    bot = HybridTradingBot()
    
    try:
        bot.initialize()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n⚠️ Stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()