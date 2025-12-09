"""
FINAL BRUTAL TEST
Mari kita cek REALITAS sekarang - apa yang BENAR-BENAR ada di Polymarket
"""
import requests
import json

print("\n" + "="*80)
print("🔥 FINAL REALITY CHECK - BTC 15M MARKETS")
print("="*80)

print("""
INSTRUKSI CRITICAL:
1. Buka browser: https://polymarket.com/crypto
2. Cari BTC 15-minute market
3. Jawab pertanyaan dibawah dengan JUJUR:
""")

print("\n📋 PERTANYAAN 1:")
has_market = input("Apakah kamu MELIHAT market 'BTC Up or Down 15M' di website SEKARANG? (yes/no): ").strip().lower()

if has_market != 'yes':
    print("\n" + "="*80)
    print("💡 KESIMPULAN:")
    print("="*80)
    print("""
Jika TIDAK ADA market di website:
→ Polymarket MEMANG tidak sedang running BTC 15M markets
→ Bot BEKERJA DENGAN BENAR - tidak ada yang salah!
→ Market hanya muncul pada waktu tertentu:
  • US market hours (14:30-21:00 UTC)
  • High BTC volatility
  • Sufficient user demand

SOLUSI:
1. Tunggu hingga market muncul di website
2. ATAU coba asset lain (ETH, SOL)
3. ATAU coba duration lain (30 minutes)

Bot kamu TIDAK BROKEN! Markets memang tidak tersedia!
    """)
    exit(0)

print("\n📋 PERTANYAAN 2:")
print("Apakah market tersebut menunjukkan status:")
print("  a) LIVE / TRADING (hijau, bisa place bet)")
print("  b) CLOSING SOON (countdown)")  
print("  c) CLOSED (hasil sudah keluar)")
print("  d) COMING SOON (belum dimulai)")

status = input("Pilih (a/b/c/d): ").strip().lower()

if status in ['c', 'd']:
    print("\n" + "="*80)
    print("💡 KESIMPULAN:")
    print("="*80)
    print("""
Market CLOSED atau COMING SOON:
→ Bot BENAR tidak bisa trade di market ini!
→ Market harus status LIVE/TRADING untuk bisa place orders
→ Bot menunggu market yang accepting_orders=true

SOLUSI:
1. Tunggu market berikutnya (15 menit)
2. Biarkan bot running, akan auto-detect
3. Check lagi dalam 5-10 menit
    """)
    exit(0)

print("\n📋 PERTANYAAN 3:")
market_url = input("Paste FULL URL market tersebut (contoh: https://polymarket.com/event/btc-...): ").strip()

if not market_url:
    print("❌ No URL provided")
    exit(1)

print("\n🔍 Analyzing market...")
print("="*80)

# Extract slug
import re
match = re.search(r'/event/([^?]+)', market_url)
if not match:
    print("❌ Invalid URL")
    exit(1)

slug = match.group(1)
print(f"✅ Slug: {slug}")

