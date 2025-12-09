"""
Polymarket Hybrid Trading Bot - FIXED VERSION
Uses improved MarketScanner with slug-based discovery
"""

import os
import sys
import asyncio
import signal
from datetime import datetime, timezone
from dotenv import load_dotenv

# Local imports
from core.client import PolymarketClient
from core.market_scanner import MarketScanner
from core.pair_trader import PairTrader
from core.last_second_sniper import LastSecondSniper
from core.monitor import TradeMonitor
from utils.logger import setup_logger
from config import Config

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
        self.markets_traded = 0
        
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
            
            # 2. Check allowances
            skip_allowance = os.getenv("SKIP_ALLOWANCE_CHECK", "false").lower() == "true"
            
            if not skip_allowance:
                self.logger.info("🔐 Checking USDC allowance...")
                if not self.client.check_allowance():
                    self.logger.warning("⚠️ Could not verify allowance via API")
                    self.logger.info("💡 If you ran 'python scripts/approve.py' successfully:")
                    self.logger.info("   Add to .env: SKIP_ALLOWANCE_CHECK=true")
                    
                    response = input("\nContinue anyway? (y/n): ").strip().lower()
                    if response != 'y':
                        raise Exception("Please run: python scripts/approve.py")
                else:
                    self.logger.info("✅ Allowance check passed")
            else:
                self.logger.info("⏭️ Skipping allowance check")
            
            # 3. Initialize scanner with config params
            self.logger.info(f"🔍 Initializing market scanner...")
            self.logger.info(f"   Asset: {self.config.ASSET}")
            self.logger.info(f"   Duration: {self.config.MARKET_DURATION} minutes")
            
            self.scanner = MarketScanner(
                asset=self.config.ASSET,
                duration=self.config.MARKET_DURATION
            )
            self.logger.info("✅ Scanner ready (slug + events + search)")
            
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
║                    FIXED VERSION                              ║
║                                                               ║
║  Strategy 1: Pair Trading (gabagool22)                       ║
║  Strategy 2: Last-Second Sniping                             ║
║                                                               ║
║  Scanner: Slug + Events + Markets (3-method discovery)       ║
╚═══════════════════════════════════════════════════════════════╝

📊 Configuration:
   Asset:              {self.config.ASSET}
   Duration:           {self.config.MARKET_DURATION} minutes
   Slug Pattern:       {self.config.ASSET.lower()}-updown-{self.config.MARKET_DURATION}m-{{timestamp}}
   
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
        consecutive_failures = 0
        max_failures = 10
        
        try:
            while self.running:
                check_count += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                # 1. Find or update current market
                if not self.current_market:
                    self.logger.info(f"[{now}] Check #{check_count}: Scanning for {self.config.ASSET} {self.config.MARKET_DURATION}min market...")
                    
                    try:
                        market = await self.scanner.find_active_market_async()
                        consecutive_failures = 0
                    except Exception as e:
                        self.logger.error(f"Scanner error: {e}")
                        consecutive_failures += 1
                        
                        if consecutive_failures >= max_failures:
                            self.logger.error(f"❌ Too many consecutive failures, stopping")
                            break
                        
                        await asyncio.sleep(30)
                        continue
                    
                    if market:
                        self.current_market = market
                        self.markets_traded += 1
                        
                        self.logger.info(f"🎯 MARKET #{self.markets_traded} FOUND!")
                        self.logger.info(f"   {market['question'][:70]}")
                        self.logger.info(f"   Slug: {market.get('slug', 'N/A')}")
                        self.logger.info(f"   End Time: {market.get('end_time', 'N/A')}")
                        self.logger.info(f"   YES: ${market['yes_price']:.4f}")
                        self.logger.info(f"   NO: ${market['no_price']:.4f}")
                        
                        pair_cost = market['yes_price'] + market['no_price']
                        self.logger.info(f"   Pair Cost: ${pair_cost:.4f}")
                        
                        # Set up traders
                        self.pair_trader.set_market(market)
                        await self.sniper.set_market(market)
                        self.monitor.start_monitoring(market)
                    else:
                        wait_time = 30
                        self.logger.info(f"   ⏳ No active market, retrying in {wait_time}s...")
                        self.logger.info(f"   💡 Markets may only be available during certain hours")
                        await asyncio.sleep(wait_time)
                        continue
                
                # 2. Check time remaining and switch modes
                time_remaining = self._get_time_remaining()
                
                if time_remaining is None or time_remaining <= 0:
                    # Market ended
                    self.logger.info("📊 Market settled - generating report...")
                    self.monitor.generate_final_report()
                    
                    # Reset for next market
                    self.current_market = None
                    self.trading_mode = None
                    
                    # Brief pause before scanning for next market
                    self.logger.info("⏳ Waiting 10s before scanning for next market...")
                    await asyncio.sleep(10)
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
        Returns None if market ended or no end time
        """
        if not self.current_market:
            return None
        
        end_time_str = self.current_market.get('end_time')
        
        if not end_time_str:
            # No end time available, estimate based on typical 15min duration
            self.logger.debug("No end_time in market data, using fallback")
            return 600  # Default to 10 minutes
        
        try:
            # Parse end time (handle various ISO formats)
            if end_time_str.endswith('Z'):
                end_time_str = end_time_str[:-1] + '+00:00'
            
            end_time = datetime.fromisoformat(end_time_str)
            
            # Make sure we have timezone-aware datetime
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            
            remaining = (end_time - now).total_seconds()
            
            return max(0, int(remaining))
            
        except Exception as e:
            self.logger.error(f"Error calculating time remaining: {e}")
            return 600  # Fallback
    
    def shutdown_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info("\n🛑 Shutdown signal received")
        self.running = False
    
    async def shutdown(self):
        """Clean shutdown"""
        self.logger.info("\n📊 Shutting down...")
        
        if self.monitor and self.current_market:
            self.logger.info("📈 Generating final report...")
            self.monitor.generate_final_report()
        
        if self.pair_trader:
            self.logger.info("💰 Closing pair trading positions...")
            self.pair_trader.cleanup()
        
        if self.sniper:
            self.logger.info("🎯 Closing sniper connections...")
            await self.sniper.cleanup()
        
        self.logger.info(f"\n📊 Session Summary:")
        self.logger.info(f"   Markets Traded: {self.markets_traded}")
        self.logger.info("✅ Shutdown complete. Goodbye! 👋\n")


def main():
    """Entry point"""
    
    print("\n" + "="*60)
    print("🚀 POLYMARKET HYBRID BOT - FIXED VERSION")
    print("="*60 + "\n")
    
    # Check required env vars
    required_vars = ['PRIVATE_KEY', 'PROXY_ADDRESS']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print(f"❌ Missing required environment variables: {', '.join(missing)}")
        print("\n💡 Please create a .env file with:")
        print("   PRIVATE_KEY=your_private_key_without_0x")
        print("   PROXY_ADDRESS=0xYourPolymarketWallet")
        sys.exit(1)
    
    # Create and run bot
    bot = HybridTradingBot()
    
    try:
        bot.initialize()
        
        # Run async event loop
        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        print("\n⚠️ Stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()