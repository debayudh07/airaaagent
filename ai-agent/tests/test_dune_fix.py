#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.append('.')

from main import research_agent, ResearchRequest, init_http_client

async def test_dune_fix():
    """Test the fixed Dune Analytics integration"""
    await init_http_client()
    
    print("=== DUNE ANALYTICS INTEGRATION TEST ===")
    print("Testing DEX query with fixed data access pattern...")
    
    # Test with a DEX query
    request = ResearchRequest('DEX trading data for Ethereum', time_range='7d')
    result = await research_agent.research(request)
    
    print(f"Success: {result.get('success')}")
    print(f"Data Sources: {result.get('data_sources_used')}")
    print(f"Query Intent: {result.get('query_intent')}")
    print(f"Data Quality Score: {result.get('data_quality_score', 0):.0f}%")
    
    if result.get('success'):
        print("✅ Dune Analytics integration working!")
        
        # Check if Dune data was actually retrieved
        tool_results = result.get('tool_results', [])
        dune_results = [r for r in tool_results if 'dune' in r.get('source', '')]
        
        if dune_results:
            dune_result = dune_results[0]
            print(f"✅ Dune tool executed successfully: {dune_result.get('success')}")
            if dune_result.get('success'):
                data = dune_result.get('data', [])
                print(f"✅ Retrieved {len(data) if isinstance(data, list) else 0} DEX pairs")
                
                # Show sample data structure
                if isinstance(data, list) and len(data) > 0:
                    sample_pair = data[0]
                    print("✅ Sample pair structure:")
                    for key in ['token_pair', 'one_day_volume', 'seven_day_volume', 'usd_liquidity']:
                        if key in sample_pair:
                            value = sample_pair[key]
                            if isinstance(value, (int, float)):
                                print(f"   {key}: ${value:,.2f}" if 'volume' in key or 'liquidity' in key else f"   {key}: {value}")
                            else:
                                print(f"   {key}: {value}")
            else:
                print(f"❌ Dune tool failed: {dune_result.get('error', 'Unknown error')}")
        else:
            print("⚠️  No Dune results found in tool_results")
    else:
        print(f"❌ Research failed: {result.get('error')}")
    
    print("\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(test_dune_fix())
