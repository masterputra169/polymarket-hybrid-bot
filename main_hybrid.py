"""
Polymarket Hybrid Trading Bot
Combines two proven strategies:
1. Pair Trading (gabagool22) - During market
2. Last-Second Sniping - Final seconds before settlement
"""

import os
import sys
import asyncio
import signal
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Local imports
from core.client import PolymarketClient
from core.market_scanner import MarketScanner
from core.pair_trader import PairTrader
from core.last_second_sniper import LastSecondSniper
from core.monitor import TradeMonitor
from utils.logger import setup_logger
from config import Config

# Load environment
load_dotenv()


class HybridTradingBot:
    """
    Hybrid bot with two modes:
    - PAIR_TRADING: Active during market (0-14 minutes remaining)
    - SNIPING: Last 60 seconds before settlement
    """
    
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger("HybridBot")
        self.running = False
        
        # Components
        self.client = None
        self.scanner = None
        self.pair_trader = None
        self.sniper = None
        self.monitor = None
        
        # State
        self.current_market = None
        self.trading_mode = None  # 'PAIR_TRADING' or 'SNIPING'
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)
    
    def initialize(self):
        """Initialize all components"""
        self.logger.info("🚀 Initializing Hybrid Trading Bot...")
        
        try:
            # 1. Initialize client
            self.logger.info("📡 Connecting to Polymarket...")
            self.client = PolymarketClient(
                private_key=self.config.PRIVATE_KEY,
                proxy_address=self.config.PROXY_ADDRESS,
                chain_id=self.config.CHAIN_ID
            )
            self.logger.info("✅ Connected to Polymarket")
            
            # 2. Check allowances (optional - if user ran approve.py, skip this)
            skip_allowance_check = os.getenv("SKIP_ALLOWANCE_CHECK", "false").lower() == "true"
            
            if not skip_allowance_check:
                self.logger.info("🔐 Checking USDC allowance...")
                if not self.client.check_allowance():
                    self.logger.warning("⚠️ Could not verify allowance via API")
                    self.logger.info("💡 If you ran 'python scripts/approve.py' successfully:")
                    self.logger.info("   Add to .env: SKIP_ALLOWANCE_CHECK=true")
                    self.logger.info("   Or just continue - bot will try to trade anyway")
                    
                    response = input("\nContinue anyway? (y/n): ").strip().lower()
                    if response != 'y':
                        raise Exception("Please run: python scripts/approve.py")
                else:
                    self.logger.info("✅ Allowance check passed")
            else:
                self.logger.info("⏭️ Skipping allowance check (SKIP_ALLOWANCE_CHECK=true)")
            
            # 3. Initialize scanner
            self.logger.info("🔍 Initializing market scanner...")
            self.scanner = MarketScanner(
                asset=self.config.ASSET,
                duration=self.config.MARKET_DURATION
            )
            self.logger.info("✅ Scanner ready")
            
            # 4. Initialize pair trader
            self.logger.info("💰 Initializing pair trader...")
            self.pair_trader = PairTrader(
                client=self.client,
                config=self.config
            )
            self.logger.info("✅ Pair trader ready")
            
            # 5. Initialize sniper
            self.logger.info("🎯 Initializing last-second sniper...")
            self.sniper = LastSecondSniper(
                client=self.client,
                config=self.config
            )
            self.logger.info("✅ Sniper ready")
            
            # 6. Initialize monitor
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
        """Print startup banner"""
        banner = f"""
╔═══════════════════════════════════════════════════════════════╗
║           POLYMARKET HYBRID TRADING BOT                       ║
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
   
🎯 Sniping Mode (Last 60s):
   Trigger Time:       {self.config.SNIPE_TRIGGER_SECONDS}s before settlement
   Min Price:          ${self.config.SNIPE_MIN_PRICE}
   Max Price:          ${self.config.SNIPE_MAX_PRICE}
   Snipe Size:         ${self.config.SNIPE_SIZE_USD}
   
⚙️  Settings:
   Dry Run:            {self.config.DRY_RUN}
   Polling:            {self.config.POLLING_INTERVAL}s
   Max Daily Loss:     ${self.config.MAX_DAILY_LOSS}
   
🔐 Wallet:
   Address:            {self.config.PROXY_ADDRESS[:10]}...{self.config.PROXY_ADDRESS[-8:]}
   
{'='*67}
"""
        print(banner)
    
    async def run(self):
        """Main bot loop (async)"""
        self.running = True
        self.print_banner()
        
        self.logger.info("🏁 Bot started - scanning for markets...")
        
        check_count = 0
        
        try:
            while self.running:
                check_count += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                # 1. Find or update current market
                if not self.current_market:
                    self.logger.info(f"[{now}] Check #{check_count}: Scanning for active market...")
                    
                    market = await self.scanner.find_active_market_async()
                    
                    if market:
                        self.current_market = market
                        self.logger.info(f"🎯 MARKET FOUND!")
                        self.logger.info(f"   {market['title']}")
                        self.logger.info(f"   End Time: {market['end_time']}")
                        self.logger.info(f"   Outcomes: {market['outcomes']}")
                        
                        # Set up traders
                        self.pair_trader.set_market(market)
                        await self.sniper.set_market(market)
                        self.monitor.start_monitoring(market)
                    else:
                        self.logger.info(f"   ⏳ No active market, retrying in 30s...")
                        await asyncio.sleep(30)
                        continue
                
                # 2. Check time remaining and switch modes
                time_remaining = self._get_time_remaining()
                
                if time_remaining is None:
                    # Market ended
                    self.logger.info("📊 Market settled - generating report...")
                    self.monitor.generate_final_report()
                    self.current_market = None
                    self.trading_mode = None
                    continue
                
                # 3. Determine trading mode
                if time_remaining <= self.config.SNIPE_TRIGGER_SECONDS:
                    # Switch to SNIPING mode
                    if self.trading_mode != 'SNIPING':
                        self.logger.info(f"\n🎯 SWITCHING TO SNIPING MODE ({time_remaining}s remaining)")
                        self.trading_mode = 'SNIPING'
                        
                        # Cancel any open pair trading orders
                        self.pair_trader.cleanup()
                    
                    # Execute sniping
                    await self.sniper.execute_snipe()
                    
                else:
                    # Use PAIR_TRADING mode
                    if self.trading_mode != 'PAIR_TRADING':
                        self.logger.info(f"\n💰 PAIR TRADING MODE ({time_remaining}s remaining)")
                        self.trading_mode = 'PAIR_TRADING'
                    
                    # Execute pair trading
                    self.pair_trader.execute_trading_cycle()
                
                # 4. Update monitoring
                self.monitor.update()
                
                # 5. Wait before next cycle
                await asyncio.sleep(self.config.POLLING_INTERVAL)
                
        except KeyboardInterrupt:
            self.logger.info("\n⚠️ Keyboard interrupt")
        except Exception as e:
            self.logger.error(f"❌ Fatal error: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    def _get_time_remaining(self) -> int:
        """
        Get seconds remaining until market settlement
        Returns None if market ended
        """
        if not self.current_market:
            return None
        
        end_time_str = self.current_market.get('end_time')
        if not end_time_str:
            return None
        
        try:
            # Parse end time (ISO format)
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            now = datetime.now(end_time.tzinfo)
            
            remaining = (end_time - now).total_seconds()
            
            return max(0, int(remaining))
            
        except Exception as e:
            self.logger.error(f"Error calculating time remaining: {e}")
            return None
    
    def shutdown_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info("\n🛑 Shutdown signal received")
        self.running = False
    
    async def shutdown(self):
        """Clean shutdown"""
        self.logger.info("\n📊 Shutting down...")
        
        if self.monitor:
            self.logger.info("📈 Generating final report...")
            self.monitor.generate_final_report()
        
        if self.pair_trader:
            self.logger.info("💰 Closing pair trading positions...")
            self.pair_trader.cleanup()
        
        if self.sniper:
            self.logger.info("🎯 Closing sniper connections...")
            await self.sniper.cleanup()
        
        self.logger.info("✅ Shutdown complete. Goodbye! 👋\n")


def main():
    """Entry point"""
    
    # Check required env vars
    required_vars = ['PRIVATE_KEY', 'PROXY_ADDRESS']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print(f"❌ Missing required environment variables: {', '.join(missing)}")
        print("💡 Please create a .env file with required configuration")
        sys.exit(1)
    
    # Create and run bot
    bot = HybridTradingBot()
    
    try:
        bot.initialize()
        
        # Run async event loop
        asyncio.run(bot.run())
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()