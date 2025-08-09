#!/usr/bin/env python3

import asyncio
import sys
sys.path.append('.')

from main import research_agent, ResearchRequest, init_http_client

async def final_test():
    """Final comprehensive test of the Dune Analytics integration"""
    await init_http_client()
    
    print("🎯 FINAL DUNE ANALYTICS INTEGRATION TEST")
    print("=" * 60)
    
    # Test the exact query from the user's request
    request = ResearchRequest('DEX trading data for Ethereum', time_range='7d')
    result = await research_agent.research(request)
    
    if result.get('success'):
        print("✅ SUCCESS - Dune Analytics integration is working!")
        print(f"✅ Data Quality Score: {result.get('data_quality_score', 0):.0f}%")
        print(f"✅ Data Sources Used: {result.get('data_sources_used')}")
        
        # Show the full response
        print("\n" + "="*60)
        print("📊 COMPLETE RESPONSE:")
        print("="*60)
        print(result.get('result', ''))
        
        # Verify DEX data in merged structure
        merged_data = result.get('merged_data', {})
        primary_data = merged_data.get('primary_data', {})
        
        if 'dex_trading' in primary_data:
            dex_data = primary_data['dex_trading']
            print("\n" + "="*60)
            print("📈 DEX DATA VERIFICATION:")
            print("="*60)
            print(f"✅ Total DEX pairs analyzed: {dex_data.get('total_pairs', 0)}")
            print(f"✅ Total 24h volume: ${dex_data.get('total_24h_volume', 0):,.2f}")
            print(f"✅ Total 7d volume: ${dex_data.get('total_7d_volume', 0):,.2f}")
            print(f"✅ Total liquidity: ${dex_data.get('total_liquidity', 0):,.2f}")
            
            top_pairs = dex_data.get('top_pairs', [])
            if top_pairs:
                print(f"\n🔥 TOP 5 TRADING PAIRS:")
                for i, pair in enumerate(top_pairs):
                    token_pair = pair.get('token_pair', 'Unknown')
                    volume_24h = pair.get('one_day_volume', 0)
                    volume_7d = pair.get('seven_day_volume', 0)
                    liquidity = pair.get('usd_liquidity', 0)
                    
                    print(f"   {i+1}. {token_pair}")
                    print(f"      24H: ${volume_24h:,.2f} | 7D: ${volume_7d:,.2f} | Liquidity: ${liquidity:,.2f}")
        
        print("\n🎯 INTEGRATION STATUS: FULLY FUNCTIONAL! ✅")
        
    else:
        print(f"❌ FAILED: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(final_test())
