<div align="center">

# 🤖 AIRAA
### AI Research Agent for Blockchain Analytics

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat&logo=next.js&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat&logo=react&logoColor=black)](https://reactjs.org/)

**Your intelligent blockchain research companion powered by Google's Gemini AI**

</div>

---

## 🌟 Overview

AIRAA is an AI-powered blockchain research platform that combines Google's Gemini AI with multiple data sources (Dune Analytics, Etherscan, CoinMarketCap, DefiLlama) to provide comprehensive Web3 analytics through a conversational interface.

## ✨ Features

- 🤖 **AI-Powered Research**: Natural language queries powered by Gemini 2.0
- 📊 **Multi-Source Data**: Aggregates data from leading blockchain analytics platforms
- 💬 **Conversational Interface**: Context-aware chat with session memory
- 📈 **Data Visualization**: Interactive charts and customizable dashboards
- 🔗 **Web3 Integration**: Wallet connection via RainbowKit
- 🎨 **Modern UI**: Anime-inspired design with glass morphism effects

## 🏗️ Architecture

```
Frontend (Next.js + React)  ◄──REST API──►  Backend (Flask + LangChain)
       │                                              │
       └─ RainbowKit, Tailwind, Recharts             └─ Gemini AI, Data Tools
                                                             │
                                    ┌────────────────────────┼────────────────────────┐
                                    ▼                        ▼                        ▼
                              Dune Analytics          Etherscan              CoinMarketCap
                                                             │
                                                             ▼
                                                        DefiLlama
```

## 🔧 Tech Stack

**Backend**: Python 3.8+, Flask 3.0, LangChain 0.2, Google Gemini AI  
**Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS 4, RainbowKit, Wagmi  
**APIs**: Dune Analytics, Etherscan, CoinMarketCap, DefiLlama

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Node.js 18+
- API Keys:
  - [Google Gemini API](https://makersuite.google.com/app/apikey) (required)
  - [Dune Analytics](https://dune.com/settings/api) (optional)
  - [Etherscan](https://etherscan.io/myapikey) (optional)
  - [CoinMarketCap](https://pro.coinmarketcap.com/account) (optional)

### Backend Setup

```bash
cd ai-agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
echo "GEMINI_API_KEY=your_key_here" > .env

python app.py
```

### Frontend Setup

```bash
cd client
npm install
npm run dev
```

Visit `http://localhost:3000` to access the application.

## 📚 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Check API and service status |
| `/api/research` | POST | Submit research queries |
| `/api/conversation/<session_id>` | GET | Retrieve chat history |
| `/api/sessions` | GET | List active sessions |

### Example Request

```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the current TVL of Uniswap V3?",
    "session_id": "my-session"
  }'
```

## 💡 Usage Examples

**Basic Query**: "What is Ethereum?"  
**DeFi Analysis**: "Compare TVL of Aave vs Compound"  
**Wallet Analysis**: "Analyze transactions for 0x..."  
**Market Data**: "Show me ETH price trends for the last week"

## 🚢 Deployment

### Docker

```bash
# Backend
docker build -t airaa-backend -f Dockerfile.backend .
docker run -p 8000:8000 --env-file .env airaa-backend

# Frontend
docker build -t airaa-frontend -f Dockerfile.frontend .
docker run -p 3000:3000 airaa-frontend
```

### Cloud Platforms

- **Backend**: Deploy to Render, Railway, or similar (see `deployment/render.yaml`)
- **Frontend**: Deploy to Vercel, Netlify, or similar

## 🛠️ Development

### Project Structure

```
airaaagent/
├── ai-agent/           # Backend (Flask + LangChain)
│   ├── app.py          # API routes
│   ├── main.py         # Research agent logic
│   └── requirements.txt
├── client/             # Frontend (Next.js + React)
│   ├── app/            # Pages and routes
│   ├── components/     # UI components
│   └── package.json
└── deployment/         # Deployment configs
```

### Testing

```bash
# Backend
cd ai-agent/tests
python test_conversation_memory.py

# Frontend
cd client
npm run build
npm run lint
```

## 🔒 Security

- Store API keys in `.env` files (never commit)
- Use HTTPS in production
- Configure CORS properly (`ALLOWED_ORIGINS`)
- Implement rate limiting
- Validate all inputs

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with:
- [LangChain](https://www.langchain.com/) - AI orchestration
- [Google Gemini](https://deepmind.google/technologies/gemini/) - AI model
- [Next.js](https://nextjs.org/) - React framework
- [Flask](https://flask.palletsprojects.com/) - Python web framework
- [RainbowKit](https://www.rainbowkit.com/) - Web3 wallet integration

Data providers: Dune Analytics, Etherscan, CoinMarketCap, DefiLlama

---

<div align="center">

**AIRAA** - Your Intelligent Blockchain Research Companion

[![GitHub stars](https://img.shields.io/github/stars/debayudh07/airaaagent?style=social)](https://github.com/debayudh07/airaaagent/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/debayudh07/airaaagent)](https://github.com/debayudh07/airaaagent/issues)

Made with 💜 by the AIRAA team | [Report Bug](https://github.com/debayudh07/airaaagent/issues) | [Request Feature](https://github.com/debayudh07/airaaagent/issues)

</div>
