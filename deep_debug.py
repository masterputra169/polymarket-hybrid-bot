"""
Deep Debug Tool
Analisis mendalam untuk menemukan masalah sebenarnya
"""
import requests
import json
import time
from datetime import datetime

print("\n" + "="*80)
print("🔬 DEEP ANALYSIS - Finding the REAL Problem")
print("="*80)

# ==========================================
# TEST 1: Direct URL Access
# ==========================================
print("\n📍 TEST 1: Testing direct market URLs you provided")
print("-"*80)

test_urls = [
    "https://polymarket.com/event/btc-updown-15m-1765204200",
    "https://polymarket.com/event/btc-updown-15m-1765205100"
]

for url in test_urls:
    print(f"\n   Testing: {url}")
    try:
        response = requests.get(url, timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   ✅ URL accessible")
            # Try to find condition_id in HTML
            html = response.text
            if 'condition' in html.lower():
                print(f"   📄 HTML contains 'condition'")
        else:
            print(f"   ❌ URL returned {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

# ==========================================
# TEST 2: Gamma API - Events Endpoint
# ==========================================
print("\n\n📍 TEST 2: Testing Gamma API Events endpoint")
print("-"*80)

# Extract slug from URL
slug = "btc-updown-15m-1765204200"
gamma_event_url = f"https://gamma-api.polymarket.com/events/{slug}"

print(f"\n   Trying: {gamma_event_url}")

try:
    response = requests.get(gamma_event_url, timeout=10)
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n   ✅ SUCCESS! Event data retrieved")
        print(f"\n   📊 Event Structure:")
        print(f"      Keys: {list(data.keys())}")
        
        if 'markets' in data:
            markets = data['markets']
            print(f"      Markets count: {len(markets)}")
            
            if markets:
                market = markets[0]
                print(f"\n   📈 Market Info:")
                print(f"      Question: {market.get('question', 'N/A')}")
                print(f"      Condition ID: {market.get('condition_id', 'N/A')[:30]}...")
                print(f"      Active: {market.get('active')}")
                print(f"      Closed: {market.get('closed')}")
                
                # Save for next test
                condition_id = market.get('condition_id')
        else:
            print(f"   ⚠️  No 'markets' key in response")
            print(f"   Response keys: {list(data.keys())}")
    else:
        print(f"   ❌ Failed with status {response.status_code}")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ==========================================
# TEST 3: CLOB API with Condition ID
# ==========================================
print("\n\n📍 TEST 3: Testing CLOB API with condition_id")
print("-"*80)

if 'condition_id' in locals():
    clob_url = "https://clob.polymarket.com/markets"
    params = {'condition_id': condition_id}
    
    print(f"\n   URL: {clob_url}")
    print(f"   Params: condition_id={condition_id[:30]}...")
    
    try:
        response = requests.get(clob_url, params=params, timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n   ✅ SUCCESS! CLOB data retrieved")
            
            # Check response structure
            if isinstance(data, dict) and 'data' in data:
                markets = data['data']
                print(f"   Response type: dict with 'data' key")
                print(f"   Markets count: {len(markets)}")
            elif isinstance(data, list):
                markets = data
                print(f"   Response type: list")
                print(f"   Markets count: {len(markets)}")
            else:
                print(f"   ⚠️  Unexpected response type: {type(data)}")
                markets = []
            
            if markets:
                market = markets[0]
                print(f"\n   📊 Market Details:")
                print(f"      Active: {market.get('active')}")
                print(f"      Closed: {market.get('closed')}")
                print(f"      Accepting Orders: {market.get('accepting_orders')}")
                print(f"      Tokens: {len(market.get('tokens', []))}")
                
                if market.get('tokens'):
                    print(f"\n   💰 Token Prices:")
                    for token in market['tokens']:
                        print(f"      {token.get('outcome')}: ${token.get('price')}")
                
                # Check if market is tradeable
                is_active = market.get('active', False)
                is_closed = market.get('closed', False)
                accepting = market.get('accepting_orders', False)
                has_tokens = len(market.get('tokens', [])) == 2
                
                print(f"\n   🔍 Validation:")
                print(f"      ✓ Active: {is_active}")
                print(f"      ✓ Not Closed: {not is_closed}")
                print(f"      ✓ Accepting Orders: {accepting}")
                print(f"      ✓ Has 2 Tokens: {has_tokens}")
                
                is_tradeable = is_active and not is_closed and accepting and has_tokens
                
                if is_tradeable:
                    print(f"\n   ✅ MARKET IS TRADEABLE!")
                else:
                    print(f"\n   ❌ MARKET NOT TRADEABLE")
                    if not accepting:
                        print(f"      Reason: Not accepting orders")
                    if is_closed:
                        print(f"      Reason: Market is closed")
        else:
            print(f"   ❌ Failed with status {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("   ⏭️  Skipped (no condition_id from previous test)")

# ==========================================
# TEST 4: Timestamp Calculation
# ==========================================
print("\n\n📍 TEST 4: Testing timestamp calculation logic")
print("-"*80)

now = int(time.time())
interval = 900  # 15 minutes

print(f"\n   Current timestamp: {now}")
print(f"   Current time: {datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')}")

print(f"\n   Testing different rounding methods:")

# Method 1: Floor division
ts_floor = (now // interval) * interval
print(f"   1. Floor: {ts_floor} → {datetime.fromtimestamp(ts_floor).strftime('%H:%M:%S')}")
print(f"      Slug: btc-updown-15m-{ts_floor}")

# Method 2: Round to nearest
ts_round = round(now / interval) * interval
print(f"   2. Round: {ts_round} → {datetime.fromtimestamp(ts_round).strftime('%H:%M:%S')}")
print(f"      Slug: btc-updown-15m-{ts_round}")

# Method 3: Ceiling
ts_ceil = ((now + interval - 1) // interval) * interval
print(f"   3. Ceiling: {ts_ceil} → {datetime.fromtimestamp(ts_ceil).strftime('%H:%M:%S')}")
print(f"      Slug: btc-updown-15m-{ts_ceil}")

# Try fetching with calculated timestamps
print(f"\n   Testing calculated slugs:")

for i, ts in enumerate([ts_floor, ts_round, ts_ceil], 1):
    slug = f"btc-updown-15m-{ts}"
    url = f"https://gamma-api.polymarket.com/events/{slug}"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('markets'):
                print(f"   ✅ Method {i} WORKS! Slug: {slug}")
                break
        else:
            print(f"   ❌ Method {i} failed (status {response.status_code})")
    except:
        print(f"   ❌ Method {i} error")

# ==========================================
# TEST 5: Search for ANY active BTC market
# ==========================================
print("\n\n📍 TEST 5: Searching for ANY active BTC 15M market")
print("-"*80)

gamma_markets_url = "https://gamma-api.polymarket.com/markets"
params = {
    'limit': 20,
    'active': 'true',
    'closed': 'false'
}

print(f"\n   URL: {gamma_markets_url}")
print(f"   Params: {params}")

try:
    response = requests.get(gamma_markets_url, params=params, timeout=10)
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        markets = response.json()
        print(f"\n   ✅ Retrieved {len(markets)} active markets")
        
        # Filter for BTC 15M
        btc_markets = []
        
        for market in markets:
            question = market.get('question', '').lower()
            
            if any(kw in question for kw in ['btc', 'bitcoin']):
                if any(kw in question for kw in ['15 minute', '15min', '15m']):
                    btc_markets.append(market)
        
        print(f"   🎯 Found {len(btc_markets)} BTC 15-minute markets")
        
        if btc_markets:
            print(f"\n   📋 BTC 15M Markets:")
            for i, m in enumerate(btc_markets[:5], 1):
                print(f"\n   {i}. {m.get('question', 'N/A')[:70]}")
                print(f"      Slug: {m.get('slug', 'N/A')}")
                print(f"      Condition ID: {m.get('condition_id', 'N/A')[:30]}...")
                print(f"      Active: {m.get('active')}")
                print(f"      Closed: {m.get('closed')}")
        else:
            print(f"\n   ⚠️  NO BTC 15-minute markets in active list")
            print(f"\n   Sample of what's available:")
            for i, m in enumerate(markets[:3], 1):
                print(f"   {i}. {m.get('question', 'N/A')[:70]}")
    else:
        print(f"   ❌ Failed with status {response.status_code}")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ==========================================
# SUMMARY & RECOMMENDATIONS
# ==========================================
print("\n\n" + "="*80)
print("📊 ANALYSIS SUMMARY")
print("="*80)

print("""
Based on the tests above, the problem is likely one of:

1. ⏰ TIMING ISSUE
   - Markets only active during specific times
   - Your timezone vs market timezone mismatch
   - Between market rounds (15-min gaps)

2. 🔗 API ENDPOINT ISSUE
   - Using wrong endpoint structure
   - API response format changed
   - Authentication needed

3. 🎯 FILTERING LOGIC ISSUE
   - Markets exist but bot filters them out
   - Validation criteria too strict
   - Field names don't match

4. 📍 SLUG FORMAT ISSUE
   - Timestamp calculation wrong
   - Slug pattern changed by Polymarket
   - Need different URL format

Check which TEST above succeeded to identify the issue!
""")

print("="*80)
print("✅ Analysis complete!")
print("="*80)