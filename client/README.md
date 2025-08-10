# AIRAA Frontend Setup Guide

A modern, anime-inspired Web3 research interface with AI-powered blockchain analytics.

## 🎯 Overview

The AIRAA frontend is a Next.js 15 application featuring:
- **Modern UI**: Glass morphism design with animated backgrounds
- **Web3 Integration**: RainbowKit wallet connections supporting multiple chains
- **AI Chat Interface**: Conversational research with session persistence
- **Data Visualization**: Interactive charts, tables, and export capabilities
- **Real-time Analytics**: Live API monitoring and health checks

## 📋 Prerequisites

Before setting up the frontend, ensure you have:

- **Node.js**: Version 18 or higher
- **npm**: Version 8 or higher (comes with Node.js)
- **Backend API**: AIRAA backend running on `http://localhost:8000`
- **Modern Browser**: Chrome, Firefox, Safari, or Edge with Web3 support

## 🚀 Installation & Setup

### 1. Clone and Navigate
```bash
git clone <repository-url>
cd airaa/client
```

### 2. Install Dependencies
```bash
npm install
```

### 3. Verify Installation
Check that key dependencies are installed:
```bash
npm list --depth=0
```

Expected key packages:
- `next@15.4.6`
- `react@19.1.0`
- `@rainbow-me/rainbowkit@^2.2.8`
- `tailwindcss@^4`
- `typescript@^5`

### 4. Start Development Server
```bash
npm run dev
```

The application will be available at: `http://localhost:3000`

### 5. Backend Connection
Ensure the AIRAA backend is running on `http://localhost:8000`. See the backend SETUP.md for instructions.

## 🌐 Web3 Configuration

### Supported Chains
The frontend supports multiple blockchain networks:

- **Mainnet**: Ethereum mainnet
- **Sepolia**: Ethereum testnet
- **Polygon Mumbai**: Polygon testnet
- **Base Sepolia**: Base testnet
- **Avalanche Fuji**: Avalanche testnet

### Wallet Support
Compatible wallets through RainbowKit:
- **MetaMask**: Browser extension and mobile
- **WalletConnect**: Mobile wallet connections
- **Coinbase Wallet**: Smart wallet integration
- **Rainbow Wallet**: Native mobile experience
- **Core Wallet**: Multi-chain support
- **Ledger**: Hardware wallet security

### Adding New Chains
To add additional blockchain networks:

1. Edit `app/wagmi.ts`:
```typescript
import { newChain } from "wagmi/chains";

// Add to chains array
chains: [mainnet, sepolia, newChain]

// Add transport
transports: {
  [newChain.id]: http(),
}
```

2. Update providers in `app/providers.tsx` if needed

## 🎨 UI Components & Features

### Core Components

#### Landing Page (`app/page.tsx`)
- Animated AI chat interface
- Aurora background effects
- Initial query input with redirect to main chat

#### Main Chat Interface (`app/main-chat/page.tsx`)
- Research query input with advanced options
- Real-time API health monitoring
- Session-based conversation history
- Data visualization controls
- Export functionality (JSON, CSV, PDF)

#### Data Visualization (`app/components/DataVisualization.tsx`)
- **View Modes**:
  - Formatted: AI-structured reports
  - Table: Sortable data grids
  - Chart: Interactive visualizations
  - JSON: Raw data inspection
  - Metrics: KPI dashboards
  - AI Suggestions: Smart recommendations

#### UI Effects
- **Aurora Background**: Animated gradient effects
- **Wavy Background**: Particle animation system
- **Glass Morphism**: Translucent cards with backdrop blur
- **Loading Spinners**: Custom animated loading states

### Styling System

#### Tailwind CSS 4
- Custom design tokens
- Responsive utilities
- Animation classes
- Dark theme support

#### Font Configuration
- **Display**: Oxanium (headings)
- **Body**: Noto Sans JP (readable text)
- **Code**: JetBrains Mono (monospace)

## 🔧 Development Scripts

```bash
# Development
npm run dev          # Start with Turbopack (faster builds)
npm run build        # Production build
npm run start        # Serve production build
npm run lint         # ESLint checking

# Advanced Development
npm run dev -- --port 3001    # Custom port
npm run build -- --debug      # Debug build info
```

## 🛠️ Configuration Files

### Core Configuration

#### `next.config.ts`
```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    turboMode: true,
  },
};

export default nextConfig;
```

