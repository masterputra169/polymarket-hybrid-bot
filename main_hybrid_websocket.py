"""
Polymarket Hybrid Trading Bot - WEBSOCKET VERSION
Uses WebSocket for REAL-TIME market detection
"""

import os
import sys
import asyncio
import signal
from datetime import datetime
from dotenv import load_dotenv

# Local imports
from core.client import PolymarketClient
from core.websocket_scanner import WebSocketScanner
from core.pair_trader import PairTrader
from core.last_second_sniper import LastSecondSniper
from core.monitor import TradeMonitor
from utils.logger import setup_logger
from config import Config

load_dotenv()


class HybridTradingBotWebSocket:
    """
    Hybrid bot with WebSocket for INSTANT market detection
    """
    
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger("HybridBotWS")
        self.running = False
        
        # Components
        self.client = None
        self.scanner = None
        self.pair_trader = None
        self.sniper = None
        self.monitor = None
        
        # State
        self.current_market = None
        self.trading_mode = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)
    
    def initialize(self):
        """Initialize all components"""
        self.logger.info("🚀 Initializing Hybrid Trading Bot (WebSocket)...")
        
        try:
            # 1. Initialize client
            self.logger.info("📡 Connecting to Polymarket...")
            self.client = PolymarketClient(
                private_key=self.config.PRIVATE_KEY,
                proxy_address=self.config.PROXY_ADDRESS,
                chain_id=self.config.CHAIN_ID
            )
            self.logger.info("✅ Connected to Polymarket")
            
            # 2. Skip allowance check if configured
            skip_allowance_check = os.getenv("SKIP_ALLOWANCE_CHECK", "false").lower() == "true"
            
            if not skip_allowance_check:
                self.logger.info("🔐 Checking USDC allowance...")
                if not self.client.check_allowance():
                    self.logger.warning("⚠️  Could not verify allowance")
                    response = input("\nContinue anyway? (y/n): ").strip().lower()
                    if response != 'y':
                        raise Exception("Please run: python scripts/approve.py")
            
            # 3. Initialize WebSocket scanner
            self.logger.info("🔌 Initializing WebSocket scanner...")
            self.scanner = WebSocketScanner(on_market_found=self.on_market_found)
            self.logger.info("✅ WebSocket scanner ready")
            
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
║     POLYMARKET HYBRID BOT - WEBSOCKET EDITION                ║
║                                                               ║
║  🔌 Real-Time Market Detection via WebSocket                 ║
║  ⚡ INSTANT notification when market goes live                ║
╚═══════════════════════════════════════════════════════════════╝

📊 Configuration:
   Asset:              {self.config.ASSET}
   Duration:           {self.config.MARKET_DURATION} minutes
   
💰 Pair Trading Mode:
   Target Pair Cost:   < ${self.config.TARGET_PAIR_COST}
   Order Size:         ${self.config.ORDER_SIZE_USD}
   Max Per Side:       ${self.config.MAX_PER_SIDE}
   
🎯 Sniping Mode:
   Trigger Time:       {self.config.SNIPE_TRIGGER_SECONDS}s before settlement
   Snipe Size:         ${self.config.SNIPE_SIZE_USD}
   
⚙️  Settings:
   Dry Run:            {self.config.DRY_RUN}
   WebSocket:          ENABLED ✅
   
🔐 Wallet:
   Address:            {self.config.PROXY_ADDRESS[:10]}...{self.config.PROXY_ADDRESS[-8:]}
   
{'='*67}
"""
        print(banner)
    
    async def on_market_found(self, market: dict):
        """
        Callback when WebSocket finds a new market
        
        This is called INSTANTLY when market becomes available!
        """
        self.logger.info("🎉 NEW MARKET DETECTED VIA WEBSOCKET!")
        self.logger.info(f"   {market['title']}")
        
        self.current_market = market
        
        # Setup traders
        self.pair_trader.set_market(market)
        await self.sniper.set_market(market)
        self.monitor.start_monitoring(market)
        
        self.logger.info("✅ Market setup complete, starting trading!")
    
    async def run(self):
        """Main bot loop"""
        self.running = True
        self.print_banner()
        
        self.logger.info("🏁 Bot started - connecting to WebSocket...")
        
        try:
            # Start WebSocket scanner in background
            scanner_task = asyncio.create_task(self.scanner.start())
            
            # Main trading loop
            while self.running:
                if self.current_market:
                    # Market is active, execute trading logic
                    time_remaining = self._get_time_remaining()
                    
                    if time_remaining is None:
                        # Market ended
                        self.logger.info("📊 Market settled - generating report...")
                        self.monitor.generate_final_report()
                        self.current_market = None
                        self.trading_mode = None
                        continue
                    
                    # Determine mode
                    if time_remaining <= self.config.SNIPE_TRIGGER_SECONDS:
                        # Sniping mode
                        if self.trading_mode != 'SNIPING':
                            self.logger.info(f"\n🎯 SNIPING MODE ({time_remaining}s)")
                            self.trading_mode = 'SNIPING'
                            self.pair_trader.cleanup()
                        
                        await self.sniper.execute_snipe()
                    
                    else:
                        # Pair trading mode
                        if self.trading_mode != 'PAIR_TRADING':
                            self.logger.info(f"\n💰 PAIR TRADING MODE ({time_remaining}s)")
                            self.trading_mode = 'PAIR_TRADING'
                        
                        self.pair_trader.execute_trading_cycle()
                    
                    # Update monitor
                    self.monitor.update()
                    
                    # Wait before next cycle
                    await asyncio.sleep(self.config.POLLING_INTERVAL)
                
                else:
                    # No market yet, WebSocket will notify when available
                    await asyncio.sleep(1)
            
            # Cleanup
            scanner_task.cancel()
            try:
                await scanner_task
            except asyncio.CancelledError:
                pass
        
        except KeyboardInterrupt:
            self.logger.info("\n⚠️  Keyboard interrupt")
        except Exception as e:
            self.logger.error(f"❌ Fatal error: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    def _get_time_remaining(self) -> int:
        """Get seconds remaining until settlement"""
        if not self.current_market:
            return None
        
        end_time_str = self.current_market.get('end_time')
        if not end_time_str:
            return None
        
        try:
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            now = datetime.now(end_time.tzinfo)
            remaining = (end_time - now).total_seconds()
            return max(0, int(remaining))
        except Exception as e:
            self.logger.error(f"Error calculating time: {e}")
            return None
    
    def shutdown_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info("\n🛑 Shutdown signal received")
        self.running = False
    
    async def shutdown(self):
        """Clean shutdown"""
        self.logger.info("\n📊 Shutting down...")
        
        if self.monitor:
            self.monitor.generate_final_report()
        
        if self.pair_trader:
            self.pair_trader.cleanup()
        
        if self.sniper:
            await self.sniper.cleanup()
        
        if self.scanner:
            await self.scanner.stop()
        
        self.logger.info("✅ Shutdown complete. Goodbye! 👋\n")


def main():
    """Entry point"""
    
    required_vars = ['PRIVATE_KEY', 'PROXY_ADDRESS']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print(f"❌ Missing: {', '.join(missing)}")
        sys.exit(1)
    
    bot = HybridTradingBotWebSocket()
    
    try:
        bot.initialize()
        asyncio.run(bot.run())
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()