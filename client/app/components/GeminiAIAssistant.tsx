/* eslint-disable */
'use client';

import { useState } from 'react';

interface GeminiAIAssistantProps {
  researchData?: any;
  onSuggestionSelect: (suggestion: string) => void;
}

export default function GeminiAIAssistant({ researchData, onSuggestionSelect }: GeminiAIAssistantProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState<Array<{role: 'user' | 'assistant', content: string}>>([]);
  const [loading, setLoading] = useState(false);

  const generateSmartSuggestions = (data: any): string[] => {
    if (!data) return [];

    const suggestions = [
      "Explain this data in simple terms",
      "What are the key insights from this analysis?",
      "How does this compare to market averages?",
      "What should I do based on these findings?",
      "Show me the most important metrics",
      "Generate a summary report",
      "What are the potential risks?",
      "Predict future trends based on this data"
    ];

    // Add data-specific suggestions
    if (typeof data === 'string' && data.toLowerCase().includes('bitcoin')) {
      suggestions.push("Compare Bitcoin to other cryptocurrencies");
    }
    if (typeof data === 'string' && data.toLowerCase().includes('defi')) {
      suggestions.push("Explain DeFi risks and opportunities");
    }
    if (typeof data === 'string' && data.toLowerCase().includes('ethereum')) {
      suggestions.push("Analyze Ethereum gas fees and network health");
    }

    return suggestions.slice(0, 6); // Limit to 6 suggestions
  };

  const callGeminiAPI = async (prompt: string) => {
    setLoading(true);
    
    try {
      const GEMINI_API_KEY = process.env.NEXT_PUBLIC_GEMINI_API_KEY;
      if (!GEMINI_API_KEY) {
        throw new Error('Missing NEXT_PUBLIC_GEMINI_API_KEY');
      }

      const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}` , {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          contents: [{
            parts: [{
              text: `You are an expert Web3 and cryptocurrency analyst. Based on the following research data, please ${prompt}:

${researchData ? (typeof researchData === 'string' ? researchData : JSON.stringify(researchData, null, 2)) : 'No research data available yet.'}

Please provide a concise, actionable response in a friendly, professional tone.`
            }]
          }],
          generationConfig: {
            temperature: 0.7,
            topK: 40,
            topP: 0.95,
            maxOutputTokens: 1024,
          }
        }),
      });

      const data = await response.json();
      
      if (data.candidates && data.candidates[0] && data.candidates[0].content) {
        const content = data.candidates[0].content.parts[0].text;
        setChatHistory(prev => [...prev, 
          { role: 'user', content: prompt },
          { role: 'assistant', content }
        ]);
      } else {
        throw new Error('Invalid response from Gemini API');
      }
    } catch (error) {
      setChatHistory(prev => [...prev, 
        { role: 'user', content: prompt },
        { role: 'assistant', content: `Sorry, I encountered an error: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.` }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleChatSubmit = async () => {
    if (!chatInput.trim()) return;
    
    const input = chatInput.trim();
    setChatInput('');
    await callGeminiAPI(input);
  };

  const suggestions = generateSmartSuggestions(researchData);

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {/* Chat Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-16 h-16 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full flex items-center justify-center shadow-2xl hover:scale-110 transition-all duration-300 hover:shadow-purple-500/25"
      >
        <span className="text-2xl">{isOpen ? '✕' : '🤖'}</span>
      </button>

      {/* Chat Interface */}
      {isOpen && (
        <div className="absolute bottom-20 right-0 w-96 h-96 bg-black/90 backdrop-blur-xl rounded-2xl border border-purple-500/30 shadow-2xl flex flex-col">
          {/* Header */}
          <div className="p-4 border-b border-purple-500/30">
            <h3 className="text-lg font-bold text-purple-400 flex items-center space-x-2">
              <span>🧠</span>
              <span>AI Assistant</span>
            </h3>
            <p className="text-xs text-gray-400">Powered by Gemini AI</p>
          </div>

          {/* Smart Suggestions */}
          {suggestions.length > 0 && !chatHistory.length && (
            <div className="p-4 border-b border-purple-500/20">
              <p className="text-sm text-cyan-400 mb-2">💡 Smart Suggestions:</p>
              <div className="space-y-1">
                {suggestions.slice(0, 3).map((suggestion, index) => (
                  <button
                    key={index}
                    onClick={() => callGeminiAPI(suggestion)}
                    className="w-full text-left px-2 py-1 text-xs bg-purple-600/20 hover:bg-purple-600/40 rounded text-gray-300 transition-all duration-200"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chat History */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {chatHistory.length === 0 && (
              <div className="text-center text-gray-500 mt-8">
                <p className="mb-2">👋 Hi! I'm your AI research assistant.</p>
                <p className="text-xs">Ask me anything about your Web3 research data!</p>
              </div>
            )}
            
            {chatHistory.map((message, index) => (
              <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] p-3 rounded-lg ${
                  message.role === 'user' 
                    ? 'bg-cyan-600/30 text-cyan-100' 
                    : 'bg-gray-800/50 text-gray-200'
                }`}>
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                </div>
              </div>
            ))}
            
            {loading && (
              <div className="flex justify-start">
                <div className="bg-gray-800/50 p-3 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <div className="w-4 h-4 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin"></div>
                    <span className="text-sm text-gray-400">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="p-4 border-t border-purple-500/30">
            <div className="flex space-x-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask about your research data..."
                className="flex-1 bg-gray-800/50 border border-gray-600/50 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-cyan-400 focus:outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleChatSubmit();
                  }
                }}
                disabled={loading}
              />
              <button
                onClick={handleChatSubmit}
                disabled={loading || !chatInput.trim()}
                className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-purple-600 rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:from-cyan-400 hover:to-purple-500 transition-all duration-300"
              >
                🚀
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}