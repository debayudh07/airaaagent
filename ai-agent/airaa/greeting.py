"""Small-talk detection and canned replies (no LLM or data calls needed)."""
from __future__ import annotations

import random
import re
from typing import Any, Dict, Optional


_GREETING_PHRASES = [
    "hi", "hello", "hey", "hiya", "howdy", "greetings",
    "good morning", "good afternoon", "good evening", "good day",
    "what's up", "whats up", "how are you", "how're you", "how are you doing",
    "how's it going", "hows it going", "how's everything", "hows everything",
    "nice to meet you", "pleasure to meet you", "thanks", "thank you",
    "bye", "goodbye", "see you", "catch you later", "take care",
    "how do you do", "sup", "yo", "cheers",
]

_TASK_HINTS = (
    "price", "tvl", "apy", "yield", "volume", "market", "analy", "compare", "token",
    "coin", "defi", "wallet", "address", "0x", "gas", "chain", "stablecoin", "bridge",
    "fees", "swap", "dex", "whale", "invest", "btc", "eth", "sol", "bitcoin", "ethereum",
)


def detect_greeting(query: str) -> bool:
    """True only for short, pure small talk. A greeting followed by a real
    question ("hey, what's the BTC price?") must go through the research path."""
    cleaned = re.sub(r"[^\w\s'’]", " ", (query or "").lower()).strip()
    if not cleaned or len(cleaned.split()) > 6:
        return False
    if any(hint in cleaned for hint in _TASK_HINTS):
        return False
    return any(
        cleaned == g or cleaned.startswith(g + " ")
        for g in _GREETING_PHRASES
    )

def get_greeting_response(query: str, session_context: Optional[Dict[str, Any]] = None) -> str:
    """Generate appropriate AI greeting responses"""
    query_lower = query.lower().strip()
    
    # Check if this is a returning user
    is_returning = session_context and session_context.get("message_count", 0) > 2
    
    # Morning greetings
    if any(word in query_lower for word in ["good morning", "morning"]):
        responses = [
            "Good morning! ☀️ Ready to dive into some Web3 research today? I can help you analyze crypto markets, track DeFi protocols, or explore blockchain data.",
            "Morning! 🌅 What crypto insights are you looking for today? I've got access to real-time market data, DeFi analytics, and blockchain metrics.",
            "Good morning! ⚡ Let's make today productive with some Web3 research. What would you like to explore?"
        ]
    
    # Evening greetings
    elif any(word in query_lower for word in ["good evening", "evening"]):
        responses = [
            "Good evening! 🌙 Perfect time to catch up on crypto markets. What Web3 data are you curious about?",
            "Evening! 🌆 The crypto markets never sleep, and neither do I. How can I help with your research tonight?",
            "Good evening! ✨ Ready to explore some blockchain insights? I can analyze anything from DeFi yields to market trends."
        ]
    
    # Afternoon greetings
    elif any(word in query_lower for word in ["good afternoon", "afternoon"]):
        responses = [
            "Good afternoon! 🌤️ Hope your day is going well! What crypto research can I help you with?",
            "Afternoon! ☀️ Time for some Web3 analysis? I'm here to help with market data, protocol insights, or blockchain metrics.",
            "Good afternoon! 🚀 Ready to explore the crypto universe? Let me know what you'd like to research."
        ]
    
    # How are you / How's it going
    elif any(phrase in query_lower for phrase in ["how are you", "how're you", "how's it going", "hows it going", "how are you doing"]):
        responses = [
            "I'm doing great, thanks for asking! 🤖 My circuits are buzzing with excitement to help you research Web3 data. What's on your crypto curiosity list today?",
            "Fantastic! 💫 I'm energized and ready to dive into some blockchain analytics. How can I assist with your crypto research?",
            "I'm excellent! 🔥 Always excited to help explore the fascinating world of Web3. What would you like to analyze today?",
            "Doing wonderfully! ⚡ My databases are fresh and my APIs are ready. What crypto insights are you looking for?"
        ]
    
    # What's up
    elif any(phrase in query_lower for phrase in ["what's up", "whats up", "sup", "wassup"]):
        responses = [
            "Hey there! 👋 Just here monitoring the crypto markets and ready to help with any Web3 research you need!",
            "Not much, just keeping tabs on DeFi protocols and blockchain metrics! 📊 What's up with you? Any crypto questions?",
            "Just analyzing the latest market movements! 📈 What brings you here today? Looking for some Web3 insights?",
            "Hey! 🚀 Just hanging out in the data streams, ready to help you explore the crypto universe. What's on your mind?"
        ]
    
    # Thank you
    elif any(phrase in query_lower for phrase in ["thanks", "thank you"]):
        responses = [
            "You're very welcome! 😊 Happy to help anytime with your Web3 research needs!",
            "My pleasure! 🌟 Always here when you need crypto insights or blockchain analysis.",
            "Absolutely! 💙 That's what I'm here for. Feel free to ask about any Web3 topics anytime!",
            "You're welcome! ⚡ I love helping people navigate the crypto space. Come back anytime!"
        ]
    
    # Basic greetings (hi, hello, hey)
    elif any(word in query_lower for word in ["hi", "hello", "hey", "hiya", "howdy"]):
        if is_returning:
            responses = [
                "Hey there! 👋 Welcome back! Ready for another round of Web3 research?",
                "Hello again! 🔄 Great to see you back. What crypto mysteries shall we solve today?",
                "Hi! 🌟 Nice to have you back for more blockchain exploration. What's your research focus this time?",
                "Hey! ⚡ Welcome back to the crypto research hub. What are we diving into today?"
            ]
        else:
            responses = [
                "Hello! 👋 Welcome to your Web3 Research Assistant! I can help you analyze crypto markets, DeFi protocols, blockchain data, and much more. What would you like to explore?",
                "Hi there! 🚀 I'm your AI-powered Web3 researcher. I can access real-time crypto data, analyze market trends, track DeFi yields, and provide comprehensive blockchain insights. What interests you today?",
                "Hey! 💫 Great to meet you! I specialize in Web3 research and can help with everything from token analysis to DeFi protocol deep-dives. What crypto topic are you curious about?",
                "Hello! ⚡ I'm here to help you navigate the crypto universe with data-driven insights. Whether it's market analysis, protocol research, or blockchain metrics - I've got you covered. What shall we explore first?"
            ]
    
    # Goodbye
    elif any(word in query_lower for word in ["bye", "goodbye", "see you", "catch you later", "take care"]):
        responses = [
            "Goodbye! 👋 Thanks for exploring Web3 with me today. Come back anytime for more crypto insights!",
            "Take care! 🌟 Hope the research was helpful. I'll be here whenever you need more blockchain analysis!",
            "See you later! 🚀 Keep those crypto curiosities coming - I'm always ready to help!",
            "Farewell! ⚡ May your crypto journey be profitable and your DeFi yields be high! Come back soon!"
        ]
    
    # Default friendly response
    else:
        responses = [
            "Hello! 😊 I'm your Web3 Research Assistant, powered by AI and connected to live crypto data. How can I help you today?",
            "Hi there! 🤖 Ready to explore the crypto universe together? I can analyze markets, track protocols, and provide blockchain insights!",
            "Greetings! 🌟 I'm here to help with all your Web3 research needs. What crypto topic interests you today?"
        ]
    
    # Return a random response from the appropriate category
    return random.choice(responses)