#### `tsconfig.json`
TypeScript configuration with Next.js optimizations and path mapping.

#### `tailwind.config.js`
Tailwind CSS configuration with:
- Custom color schemes
- Animation utilities
- Component classes
- Responsive breakpoints

### Package Management

#### Dependencies Overview
- **Framework**: Next.js 15 with React 19
- **Web3**: Wagmi 2.16 + RainbowKit 2.2.8
- **Styling**: Tailwind CSS 4
- **Charts**: Recharts 2.13
- **Animations**: Motion 12.23
- **PDF Export**: jsPDF + html2canvas
- **Excel Export**: XLSX
- **Icons**: Lucide React

## 🔍 API Integration

### Backend Endpoints

#### Health Check
```bash
GET http://localhost:8000/api/health
```

#### Research Query
```bash
POST http://localhost:8000/api/research
Content-Type: application/json

{
  "query": "What is the TVL of Uniswap V3?",
  "address": "0x...", // optional
  "time_range": "7d", // optional
  "session_id": "uuid" // optional
}
```

#### Session Management
```bash
GET http://localhost:8000/api/conversation/{session_id}
GET http://localhost:8000/api/sessions
```

### Error Handling
The frontend includes comprehensive error handling:
- API connection failures
- Rate limiting responses  
- Invalid query formats
- Network timeouts
- Session expiration

## 🎮 User Features

### Query Interface
- **Basic Mode**: Simple text input for research queries
- **Advanced Mode**: Address and time range filters
- **Quick Examples**: Pre-defined query templates
- **Session Persistence**: Conversation history across page reloads

### Data Export
- **JSON**: Raw API response data
- **CSV**: Tabular data export
- **PDF**: Report generation with charts
- **Excel**: Spreadsheet format

### Keyboard Shortcuts
- `Ctrl/Cmd + Enter`: Execute research query
- `Escape`: Close modals/dialogs
- `Tab`: Navigate form elements
- `Ctrl/Cmd + K`: Focus search input

### Responsive Design
- **Mobile**: Touch-optimized interface
- **Tablet**: Adapted layouts
- **Desktop**: Full feature set
- **Wide Screen**: Expanded data views

## 🚨 Troubleshooting

### Common Issues

#### 1. Build Errors
```bash
# Clear Next.js cache
rm -rf .next
npm run build

# Clear node_modules
rm -rf node_modules package-lock.json
npm install
```

#### 2. Web3 Connection Issues
- Ensure MetaMask is installed and unlocked
- Check network selection matches supported chains
- Verify WalletConnect project ID in providers

#### 3. API Connection Problems
```bash
# Check backend status
curl http://localhost:8000/api/health

# Verify CORS settings in backend
# Check browser console for CORS errors
```

#### 4. Styling Issues
```bash
# Rebuild Tailwind classes
npm run build

# Check for conflicting CSS
# Verify Tailwind config is valid
```

#### 5. TypeScript Errors
```bash
# Check type definitions
npm run lint

# Update type packages
npm update @types/react @types/node
```

### Development Tips

#### Hot Reload Issues
If hot reload stops working:
1. Restart the dev server
2. Clear browser cache
3. Check for syntax errors in components

#### Performance Optimization
- Use React DevTools Profiler
- Monitor bundle size with `npm run build`
- Optimize images and animations
- Implement proper memoization

## 📱 Browser Support

### Minimum Requirements
- **Chrome**: Version 91+
- **Firefox**: Version 89+
- **Safari**: Version 14+
- **Edge**: Version 91+

### Web3 Features
- MetaMask extension
- WalletConnect v2 support
- EIP-1193 provider
- Web3Modal compatibility

## 🚀 Production Deployment

### Build Optimization
```bash
npm run build
npm run start
```

### Environment Variables
No environment variables required for basic functionality.

### Deployment Platforms
- **Vercel**: Recommended (Next.js native)
- **Netlify**: Static site deployment
- **AWS S3**: Static hosting
- **Cloudflare Pages**: Edge optimization

### CDN Configuration
Optimize static assets:
- Enable compression
- Set proper cache headers
- Use image optimization
- Implement preloading

---

## 📞 Support

### Getting Help
- **Documentation**: Check inline code comments
- **Console Logs**: Browser developer tools
- **Network Tab**: API request debugging
- **React DevTools**: Component inspection

### Contributing
See the main README.md for contribution guidelines.

---

Built with ❤️ for the Web3 community using cutting-edge frontend technologies.