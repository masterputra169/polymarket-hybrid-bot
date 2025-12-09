"""
BRUTAL CHECK - Find the EXACT market you see in browser
"""
import requests
import json
import time
from datetime import datetime

print("\n" + "="*80)
print("🔥 BRUTAL LIVE MARKET CHECK")
print("="*80)

print("""
INSTRUKSI:
1. Buka browser: https://polymarket.com/crypto
2. Cari market "BTC Up or Down - 15M" yang LIVE/TRADING
3. Copy FULL URL-nya (contoh: https://polymarket.com/event/btc-updown-15m-...)
4. Paste disini
""")

market_url = input("\n📝 Paste URL market yang SEDANG LIVE: ").strip()

if not market_url:
    print("❌ No URL provided. Using default timestamp...")
    now = int(time.time())
    interval = 900
    ts = (now // interval) * interval
    market_url = f"https://polymarket.com/event/btc-updown-15m-{ts}"

print(f"\n🔍 Checking: {market_url}")
print("="*80)

# Extract slug
import re
match = re.search(r'/event/([^?]+)', market_url)
if match:
    slug = match.group(1)
    print(f"✅ Slug: {slug}")
else:
    print("❌ Could not extract slug from URL")
    exit(1)

# Fetch page
print("\n1️⃣ Fetching HTML page...")
try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    response = requests.get(market_url, headers=headers, timeout=10)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print("❌ Page not accessible")
        exit(1)
    
    html = response.text
    print(f"   HTML Length: {len(html):,} chars")
    
    # Extract ALL condition_ids
    condition_ids = re.findall(r'0x[a-fA-F0-9]{64}', html)
    unique_ids = []
    seen = set()
    for cid in condition_ids:
        if cid not in seen:
            seen.add(cid)
            unique_ids.append(cid)
    
    print(f"   Found {len(unique_ids)} unique condition_ids")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

# Check EACH condition_id with CLOB
print("\n2️⃣ Checking EACH condition_id with CLOB API...")
print("-"*80)

clob_url = "https://clob.polymarket.com/markets"
btc_markets = []

for i, cid in enumerate(unique_ids, 1):
    print(f"\n{i}. {cid}")
    
    try:
        params = {'condition_id': cid}
        clob_response = requests.get(clob_url, params=params, timeout=10)
        
        if clob_response.status_code != 200:
            print(f"   ⚠️  CLOB API error: {clob_response.status_code}")
            continue
        
        data = clob_response.json()
        
        if isinstance(data, dict) and 'data' in data:
            markets = data['data']
        else:
            markets = data if isinstance(data, list) else []
        
        if not markets:
            print(f"   ⚠️  No market data")
            continue
        
        market = markets[0]
        
        # Extract info
        active = market.get('active', False)
        closed = market.get('closed', False)
        accepting = market.get('accepting_orders', False)
        end_date = market.get('end_date_iso', 'N/A')
        
        tokens = market.get('tokens', [])
        outcomes = [t.get('outcome', '') for t in tokens]
        outcomes_str = ' | '.join(outcomes)
        
        # Display
        print(f"   Outcomes: {outcomes_str}")
        print(f"   Active: {active}, Closed: {closed}, Accepting: {accepting}")
        print(f"   End Date: {end_date}")
        
        # Check if BTC market
        is_btc = any(kw in outcomes_str.lower() for kw in ['yes', 'no', 'higher', 'lower', 'up', 'down'])
        
        if is_btc:
            print(f"   ✅ THIS IS A BTC MARKET!")
            
            if accepting and not closed:
                print(f"   🎉 AND IT'S ACCEPTING ORDERS!")
                
                for token in tokens:
                    print(f"      {token.get('outcome')}: ${token.get('price')}")
                
                btc_markets.append({
                    'condition_id': cid,
                    'outcomes': outcomes_str,
                    'accepting': accepting,
                    'prices': {t.get('outcome'): t.get('price') for t in tokens}
                })
            else:
                if closed:
                    print(f"   ❌ But it's CLOSED")
                else:
                    print(f"   ❌ But NOT accepting orders")
        else:
            print(f"   ℹ️  Not BTC market: {outcomes_str[:50]}")
    
    except Exception as e:
        print(f"   ❌ Error: {e}")

# Summary
print("\n" + "="*80)
print("📊 SUMMARY")
print("="*80)

if btc_markets:
    print(f"\n✅ FOUND {len(btc_markets)} TRADEABLE BTC MARKET(S)!")
    
    for i, m in enumerate(btc_markets, 1):
        print(f"\n{i}. Condition ID: {m['condition_id']}")
        print(f"   Outcomes: {m['outcomes']}")
        print(f"   Accepting Orders: {m['accepting']}")
        print(f"   Prices: {m['prices']}")
    
    print("\n" + "="*80)
    print("🔧 NEXT STEP: Update bot to use this condition_id")
    print("="*80)
    
    print(f"""
Bot should be able to find this market!

If bot still can't find it, the issue is:
1. Bot's HTML parsing logic extracts WRONG condition_id
2. Bot's filtering logic is too strict
3. Bot checks at wrong timing

Let me know and I'll fix the exact issue!
""")
    
else:
    print(f"\n❌ NO TRADEABLE BTC MARKETS FOUND!")
    print(f"\nThis means:")
    print(f"1. The market you see in browser might NOT be accepting orders yet")
    print(f"2. Or it's in a different state (pre-trading, settling, etc)")
    print(f"3. Or the condition_ids on this page are all old/unrelated markets")
    
    print(f"\n🔍 What you should check:")
    print(f"1. Does the market in your browser say 'TRADING' or 'LIVE'?")
    print(f"2. Can you manually place a bet on it?")
    print(f"3. What's the countdown timer showing?")
    
    print(f"\nIf market IS tradeable in browser but bot can't find:")
    print(f"→ There's a mismatch between what browser shows and API returns")
    print(f"→ Polymarket might be using different data source for web vs API")

print("\n" + "="*80)
print("✅ Check complete!")
print("="*80)

print(f"\n💡 DEBUGGING TIP:")
print(f"If you found tradeable market above, try this:")
print(f"")
print(f"from core.client import PolymarketClient")
print(f"from config import Config")
print(f"")
print(f"config = Config()")
print(f"client = PolymarketClient(")
print(f"    private_key=config.PRIVATE_KEY,")
print(f"    proxy_address=config.PROXY_ADDRESS")
print(f")")
print(f"")
print(f"# Use the condition_id found above")
print(f"condition_id = 'PASTE_HERE'")
print(f"prices = client.get_prices(condition_id)")
print(f"print(prices)")
print(f"")
print(f"# Try to place test order (DRY_RUN=true)")
print(f"# client.buy_outcome(token_id='...', usd_amount=1.0)")
print("="*80)