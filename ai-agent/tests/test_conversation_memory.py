#!/usr/bin/env python3
"""
Test script to verify conversation memory functionality
"""

import asyncio
from main import OptimizedWeb3ResearchAgent, ResearchRequest, init_http_client, session_manager

async def test_conversation_memory():
    """Test conversation memory functionality"""
    print("🧪 Testing Conversation Memory...")
    
    # Initialize HTTP client
    await init_http_client()
    
    # Create agent with session
    session_id = "test-session-001"
    agent = OptimizedWeb3ResearchAgent(session_id=session_id)
    
    print(f"✅ Created agent with session: {session_id}")
    
    # First query
    print("\n📝 First Query: About Bitcoin...")
    request1 = ResearchRequest(
        query="Tell me about Bitcoin's current price",
        session_id=session_id
    )
    
    result1 = await agent.research(request1)
    print(f"✅ First query completed. Success: {result1['success']}")
    print(f"📊 Messages in session: {agent.session['message_count']}")
    
    # Second query (should reference first)
    print("\n📝 Second Query: Follow-up question...")
    request2 = ResearchRequest(
        query="How does that compare to last week?",
        session_id=session_id
    )
    
    result2 = await agent.research(request2)
    print(f"✅ Second query completed. Success: {result2['success']}")
    print(f"📊 Messages in session: {agent.session['message_count']}")
    
    # Check conversation history
    print("\n💬 Conversation History:")
    chat_history = agent.session["chat_history"]
    for i, msg in enumerate(chat_history.messages):
        msg_type = "👤 User" if msg.__class__.__name__ == "HumanMessage" else "🤖 AI"
        content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
        print(f"{i+1}. {msg_type}: {content_preview}")
    
    # Test session manager
    print(f"\n🔍 Session Manager Stats:")
    print(f"Active sessions: {len(session_manager.sessions)}")
    print(f"Session info: {session_manager.sessions[session_id]['message_count']} messages")
    
    print("\n✨ Conversation memory test completed!")

if __name__ == "__main__":
    asyncio.run(test_conversation_memory())
