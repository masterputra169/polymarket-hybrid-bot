"""
Chart Generator
Simplified version of gabagool22's visualization
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from datetime import datetime
from typing import List, Dict


class ChartGenerator:
    """Generate trading charts gabagool22 style"""
    
    def __init__(self, market_title: str = "Unknown Market"):
        self.market_title = market_title
    
    def generate_chart(self, trades: List[Dict], output_file: str = "chart.png"):
        """
        Generate chart from trades
        
        Args:
            trades: List of trade dictionaries
            output_file: Output filename
        """
        if not trades:
            print("⚠️ No trades to visualize")
            return
        
        # Sort by timestamp
        trades = sorted(trades, key=lambda x: x.get('timestamp', 0))
        
        # Calculate curves
        yes_exp, no_exp, net_exp = [], [], []
        yes_sh, no_sh = [], []
        
        yes_e = no_e = 0
        yes_s = no_s = 0
        
        for t in trades:
            cost = t['cost']
            shares = t['size']
            
            if t['side'] == 'YES':
                yes_e += cost
                yes_s += shares
            else:
                no_e += cost
                no_s += shares
            
            yes_exp.append(yes_e)
            no_exp.append(no_e)
            net_exp.append(yes_e + no_e)
            yes_sh.append(yes_s)
            no_sh.append(no_s)
        
        # Create figure
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10))
        fig.suptitle(f"Pair Trading: {self.market_title}", fontsize=14, fontweight='bold')
        
        x = range(len(trades))
        
        # 1. PRICE SCATTER
        for i, t in enumerate(trades):
            color = 'green' if t['side'] == 'YES' else 'red'
            marker = 'o'
            price_cents = t['price'] * 100
            
            ax1.scatter(i, price_cents, color=color, marker=marker, s=60, alpha=0.8)
        
        ax1.set_title("Trade Prices")
        ax1.set_ylabel("Price (cents)")
        ax1.set_ylim(0, 100)
        ax1.grid(alpha=0.3)
        ax1.axhline(y=50, color='gray', linestyle='--', alpha=0.5)
        
        # 2. DOLLAR EXPOSURE
        ax2.plot(x, yes_exp, 'g-', linewidth=2, label='YES Exposure')
        ax2.plot(x, no_exp, 'r-', linewidth=2, label='NO Exposure')
        ax2.plot(x, net_exp, 'b-', linewidth=2, label='NET Exposure')
        ax2.fill_between(x, yes_exp, alpha=0.1, color='green')
        ax2.fill_between(x, no_exp, alpha=0.1, color='red')
        
        ax2.set_title("Dollar Exposure")
        ax2.set_ylabel("Exposure ($)")
        ax2.legend(loc='upper left')
        ax2.grid(alpha=0.3)
        
        # Annotations
        if len(yes_exp) > 0:
            ax2.annotate(f"${yes_exp[-1]:.2f}", xy=(len(x)-1, yes_exp[-1]), 
                        xytext=(5, 0), textcoords='offset points', color='green')
            ax2.annotate(f"${no_exp[-1]:.2f}", xy=(len(x)-1, no_exp[-1]),
                        xytext=(5, 0), textcoords='offset points', color='red')
            ax2.annotate(f"${net_exp[-1]:.2f}", xy=(len(x)-1, net_exp[-1]),
                        xytext=(5, 0), textcoords='offset points', color='blue')
        
        # 3. SHARES EXPOSURE
        ax3.plot(x, yes_sh, 'g-', linewidth=2, label='YES Shares')
        ax3.plot(x, no_sh, 'r-', linewidth=2, label='NO Shares')
        ax3.fill_between(x, yes_sh, alpha=0.1, color='green')
        ax3.fill_between(x, no_sh, alpha=0.1, color='red')
        
        ax3.set_title("Shares Exposure")
        ax3.set_ylabel("Shares")
        ax3.set_xlabel("Trade #")
        ax3.legend(loc='upper left')
        ax3.grid(alpha=0.3)
        
        # Annotations
        if len(yes_sh) > 0:
            ax3.annotate(f"{yes_sh[-1]:.2f} sh", xy=(len(x)-1, yes_sh[-1]),
                        xytext=(5, 0), textcoords='offset points', color='green')
            ax3.annotate(f"{no_sh[-1]:.2f} sh", xy=(len(x)-1, no_sh[-1]),
                        xytext=(5, 0), textcoords='offset points', color='red')
        
        # Summary text
        total_spent = net_exp[-1] if net_exp else 0
        min_shares = min(yes_sh[-1], no_sh[-1]) if yes_sh and no_sh else 0
        profit = min_shares - total_spent
        
        summary = (
            f"Total Spent: ${total_spent:.2f}\n"
            f"Min Shares: {min_shares:.2f}\n"
            f"Profit: ${profit:.2f}"
        )
        
        fig.text(0.99, 0.01, summary, ha='right', va='bottom',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                fontsize=10)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()


# Test function
def test_chart():
    """Test chart generation with dummy data"""
    
    # Create dummy trades
    trades = []
    base_time = 1700000000
    
    for i in range(20):
        # Alternate between YES and NO
        side = 'YES' if i % 2 == 0 else 'NO'
        price = 0.45 + (i * 0.01)
        size = 1.0 + (i * 0.1)
        
        trade = {
            'timestamp': base_time + (i * 30),
            'side': side,
            'outcome': 'Up' if side == 'YES' else 'Down',
            'price': price,
            'size': size,
            'cost': price * size
        }
        trades.append(trade)
    
    # Generate chart
    gen = ChartGenerator("Test Market - BTC 15min")
    gen.generate_chart(trades, "test_chart.png")
    
    print("✅ Test chart generated: test_chart.png")


if __name__ == "__main__":
    test_chart()