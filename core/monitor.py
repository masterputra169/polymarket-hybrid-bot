"""
Trade Monitor Module
Real-time monitoring and chart generation (gabagool22 style)
"""
import json
import time
from datetime import datetime
from typing import Dict, List, Optional


class TradeMonitor:
    """
    Monitor trades and generate visualizations
    Based on gabagool22's charting approach
    
    Works with both pair_trader and sniper
    """
    
    def __init__(self, config, pair_trader=None, sniper=None):
        """
        Initialize monitor
        
        Args:
            config: Bot configuration
            pair_trader: PairTrader instance (optional)
            sniper: LastSecondSniper instance (optional)
        """
        self.config = config
        self.pair_trader = pair_trader
        self.sniper = sniper
        
        # Chart generator
        self.chart_gen = None
        
        # Monitoring state
        self.market = None
        self.last_chart_update = 0
        self.update_count = 0
    
    def start_monitoring(self, market: Dict):
        """Start monitoring a new market"""
        self.market = market
        
        # Import here to avoid circular import
        from utils.chart_generator import ChartGenerator
        self.chart_gen = ChartGenerator(market['title'])
        
        self.last_chart_update = time.time()
        
        print(f"\n📊 Monitoring started for: {market['title']}")
    
    def update(self):
        """Update monitoring (called each cycle)"""
        self.update_count += 1
        
        # Print position summary every 10 cycles
        if self.update_count % 10 == 0:
            self._print_position_summary()
        
        # Update chart periodically
        if self.config.AUTO_GENERATE_CHART:
            now = time.time()
            
            if now - self.last_chart_update >= self.config.CHART_UPDATE_INTERVAL:
                self._update_chart()
                self.last_chart_update = now
    
    def _print_position_summary(self):
        """Print current position summary"""
        if not self.pair_trader:
            return
            
        pos = self.pair_trader.get_current_position()
        
        print(f"\n📊 Position Summary:")
        print(f"   YES: {pos['yes_shares']:.2f} shares (${pos['yes_spent']:.2f})")
        print(f"   NO:  {pos['no_shares']:.2f} shares (${pos['no_spent']:.2f})")
        print(f"   Total Spent: ${pos['total_spent']:.2f}")
        print(f"   Min Shares: {pos['min_shares']:.2f}")
        print(f"   Potential Profit: ${pos['potential_profit']:.2f} ({pos['profit_margin']:.2f}%)")
        print(f"   Imbalance: {pos['imbalance']*100:.1f}%")
    
    def _update_chart(self):
        """Generate updated chart"""
        if not self.pair_trader:
            return
            
        trades = self.pair_trader.get_trades()
        
        if not trades:
            return
        
        print(f"\n📈 Generating chart ({len(trades)} trades)...")
        
        try:
            self.chart_gen.generate_chart(trades, "chart_live.png")
            print(f"   ✅ Chart saved as chart_live.png")
        except Exception as e:
            print(f"   ❌ Error generating chart: {e}")
    
    def generate_final_report(self):
        """Generate final report and chart"""
        if not self.market:
            return
        
        print(f"\n" + "="*70)
        print(f"📊 FINAL REPORT")
        print(f"="*70)
        
        # 1. Pair Trading Position (if available)
        if self.pair_trader:
            pos = self.pair_trader.get_current_position()
            
            print(f"\n💰 Pair Trading Position:")
            print(f"   Market: {self.market['title']}")
            print(f"   YES: {pos['yes_shares']:.2f} shares (${pos['yes_spent']:.2f})")
            print(f"   NO:  {pos['no_shares']:.2f} shares (${pos['no_spent']:.2f})")
            print(f"   Total Spent: ${pos['total_spent']:.2f}")
            print(f"   Min Shares: {pos['min_shares']:.2f}")
            
            # Profit calculation
            print(f"\n📈 Profit Analysis:")
            print(f"   Guaranteed Value: ${pos['guaranteed_value']:.2f}")
            print(f"   Potential Profit: ${pos['potential_profit']:.2f}")
            print(f"   Profit Margin: {pos['profit_margin']:.2f}%")
            
            # Trade statistics
            trades = self.pair_trader.get_trades()
        else:
            trades = []
        
        # 2. Sniper Summary (if available)
        if self.sniper:
            snipe_summary = self.sniper.get_snipe_summary()
            
            print(f"\n🎯 Sniper Summary:")
            print(f"   Sniped: {snipe_summary['sniped']}")
            
            if snipe_summary['sniped']:
                print(f"   Side: {snipe_summary['winning_side']}")
                print(f"   Price: ${snipe_summary['best_ask']:.4f}")
                print(f"   Time: {snipe_summary['snipe_time']}")
        
        # 3. Combined trades
        if trades:
            yes_trades = [t for t in trades if t['side'] == 'YES']
            no_trades = [t for t in trades if t['side'] == 'NO']
            
            print(f"\n📊 Trade Statistics:")
            print(f"   Total Trades: {len(trades)}")
            print(f"   YES Trades: {len(yes_trades)}")
            print(f"   NO Trades: {len(no_trades)}")
            
            if yes_trades:
                avg_yes_price = sum(t['price'] for t in yes_trades) / len(yes_trades)
                print(f"   Avg YES Price: ${avg_yes_price:.4f}")
            
            if no_trades:
                avg_no_price = sum(t['price'] for t in no_trades) / len(no_trades)
                print(f"   Avg NO Price: ${avg_no_price:.4f}")
            
            if yes_trades and no_trades:
                avg_pair_cost = avg_yes_price + avg_no_price
                print(f"   Avg Pair Cost: ${avg_pair_cost:.4f}")
                
                profit_margin = (1.0 - avg_pair_cost) / avg_pair_cost * 100
                print(f"   Theoretical Margin: {profit_margin:.2f}%")
        
        # 4. Save trades to JSON
        if trades:
            self._save_trades_json(trades)
        
        # 5. Generate final chart
        if trades and self.chart_gen:
            print(f"\n📈 Generating final chart...")
            try:
                self.chart_gen.generate_chart(trades, "chart_final.png")
                print(f"   ✅ Final chart saved as chart_final.png")
            except Exception as e:
                print(f"   ❌ Error generating chart: {e}")
        
        # 6. Generate text report
        if self.pair_trader:
            self._save_text_report(pos, trades)
        
        print(f"\n" + "="*70)
        print(f"✅ Final report complete")
        print(f"="*70)
    
    def _save_trades_json(self, trades: List[Dict]):
        """Save trades to JSON file"""
        filename = f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(trades, f, indent=2)
            
            print(f"   💾 Trades saved to {filename}")
        except Exception as e:
            print(f"   ❌ Error saving trades: {e}")
    
    def _save_text_report(self, position: Dict, trades: List[Dict]):
        """Save text report"""
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        lines = []
        lines.append("="*70)
        lines.append("POLYMARKET PAIR TRADING - SESSION REPORT")
        lines.append("="*70)
        lines.append("")
        
        # Market info
        lines.append(f"Market: {self.market['title']}")
        lines.append(f"Condition ID: {self.market['condition_id']}")
        lines.append(f"Outcomes: {self.market['outcomes']}")
        lines.append("")
        
        # Position
        lines.append("FINAL POSITION:")
        lines.append(f"  YES Shares: {position['yes_shares']:.2f} (${position['yes_spent']:.2f})")
        lines.append(f"  NO Shares:  {position['no_shares']:.2f} (${position['no_spent']:.2f})")
        lines.append(f"  Total Spent: ${position['total_spent']:.2f}")
        lines.append(f"  Min Shares: {position['min_shares']:.2f}")
        lines.append(f"  Potential Profit: ${position['potential_profit']:.2f} ({position['profit_margin']:.2f}%)")
        lines.append("")
        
        # Trades
        if trades:
            lines.append("TRADES:")
            lines.append("")
            lines.append("Time                | Side | Price    | Shares   | Cost")
            lines.append("-" * 60)
            
            for trade in trades:
                ts = datetime.fromtimestamp(trade['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                lines.append(
                    f"{ts} | {trade['side']:4s} | "
                    f"${trade['price']:.4f} | "
                    f"{trade['size']:8.2f} | "
                    f"${trade['cost']:7.2f}"
                )
        
        lines.append("")
        lines.append("="*70)
        
        try:
            with open(filename, 'w') as f:
                f.write('\n'.join(lines))
            
            print(f"   📄 Text report saved to {filename}")
        except Exception as e:
            print(f"   ❌ Error saving report: {e}")