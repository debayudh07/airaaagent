# AIRAA Backend Setup Guide

AI-powered Web3 research agent with multi-source blockchain data integration.

## 🎯 Overview

The AIRAA backend is a Flask-based research agent that leverages LangChain for AI orchestration and provides:
- **AI Research Engine**: Google Gemini 2.0 Flash integration for intelligent blockchain analysis
- **Multi-Source Data**: Dune Analytics, Etherscan, CoinMarketCap, and DefiLlama APIs
- **Session Management**: Persistent conversation memory with chat history
- **Tool Orchestration**: Custom LangChain tools for blockchain data retrieval
- **RESTful API**: CORS-enabled endpoints for frontend integration

## 📋 Prerequisites

Before setting up the backend, ensure you have:

- **Python**: Version 3.8 or higher
- **pip**: Latest version (comes with Python)
- **API Keys**: For Gemini AI, Dune Analytics, Etherscan, CoinMarketCap
- **Internet Connection**: For API calls and model inference

### Required API Keys

1. **Google Gemini AI** (`GEMINI_API_KEY`)
   - Get from: [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Used for: AI research analysis and conversation

2. **Dune Analytics** (`DUNE_API_KEY`)
   - Get from: [Dune Analytics](https://dune.com/settings/api)
   - Used for: Custom blockchain queries and analytics

3. **Etherscan** (`ETHERSCAN_API_KEY`)
   - Get from: [Etherscan API](https://etherscan.io/apis)
   - Used for: Ethereum blockchain data

4. **CoinMarketCap** (`COINMARKETCAP_API_KEY`)
   - Get from: [CoinMarketCap API](https://pro.coinmarketcap.com/api/)
   - Used for: Cryptocurrency market data

## 🚀 Installation & Setup

### 1. Clone and Navigate
```bash
git clone <repository-url>
cd airaa/ai-agent
```

### 2. Create Virtual Environment (Recommended)
```bash
# Create virtual environment
python -m venv airaa-env

# Activate virtual environment
# On Windows:
airaa-env\Scripts\activate
# On macOS/Linux:
source airaa-env/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the `ai-agent/` directory:

```env
# AI Configuration
GEMINI_API_KEY=your_gemini_api_key_here

# Blockchain Data APIs
DUNE_API_KEY=your_dune_api_key_here
ETHERSCAN_API_KEY=your_etherscan_api_key_here
COINMARKETCAP_API_KEY=your_coinmarketcap_api_key_here

# Server Configuration
ALLOWED_ORIGINS=*
FLASK_DEBUG=0
PORT=8000
```

### 5. Verify Installation
Test the installation:
```bash
python -c "import httpx, flask, langchain; print('Dependencies installed successfully')"
```

### 6. Start the Server
```bash
python app.py
```

The API will be available at: `http://localhost:8000`

### 7. Test the API
```bash
# Health check
curl http://localhost:8000/api/health

# Expected response: {"status": "ok"}
```

## 🏗️ Architecture Overview

### Core Components

#### 1. Flask Application (`app.py`)
- **CORS Configuration**: Handles cross-origin requests from frontend
- **Route Handlers**: API endpoints for research and session management
- **Error Handling**: Comprehensive exception management
- **Async Support**: Asyncio integration for concurrent operations

#### 2. Research Agent (`main.py`)
- **OptimizedWeb3ResearchAgent**: Main agent class
- **Session Management**: Conversation persistence and memory
- **Tool Integration**: Custom LangChain tools for data sources
- **AI Orchestration**: Gemini AI integration via LangChain

#### 3. Data Tools
- **Dune Analytics Tool**: SQL query execution and dashboard data
- **Etherscan Tool**: Ethereum blockchain data retrieval
- **CoinMarketCap Tool**: Cryptocurrency market information
- **DefiLlama Tool**: DeFi protocol analytics

### Request Flow
```
Frontend Request → Flask App → Research Agent → AI + Tools → Response
```

## 🛠️ API Endpoints

### Health Check
```http
GET /api/health
```
**Response:**
```json
{
  "status": "ok"
}
```

### Research Query
```http
POST /api/research
Content-Type: application/json
```

**Request Body:**
```json
{
  "query": "What is the current TVL of Uniswap V3?",
  "address": "0x1234...", // optional
  "time_range": "7d", // optional: 1d, 7d, 30d, 90d
  "session_id": "uuid" // optional for conversation continuity
}
```

**Response:**
```json
{
  "success": true,
  "result": "AI-formatted research report",
  "data": {
    "merged_data": "Structured data from APIs",
    "reasoning_steps": ["Step 1", "Step 2"],
    "data_sources_used": ["dune", "etherscan"],
    "execution_time": 2.5
  },
  "session_id": "uuid",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Session Management

#### Get Conversation History
```http
GET /api/conversation/{session_id}
```

#### List Active Sessions
```http
GET /api/sessions
```

## 🔧 Configuration & Customization

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GEMINI_API_KEY` | Google AI API key | - | Yes |
| `DUNE_API_KEY` | Dune Analytics API key | - | Yes |
| `ETHERSCAN_API_KEY` | Etherscan API key | - | Yes |
| `COINMARKETCAP_API_KEY` | CoinMarketCap API key | - | Yes |
| `ALLOWED_ORIGINS` | CORS allowed origins | `*` | No |
| `FLASK_DEBUG` | Flask debug mode | `0` | No |
| `PORT` | Server port | `8000` | No |

### Tool Configuration

#### Adding New Data Sources
To add a new blockchain data source:

1. **Create a new tool** in `main.py`:
```python
@tool
async def new_api_tool(query: str) -> Dict[str, Any]:
    """
    Description of the new API tool.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com/data?query={query}")
        return {"source": "new_api", "data": response.json()}
```

2. **Add to tool list** in the agent:
```python
tools = [
    dune_analytics_tool,
    etherscan_tool,
    coinmarketcap_tool,
    defillama_tool,
    new_api_tool  # Add your new tool
]
```

#### Customizing AI Behavior
Modify the system prompts in `main.py`:
```python
SYSTEM_PROMPT = """
You are AIRAA, an advanced Web3 research agent...
[Customize the AI behavior here]
"""
```

### Session Configuration
Modify session settings in `ConversationSessionManager`:
```python
# Session timeout (default: 24 hours)
session_timeout_hours = 24

# Maximum sessions (default: 100)
max_sessions = 100
```

## 🧪 Testing

### Unit Tests
Run the test suite:
```bash
cd tests
python test_conversation_memory.py
python final_test.py
```

### Manual Testing

#### Test Research Endpoint
```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the current price of ETH?",
    "time_range": "7d"
  }'
```

#### Test Session Management
```bash
# Create a session
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello", "session_id": "test-session"}'

# Get session history
curl http://localhost:8000/api/conversation/test-session
```

### Load Testing
For production readiness:
```bash
# Install ab (Apache Bench)
# Test concurrent requests
ab -n 100 -c 10 http://localhost:8000/api/health
```

## 🔍 Data Sources Integration

### Dune Analytics
- **Purpose**: Custom blockchain queries and analytics dashboards
- **Rate Limits**: Based on your Dune plan (Pro: 1000 requests/month)
- **Features**: SQL query execution, pre-built dashboards
- **Documentation**: [Dune API Docs](https://docs.dune.com/api-reference/)

### Etherscan
- **Purpose**: Ethereum blockchain data and smart contract interactions
- **Rate Limits**: 5 calls/second (free), 20 calls/second (pro)
- **Features**: Transaction history, token transfers, contract data
- **Documentation**: [Etherscan API Docs](https://docs.etherscan.io/)

### CoinMarketCap
- **Purpose**: Cryptocurrency market data and rankings
- **Rate Limits**: 333 calls/month (basic), 10,000/month (standard)
- **Features**: Price data, market cap, trading volume, metadata
- **Documentation**: [CMC API Docs](https://coinmarketcap.com/api/documentation/)

### DefiLlama
- **Purpose**: DeFi protocol analytics and TVL data
- **Rate Limits**: No authentication required, generous limits
- **Features**: Protocol TVL, yield farming data, DeFi metrics
- **Documentation**: [DefiLlama API Docs](https://defillama.com/docs/api)

## 🚨 Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# Verify Python version
python --version

# Reinstall dependencies
pip install -r requirements.txt --upgrade
```

#### 2. API Key Issues
```bash
# Check environment variables
python -c "import os; print(os.getenv('GEMINI_API_KEY'))"

# Verify .env file is in ai-agent/ directory
ls -la .env
```

#### 3. Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Use different port
PORT=8001 python app.py
```

#### 4. CORS Issues
If frontend can't connect:
1. Check `ALLOWED_ORIGINS` environment variable
2. Verify frontend URL is included
3. Check browser console for CORS errors

#### 5. Memory Issues
For large datasets:
```python
# Adjust session limits in main.py
session_manager = ConversationSessionManager(
    max_sessions=50,  # Reduce from 100
    session_timeout_hours=12  # Reduce from 24
)
```

### Debug Mode
Enable detailed logging:
```env
FLASK_DEBUG=1
```

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Performance Monitoring
Monitor API performance:
```bash
# Log response times
tail -f app.log

# Monitor memory usage
pip install psutil
python -c "import psutil; print(f'Memory: {psutil.virtual_memory().percent}%')"
```

## 🚀 Production Deployment

### Gunicorn Configuration
The app includes production-ready Gunicorn configuration:

```bash
gunicorn app:app \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --threads 2 \
  --timeout 180 \
  --access-logfile - \
  --error-logfile -
```

### Environment Security
For production:

1. **Secure API Keys**:
   - Use environment variables, not `.env` files
   - Rotate keys regularly
   - Monitor API usage

2. **CORS Configuration**:
   ```env
   ALLOWED_ORIGINS=https://your-frontend-domain.com,https://your-staging-domain.com
   ```

3. **Rate Limiting**:
   Consider implementing rate limiting for production use.

### Deployment Platforms

#### Render (Recommended)
The project includes `render.yaml` configuration:
- Automatic deployment from git
- Environment variable management
- Built-in monitoring

#### Docker Deployment
Create `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
```

#### Traditional VPS
1. Set up Python 3.8+ environment
2. Install dependencies with `pip`
3. Configure reverse proxy (nginx)
4. Set up process manager (systemd, supervisor)

## 📊 Monitoring & Maintenance

### Health Monitoring
Implement health checks:
```bash
# Check API health
curl http://localhost:8000/api/health

# Monitor logs
tail -f /var/log/airaa/app.log
```

### Performance Metrics
Track key metrics:
- API response times
- Error rates
- Memory usage
- Session count
- API quota usage

### Maintenance Tasks

#### Daily
- Monitor API quota usage
- Check error logs
- Verify all services are running

#### Weekly
- Review session cleanup
- Update dependencies if needed
- Check API key rotation schedule

#### Monthly
- Analyze usage patterns
- Update AI model versions
- Security audit

## 🔒 Security Considerations

### API Security
- **Environment Variables**: Never commit API keys to version control
- **HTTPS**: Use HTTPS in production
- **Rate Limiting**: Implement request rate limiting
- **Input Validation**: Sanitize all user inputs

### Data Privacy
- **Session Data**: Automatically expires after 24 hours
- **Logging**: Avoid logging sensitive information
- **API Responses**: Filter sensitive data before returning

### Dependencies
Keep dependencies updated:
```bash
pip list --outdated
pip install -r requirements.txt --upgrade
```

## 📞 Support & Development

### Development Mode
For active development:
```bash
export FLASK_DEBUG=1
python app.py
```

### Code Structure
```
ai-agent/
├── app.py              # Flask application and routes
├── main.py             # Research agent and tools
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (not in git)
├── tests/             # Test suite
│   ├── test_conversation_memory.py
│   └── final_test.py
└── api-docs/          # API documentation
    └── defillama-api.json
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

### Getting Help
- **Logs**: Check application logs for detailed error information
- **Documentation**: Review inline code comments
- **API Testing**: Use tools like Postman or curl for debugging
- **Community**: Check the main README for support channels

---

Built with ❤️ for the Web3 community using enterprise-grade Python technologies.
