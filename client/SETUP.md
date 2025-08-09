# AIRAA Research Agent Frontend

A sleek, retro-style Web3 research interface with AI-powered assistance.

## Features

🚀 **Modern Retro UI**
- 3D glass morphism cards
- Animated background grid
- Gradient overlays and neon accents
- Smooth transitions and hover effects

🧠 **AI-Powered Research**
- Integration with Web3 research agent backend
- Real-time API health monitoring
- Smart query suggestions
- Gemini AI assistant integration

📊 **Advanced Data Visualization**
- Multiple view modes (Formatted, Table, JSON)
- Interactive data tables
- Download capabilities (JSON, CSV)
- Syntax highlighting for research reports

🎨 **Enhanced UX**
- Responsive design
- Loading animations
- Error handling with retries
- Keyboard shortcuts (Ctrl+Enter to search)

## Quick Start

1. **Install Dependencies**
   ```bash
   cd frontend/client
   npm install
   ```

2. **Start Development Server**
   ```bash
   npm run dev
   ```

3. **Start Backend API** (In separate terminal)
   ```bash
   cd ../../ai-agent
   python app.py
   ```

4. **Open Browser**
   Navigate to `http://localhost:3000`

## Environment Configuration

Make sure your backend API is running on `http://localhost:8000` with the following endpoints:
- `GET /api/health` - API health check
- `POST /api/research` - Research query endpoint

## Usage

1. **Basic Research**: Enter any Web3-related query in the main text area
2. **Advanced Options**: Click to expand wallet address and time range filters
3. **Quick Examples**: Use predefined example queries for common research tasks
4. **AI Assistant**: Click the floating AI button for intelligent assistance
5. **Export Data**: Download research results in JSON or CSV format

## Gemini AI Integration

The integrated AI assistant uses Google's Gemini 2.0 Flash model to provide:
- Smart query suggestions based on research data
- Natural language explanations of complex data
- Interactive chat interface
- Context-aware responses

## API Endpoints Used

- **Backend Research API**: `http://localhost:8000/api/research`
- **Gemini AI API**: Google's Generative Language API
- **Health Check**: `http://localhost:8000/api/health`

## Tech Stack

- **Framework**: Next.js 15 with React 19
- **Styling**: Tailwind CSS 4
- **Language**: TypeScript
- **AI Integration**: Google Gemini 2.0 Flash
- **Build Tool**: Turbopack (Next.js native)

## Components

- `page.tsx` - Main research interface
- `DataVisualization.tsx` - Advanced data display with multiple view modes
- `GeminiAIAssistant.tsx` - Floating AI chat assistant
- `LoadingSpinner.tsx` - Custom loading animations

## Keyboard Shortcuts

- `Ctrl/Cmd + Enter` - Execute research query
- `Escape` - Close AI assistant
- `Tab` - Navigate between form elements

## Troubleshooting

1. **API Connection Issues**: Ensure backend is running on port 8000
2. **Gemini AI Errors**: Check API key and rate limits
3. **Styling Issues**: Ensure Tailwind CSS is properly configured
4. **Build Errors**: Check TypeScript types and imports

## Development

For development, use:
```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run start        # Start production server
npm run lint         # Run ESLint
```

---

Built with ❤️ for the Web3 community