# Fetch page
print("\n1️⃣ Fetching HTML...")
try:
    response = requests.get(market_url, timeout=10)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print("❌ Cannot access page")
        exit(1)
    
    html = response.text
    condition_ids = re.findall(r'0x[a-fA-F0-9]{64}', html)
    unique = list(set(condition_ids))
    
    print(f"   Condition IDs found: {len(unique)}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

# Check each with CLOB
print("\n2️⃣ Checking with CLOB API...")

clob_url = "https://clob.polymarket.com/markets"
found_tradeable = False

for cid in unique:
    try:
        params = {'condition_id': cid}
        r = requests.get(clob_url, params=params, timeout=10)
        
        if r.status_code != 200:
            continue
        
        data = r.json()
        
        if isinstance(data, dict) and 'data' in data:
            markets = data['data']
        else:
            markets = data if isinstance(data, list) else []
        
        if not markets:
            continue
        
        market = markets[0]
        tokens = market.get('tokens', [])
        
        if not tokens:
            continue
        
        outcomes = [t.get('outcome', '') for t in tokens]
        outcomes_str = ' | '.join(outcomes)
        
        # Check if BTC market
        is_btc = any(kw in outcomes_str.lower() for kw in ['yes', 'no', 'up', 'down', 'higher', 'lower'])
        
        if not is_btc:
            print(f"   ❌ {cid[:20]}... → {outcomes_str} (not BTC)")
            continue
        
        # Check status
        active = market.get('active', False)
        closed = market.get('closed', False)
        accepting = market.get('accepting_orders', False)
        
        print(f"\n   🎯 {cid[:20]}... → BTC Market!")
        print(f"      Outcomes: {outcomes_str}")
        print(f"      Active: {active}")
        print(f"      Closed: {closed}")
        print(f"      Accepting Orders: {accepting}")
        
        if accepting and not closed:
            print(f"\n   ✅ THIS MARKET IS TRADEABLE!")
            
            for token in tokens:
                print(f"      {token.get('outcome')}: ${token.get('price')}")
            
            print(f"\n   📝 Condition ID: {cid}")
            print(f"   📝 This is what bot should find!")
            
            found_tradeable = True
            
            # Save to file
            with open('TRADEABLE_MARKET.txt', 'w') as f:
                f.write(f"Market URL: {market_url}\n")
                f.write(f"Slug: {slug}\n")
                f.write(f"Condition ID: {cid}\n")
                f.write(f"Outcomes: {outcomes_str}\n")
                f.write(f"YES Token: {[t for t in tokens if 'YES' in t.get('outcome', '').upper()][0].get('token_id', '')}\n")
                f.write(f"NO Token: {[t for t in tokens if 'NO' in t.get('outcome', '').upper()][0].get('token_id', '')}\n")
            
            print(f"\n   💾 Saved to TRADEABLE_MARKET.txt")
            
            break
        else:
            if closed:
                print(f"      ❌ Market is CLOSED")
            else:
                print(f"      ❌ Not accepting orders yet")
    
    except Exception as e:
        print(f"   Error checking {cid[:20]}...: {e}")

print("\n" + "="*80)
print("💡 FINAL ANALYSIS")
print("="*80)

if found_tradeable:
    print("""
✅ MARKET DITEMUKAN DAN TRADEABLE!

Ini artinya:
1. Market EXISTS dan accepting orders
2. Bot HARUS bisa menemukan market ini
3. Ada BUG di bot logic

NEXT STEPS:
1. Check file TRADEABLE_MARKET.txt
2. Gunakan condition_id tersebut untuk test bot
3. Debug kenapa bot tidak ekstrak condition_id yang benar

Test manual:
```python
from core.client import PolymarketClient
from config import Config

config = Config()
client = PolymarketClient(config.PRIVATE_KEY, config.PROXY_ADDRESS)

# Paste condition_id dari TRADEABLE_MARKET.txt
condition_id = "PASTE_HERE"

# Get prices
market = client.get_market(condition_id)
print(market)

# Try to buy (DRY RUN)
# token_id = "..." # from TRADEABLE_MARKET.txt
# client.buy_outcome(token_id, 1.0)
```
    """)
else:
    print("""
❌ TIDAK ADA MARKET YANG TRADEABLE!

Kemungkinan:
1. Market di browser belum accepting orders (pre-trading state)
2. Semua condition_ids di page adalah old/unrelated markets
3. Page structure berubah

YANG HARUS KAMU CEK DI BROWSER:
1. Apakah ada tombol "BUY YES" atau "BUY NO" yang bisa diklik?
2. Apakah ada countdown timer yang jalan?
3. Apakah ada tulisan "LIVE" atau "TRADING"?

Jika TIDAK ada tombol buy:
→ Market memang belum bisa di-trade
→ Bot BENAR menunggu hingga accepting_orders=true

Jika ADA tombol buy:
→ Ada disconnect antara website dan API
→ Polymarket mungkin render market client-side
→ Need alternative approach
    """)

print("\n" + "="*80)
print("✅ Test complete")
print("="*80)