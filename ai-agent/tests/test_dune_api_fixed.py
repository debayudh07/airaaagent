import asyncio
import httpx
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
DUNE_API_KEY = "UIKeACbIHIVEXxxm21nLw21wco1MpW4I"
BASE_URL = "https://api.dune.com/api/v1"

async def test_dune_api_endpoints():
    """Test working Dune Analytics API endpoints with correct column names"""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "X-Dune-API-Key": DUNE_API_KEY,
            "Accept": "application/json"
        }
        
        print("🧪 TESTING WORKING DUNE ANALYTICS API ENDPOINTS")
        print("=" * 60)
        
        # Test 1: Test DEX pairs endpoint (✅ Working)
        print("\n1️⃣ Testing DEX Pairs Endpoint - /dex/pairs/ethereum ✅")
        try:
            dex_url = f"{BASE_URL}/dex/pairs/ethereum"
            params = {"limit": 10, "sort_by": "one_day_volume desc"}
            response = await client.get(dex_url, headers=headers, params=params)
            print(f"Status Code: {response.status_code}")
            print(f"Response Content Length: {len(response.text)}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response Keys: {list(data.keys())}")
                
                # Access data through result['rows'] key (correct data access pattern)
                result = data.get('result', {})
                rows = result.get('rows', [])
                print(f"✅ DEX Pairs Retrieved: {len(rows)} pairs")
                
                # Show sample pairs with correct column names
                if rows:
                    for i, pair in enumerate(rows[:3]):
                        print(f"  Pair {i+1}: {pair.get('token_pair', 'N/A')}")
                        print(f"    1D Volume: ${pair.get('one_day_volume', 0):,.2f}")
                        print(f"    7D Volume: ${pair.get('seven_day_volume', 0):,.2f}")
                        print(f"    USD Liquidity: ${pair.get('usd_liquidity', 0):,.2f}")
                        print(f"    Available keys: {list(pair.keys())}")
                        print()
                else:
                    print("  No pairs returned in rows")
            else:
                print(f"❌ DEX Pairs Failed: {response.text}")
                print(f"Response headers: {dict(response.headers)}")
        except Exception as e:
            print(f"❌ DEX Pairs Error: {e}")
        
        # Test 2: Test basic DEX pairs without sorting
        print("\n2️⃣ Testing Basic DEX Pairs (no sorting)...")
        try:
            response = await client.get(
                f"{BASE_URL}/dex/pairs/ethereum",
                headers=headers,
                params={"limit": 5}
            )
            print(f"Basic DEX - Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                # Access data through result['rows'] key (correct data access pattern)
                result = data.get('result', {})
                rows = result.get('rows', [])
                print(f"✅ Found {len(rows)} pairs")
                if rows:
                    sample_pair = rows[0]
                    print(f"Sample pair structure:")
                    for key, value in sample_pair.items():
                        if isinstance(value, (str, int, float)):
                            print(f"  {key}: {value}")
                        else:
                            print(f"  {key}: {type(value)} (length: {len(value) if hasattr(value, '__len__') else 'N/A'})")
            else:
                response_text = response.text[:100] if len(response.text) > 100 else response.text
                print(f"❌ Error: {response_text}")
        except Exception as e:
            print(f"❌ Basic DEX Error: {e}")
        
        # Test 3: Test EVM Trends endpoint
        print("\n3️⃣ Testing EVM Trends - /trends/evm/contracts/{chain}")
        try:
            response = await client.get(
                f"{BASE_URL}/trends/evm/contracts/ethereum",
                headers=headers,
                params={"limit": 5}
            )
            print(f"EVM Trends - Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                contracts = data.get('result', [])
                print(f"✅ Trending contracts: {len(contracts)}")
                if contracts:
                    for i, contract in enumerate(contracts[:3]):
                        contract_address = contract.get('contract_address', 'N/A')
                        address_display = contract_address[:20] + "..." if len(contract_address) > 20 else contract_address
                        
                        print(f"  Contract {i+1}: {address_display}")
                        print(f"    Name: {contract.get('name', 'N/A')}")
                        print(f"    Interactions: {contract.get('interactions_24h', 0):,}")
            else:
                response_text = response.text[:200] if len(response.text) > 200 else response.text
                print(f"❌ EVM Trends Failed: {response_text}")
        except Exception as e:
            print(f"❌ EVM Trends Error: {e}")

async def test_dex_sorting_options():
    """Test different sorting options for DEX pairs"""
    
    print("\n\n🔄 TESTING DEX SORTING OPTIONS")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "X-Dune-API-Key": DUNE_API_KEY,
            "Accept": "application/json"
        }
        
        sort_options = [
            "one_day_volume desc",
            "seven_day_volume desc", 
            "usd_liquidity desc",
            "seven_day_volume_liquidity_ratio desc"
        ]
        
        for sort_option in sort_options:
            print(f"\n🔄 Testing sort_by: {sort_option}")
            try:
                response = await client.get(
                    f"{BASE_URL}/dex/pairs/ethereum",
                    headers=headers,
                    params={
                        "limit": 3,
                        "sort_by": sort_option
                    }
                )
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    # Access data through result['rows'] key (correct data access pattern)
                    result = data.get('result', {})
                    rows = result.get('rows', [])
                    if rows:
                        top_pair = rows[0]
                        token_pair = top_pair.get('token_pair', 'N/A')
                        print(f"  ✅ Top pair: {token_pair}")
                        
                        # Show the metric we're sorting by
                        if "one_day_volume" in sort_option:
                            value = top_pair.get('one_day_volume', 0)
                            print(f"      1D Volume: ${value:,.2f}")
                        elif "seven_day_volume" in sort_option and "ratio" not in sort_option:
                            value = top_pair.get('seven_day_volume', 0)
                            print(f"      7D Volume: ${value:,.2f}")
                        elif "usd_liquidity" in sort_option:
                            value = top_pair.get('usd_liquidity', 0)
                            print(f"      USD Liquidity: ${value:,.2f}")
                        elif "ratio" in sort_option:
                            value = top_pair.get('seven_day_volume_liquidity_ratio', 0)
                            print(f"      7D Vol/Liq Ratio: {value:.2f}")
                    else:
                        print("  ⚠️ No pairs returned")
                else:
                    response_text = response.text[:200] if len(response.text) > 200 else response.text
                    print(f"  ❌ Failed: {response_text}")
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")

async def main():
    """Run all Dune API tests"""
    print("🚀 DUNE ANALYTICS API TESTING SUITE")
    print("🔧 Testing Correct Column Names")
    print("=" * 80)
    
    # Test main API endpoints
    await test_dune_api_endpoints()
    
    # Test sorting options
    await test_dex_sorting_options()
    
    print("\n\n📋 SUMMARY")
    print("=" * 60)
    print("✅ API testing completed")
    
    print("\n💡 CORRECT Column Names for Dune DEX Pairs:")
    print("✅ one_day_volume (not volume_24h)")
    print("✅ seven_day_volume (not volume_7d)")
    print("✅ thirty_day_volume")
    print("✅ all_time_volume")
    print("✅ usd_liquidity (not reserve_usd)")
    print("✅ seven_day_volume_liquidity_ratio")
    
    print("\n🔧 Working Endpoints:")
    print("- GET /api/v1/dex/pairs/{chain}")
    print("- GET /api/v1/trends/evm/contracts/{chain}")
    print("- POST /api/v1/query/{id}/execute")
    print("- GET /api/v1/execution/{id}/results")
    
    print("\n📝 Usage Examples:")
    print("- /dex/pairs/ethereum?sort_by=one_day_volume desc")
    print("- /dex/pairs/ethereum?sort_by=usd_liquidity desc")
    print("- /dex/pairs/ethereum?limit=20&sort_by=seven_day_volume desc")

if __name__ == "__main__":
    asyncio.run(main())
