# AIRAA - AI Research Agent for Blockchain Analytics

![AIRAA Banner](https://img.shields.io/badge/AIRAA-Web3%20Research%20Agent-blue?style=for-the-badge&logo=ethereum)

**AIRAA** (AI Research Agent for Analytics) is a comprehensive Web3 research platform that combines the power of AI with blockchain data analytics. It features an intelligent backend research agent powered by Google's Gemini AI and a modern, anime-inspired frontend interface.

## 🌟 Overview

AIRAA provides comprehensive blockchain research capabilities through a conversational AI interface. Users can query DeFi protocols, analyze wallet addresses, track market trends, and get insights from multiple data sources including Dune Analytics, Etherscan, CoinMarketCap, and DefiLlama.

### Key Features

- 🤖 **AI-Powered Research**: Gemini AI integration for intelligent blockchain analysis
- 📊 **Multi-Source Data**: Integration with Dune, Etherscan, CoinMarketCap, and DefiLlama
- 💬 **Conversational Interface**: Session-based chat with memory for context-aware responses
- 🎨 **Modern UI**: Anime-inspired design with glass morphism and gradient effects
- 🔗 **Web3 Integration**: RainbowKit wallet connection and Web3 functionality
- 📈 **Data Visualization**: Interactive charts and multiple data view modes
- 🚀 **Real-time Analytics**: Live API health monitoring and query execution

## 🏗️ Architecture

### Backend (`ai-agent/`)
The backend is a Flask-based research agent that leverages LangChain for AI orchestration:

- **Framework**: Flask with async support
- **AI Engine**: Google Gemini 2.0 Flash via LangChain
- **Memory**: Conversation session management with ChatMessageHistory
- **Tools**: Custom tools for blockchain data retrieval
- **APIs**: RESTful endpoints with CORS support

### Frontend (`client/`)
Modern Next.js application with anime-inspired UI:

- **Framework**: Next.js 15 with React 19
- **Styling**: Tailwind CSS 4
- **Web3**: RainbowKit + Wagmi for wallet connections
- **Visualization**: Recharts for data charts
- **UI Components**: Custom animated components with glass morphism

## 🚀 Quick Start

### Prerequisites

- Python 3.8+ (for backend)
- Node.js 18+ (for frontend)
- API keys for: Gemini AI, Dune Analytics, Etherscan, CoinMarketCap

### Backend Setup

1. **Navigate to backend directory**
   ```bash
   cd ai-agent
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file in the `ai-agent/` directory:
   ```env
   GEMINI_API_KEY=your_gemini_api_key
   DUNE_API_KEY=your_dune_api_key
   ETHERSCAN_API_KEY=your_etherscan_api_key
   COINMARKETCAP_API_KEY=your_coinmarketcap_api_key
   ALLOWED_ORIGINS=*
   FLASK_DEBUG=0
   ```

4. **Start the backend server**
   ```bash
   python app.py
   ```
   The API will be available at `http://localhost:8000`

### Frontend Setup

1. **Navigate to client directory**
   ```bash
   cd client
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Start development server**
   ```bash
   npm run dev
   ```
   The frontend will be available at `http://localhost:3000`

## 📚 API Documentation

### Backend Endpoints

#### Health Check
- **GET** `/api/health`
- Returns API status and health information

#### Research Query
- **POST** `/api/research`
- **Body**: 
  ```json
  {
    "query": "string (required)",
    "address": "string (optional)",
    "time_range": "string (default: 7d)",
    "session_id": "string (optional)"
  }
  ```
- **Response**: Research results with AI analysis and data

#### Conversation Management
- **GET** `/api/conversation/<session_id>` - Get chat history
- **GET** `/api/sessions` - List all active sessions

### Data Sources

#### Dune Analytics
- **Purpose**: Custom blockchain queries and analytics
- **Features**: SQL query execution, dashboard data
- **Rate Limits**: Based on Dune API plan

#### Etherscan
- **Purpose**: Ethereum blockchain data
- **Features**: Transaction history, token transfers, contract interactions
- **Rate Limits**: 5 calls/second (free tier)

#### CoinMarketCap
- **Purpose**: Cryptocurrency market data
- **Features**: Price data, market cap, trading volume
- **Rate Limits**: 333 calls/month (basic plan)

#### DefiLlama
- **Purpose**: DeFi protocol analytics
- **Features**: TVL data, protocol information, yield farming
- **Rate Limits**: Public API (no authentication required)

## 🛠️ Core Components

### Backend Components

#### `OptimizedWeb3ResearchAgent`
The main research agent class that:
- Manages conversation sessions with memory
- Orchestrates multi-source data collection
- Provides AI-powered analysis and insights
- Handles tool selection and execution

#### Data Tools
- **`dune_analytics_tool`**: Execute custom blockchain queries
- **`etherscan_tool`**: Get Ethereum blockchain data
- **`coinmarketcap_tool`**: Fetch cryptocurrency market data
- **`defillama_tool`**: Access DeFi ecosystem information

#### Session Management
- **`ConversationSessionManager`**: Handles chat persistence
- **Memory**: Context-aware conversation history
- **Cleanup**: Automatic session expiration and management

### Frontend Components

#### Core Pages
- **`app/page.tsx`**: Landing page with animated AI chat interface
- **`app/main-chat/page.tsx`**: Main research interface with advanced features

#### UI Components
- **`DataVisualization.tsx`**: Advanced data display with multiple view modes
- **`LoadingSpinner.tsx`**: Custom loading animations
- **`animated-ai-chat.tsx`**: Interactive chat interface
- **`aurora-background.tsx`**: Animated background effects

#### Web3 Integration
- **RainbowKit**: Wallet connection interface
- **Wagmi**: Web3 React hooks
- **Multi-wallet Support**: MetaMask, WalletConnect, Coinbase, and more

## 🎨 UI Features

### Design System
- **Glass Morphism**: Translucent cards with backdrop blur
- **Gradient Overlays**: Dynamic color transitions
- **Neon Accents**: Anime-inspired glow effects
- **Responsive Design**: Mobile-first approach

### Interactive Elements
- **Floating AI Assistant**: Context-aware chat interface
- **Smart Suggestions**: AI-powered query recommendations
- **Data Export**: JSON, CSV, and PDF download options
- **Keyboard Shortcuts**: Ctrl+Enter for quick queries

### Visualization Modes
- **Formatted View**: AI-structured research reports
- **Table Mode**: Tabular data display with sorting
- **Chart Mode**: Interactive data visualizations
- **JSON View**: Raw data inspection
- **Metrics Dashboard**: Key performance indicators

## 🚢 Deployment

### Production Deployment (Render)

The project includes Render deployment configuration:

#### Backend (`render.yaml`)
```yaml
services:
  - type: web
    name: airaa-backend
    env: python
    rootDir: ai-agent
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 180
    healthCheckPath: /api/health
```

#### Frontend
Deploy the `client/` directory to Vercel, Netlify, or similar platform.

### Environment Variables (Production)
Set these in your deployment platform:
- `GEMINI_API_KEY`
- `DUNE_API_KEY`
- `ETHERSCAN_API_KEY`
- `COINMARKETCAP_API_KEY`
- `ALLOWED_ORIGINS` (comma-separated frontend URLs)

### Local Development
```bash
# Terminal 1 - Backend
cd ai-agent
python app.py

# Terminal 2 - Frontend  
cd client
npm run dev
```

## 📊 Usage Examples

### Basic Research Query
```
"What is the current TVL of Uniswap V3?"
```

### Address Analysis
```
Query: "Analyze this wallet's DeFi activities"
Address: "0x742d35Cc6634C0532925a3b8D11000000000000"
Time Range: "30d"
```

### Market Analysis
```
"Compare the performance of ETH vs BTC over the last week"
```

### Protocol Deep Dive
```
"Provide a comprehensive analysis of Aave's lending metrics and recent governance proposals"
```

## 🔧 Development

### Backend Development
```bash
cd ai-agent
pip install -r requirements.txt
python app.py  # Starts Flask dev server
```

### Frontend Development
```bash
cd client
npm install
npm run dev  # Starts Next.js dev server with Turbopack
```

### Testing
```bash
# Backend tests
cd ai-agent/tests
python test_conversation_memory.py
python final_test.py

# Frontend testing
cd client
npm run lint
npm run build  # Test production build
```

## 📝 Configuration

### Backend Configuration (`ai-agent/`)
- **`requirements.txt`**: Python dependencies
- **`app.py`**: Flask application and API routes
- **`main.py`**: Core research agent logic and tools

### Frontend Configuration (`client/`)
- **`package.json`**: Node.js dependencies and scripts
- **`next.config.ts`**: Next.js configuration
- **`tailwind.config.js`**: Tailwind CSS configuration
- **`tsconfig.json`**: TypeScript configuration

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests if applicable
5. Commit your changes: `git commit -m 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Submit a pull request


## 🙏 Acknowledgments

- **LangChain**: For AI orchestration framework
- **Google Gemini**: For AI model capabilities
- **Next.js Team**: For the amazing React framework
- **RainbowKit**: For Web3 wallet integration
- **Recharts**: For data visualization components

---

Built with ❤️ for the Web3 community. **AIRAA** - Your intelligent blockchain research companion.
