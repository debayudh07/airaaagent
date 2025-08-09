/* eslint-disable */
"use client";

import React, { useMemo, useState, useEffect, useRef } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import mermaid from 'mermaid';

export type ChartType = 'line' | 'bar' | 'area' | 'pie';
export interface VisualizationConfig {
  mode: 'formatted' | 'table' | 'json' | 'chart' | 'metrics' | 'mermaid' | 'ai_suggestions';
  chartType?: ChartType;
  datasetPath?: string; // JSON path to the array used for charting
  xKey?: string;
  yKey?: string;
  mermaidCode?: string; // Generated mermaid diagram code
}

interface AISuggestion {
  id: string;
  title: string;
  description: string;
  action: () => void;
  icon: string;
}

interface DataVisualizationProps {
  data: any;
  title: string;
  config?: VisualizationConfig; // optional controlled config
  onConfigChange?: (config: VisualizationConfig) => void; // emits when local config changes
}

export default function DataVisualization({ data, title, config, onConfigChange }: DataVisualizationProps) {
  const [localConfig, setLocalConfig] = useState<VisualizationConfig>({ mode: 'formatted' });
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [isGeneratingMermaid, setIsGeneratingMermaid] = useState(false);
  const [lastGeneratedCode, setLastGeneratedCode] = useState<string>('');
  const mermaidRef = useRef<HTMLDivElement>(null);

  // Initialize mermaid
  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      themeVariables: {
        primaryColor: '#22d3ee',
        primaryTextColor: '#ffffff',
        primaryBorderColor: '#0ea5e9',
        lineColor: '#64748b',
        sectionBkgColor: '#1e293b',
        altSectionBkgColor: '#334155',
        textColor: '#ffffff',
        taskBkgColor: '#1e293b',
        taskTextColor: '#ffffff',
        taskTextLightColor: '#94a3b8',
        taskTextOutsideColor: '#94a3b8',
        taskTextClickableColor: '#22d3ee',
        activeTaskBkgColor: '#0ea5e9',
        activeTaskBorderColor: '#0284c7',
        gridColor: '#475569',
        section0: '#1e293b',
        section1: '#334155',
        section2: '#475569',
        section3: '#64748b'
      }
    });
  }, []);

  // keep localConfig in sync with external config if provided
  useEffect(() => {
    if (config) setLocalConfig(config);
  }, [config]);

  const setConfig = (updater: VisualizationConfig | ((c: VisualizationConfig) => VisualizationConfig)) => {
    setLocalConfig(prev => {
      const next = typeof updater === 'function' ? (updater as (c: VisualizationConfig) => VisualizationConfig)(prev) : updater;
      onConfigChange?.(next);
      return next;
    });
  };

  // Generate AI suggestions based on data analysis using Gemini
  const generateAISuggestions = useMemo((): AISuggestion[] => {
    if (!data) return [];

    // Always include basic visualization options
    const basicSuggestions: AISuggestion[] = [
      {
        id: 'formatted_view',
        title: 'Smart Formatted View',
        description: 'AI-enhanced formatting with highlighted insights',
        icon: '📋',
        action: () => setConfig({ ...localConfig, mode: 'formatted' })
      },
      {
        id: 'table_view',
        title: 'Data Table',
        description: 'Structured table view of all data points',
        icon: '📊',
        action: () => setConfig({ ...localConfig, mode: 'table' })
      }
    ];

    // Check for array data for charts
    if (Array.isArray(data) || (typeof data === 'object' && Object.values(data).some(v => Array.isArray(v)))) {
      basicSuggestions.push({
        id: 'chart_analysis',
        title: 'Interactive Charts',
        description: 'Visualize trends and patterns with dynamic charts',
        icon: '📈',
        action: () => setConfig({ ...localConfig, mode: 'chart', chartType: 'line' })
      });

      basicSuggestions.push({
        id: 'metrics_dashboard',
        title: 'Metrics Dashboard',
        description: 'Key performance indicators and statistical summaries',
        icon: '🧮',
        action: () => setConfig({ ...localConfig, mode: 'metrics' })
      });
    }

    // AI-powered diagram suggestions based on data content
    const dataStr = JSON.stringify(data);
    
    // Suggest flowcharts for process-oriented data
    if (dataStr.toLowerCase().includes('transaction') || 
        dataStr.toLowerCase().includes('flow') || 
        dataStr.toLowerCase().includes('process') ||
        dataStr.toLowerCase().includes('step')) {
      basicSuggestions.push({
        id: 'ai_flowchart',
        title: 'AI Process Flowchart',
        description: 'Dynamic flowchart generated from your specific data patterns',
        icon: '🔄',
        action: () => generateMermaidDiagram('flowchart')
      });
    }

    // Suggest network diagrams for relationship data
    if (dataStr.toLowerCase().includes('protocol') || 
        dataStr.toLowerCase().includes('network') || 
        dataStr.toLowerCase().includes('connection') ||
        dataStr.toLowerCase().includes('relationship')) {
      basicSuggestions.push({
        id: 'ai_network',
        title: 'AI Network Diagram',
        description: 'Intelligent network visualization based on your data relationships',
        icon: '🌐',
        action: () => generateMermaidDiagram('graph')
      });
    }

    // Suggest mindmaps for hierarchical or concept data
    if (dataStr.toLowerCase().includes('defi') || 
        dataStr.toLowerCase().includes('ecosystem') || 
        dataStr.toLowerCase().includes('category') ||
        Object.keys(data).length > 3) {
      basicSuggestions.push({
        id: 'ai_mindmap',
        title: 'AI Concept Map',
        description: 'Intelligent mindmap organizing your data concepts and relationships',
        icon: '🧠',
        action: () => generateMermaidDiagram('mindmap')
      });
    }

    return basicSuggestions;
  }, [data, localConfig]);

  // Generate Mermaid diagram using Gemini AI based on actual data content
  const generateMermaidDiagram = async (diagramType: 'flowchart' | 'graph' | 'mindmap') => {
    setIsGeneratingMermaid(true);
    try {
      const mermaidCode = await generateAIMermaidDiagram(data, diagramType);
      setLastGeneratedCode(mermaidCode);
      setConfig({ ...localConfig, mode: 'mermaid', mermaidCode });
    } catch (error) {
      console.error('Error generating mermaid diagram:', error);
      // Fallback to basic diagram if AI generation fails
      const fallbackCode = generateFallbackDiagram(diagramType);
      setLastGeneratedCode(fallbackCode);
      setConfig({ ...localConfig, mode: 'mermaid', mermaidCode: fallbackCode });
    } finally {
      setIsGeneratingMermaid(false);
    }
  };

  // Generate AI-powered Mermaid diagram using Gemini
  const generateAIMermaidDiagram = async (dataContent: any, diagramType: 'flowchart' | 'graph' | 'mindmap'): Promise<string> => {
    const GEMINI_API_KEY = process.env.NEXT_PUBLIC_GEMINI_API_KEY;
    if (!GEMINI_API_KEY) {
      throw new Error('Gemini API key not found. Please set NEXT_PUBLIC_GEMINI_API_KEY in your environment.');
    }

    const dataStr = typeof dataContent === 'string' ? dataContent : JSON.stringify(dataContent, null, 2);
    
    let prompt = '';
    if (diagramType === 'flowchart') {
      prompt = `Analyze the following Web3/blockchain data and create a Mermaid flowchart. 

Data: ${dataStr}

Requirements:
- Start with exactly "flowchart TD"
- Use simple node names (A, B, C, etc.) with descriptive labels in brackets
- Include decision points with curly braces {} where appropriate
- Use arrow connections (-->)
- Keep labels concise and relevant to the data
- Generate ONLY valid Mermaid syntax, no explanatory text

Example format:
flowchart TD
    A[Start Process] --> B{Decision Point}
    B -->|Yes| C[Action 1]
    B -->|No| D[Action 2]`;

    } else if (diagramType === 'graph') {
      prompt = `Analyze the following Web3/blockchain data and create a Mermaid graph showing relationships.

Data: ${dataStr}

Requirements:
- Start with exactly "graph LR" or "graph TD"
- Use simple node identifiers (A, B, C, etc.) with labels in brackets
- Show connections with --> arrows
- Keep labels descriptive but concise
- Generate ONLY valid Mermaid syntax, no explanatory text

Example format:
graph LR
    A[Entity 1] --> B[Entity 2]
    B --> C[Entity 3]`;

    } else if (diagramType === 'mindmap') {
      prompt = `Analyze the following Web3/blockchain data and create a Mermaid mindmap.

Data: ${dataStr}

Requirements:
- Start with exactly "mindmap"
- Use proper indentation (2 spaces per level)
- Organize concepts hierarchically
- Keep branch names concise
- Generate ONLY valid Mermaid syntax, no explanatory text

Example format:
mindmap
  root)Main Topic(
    Branch 1
      Sub-item 1
      Sub-item 2
    Branch 2
      Sub-item 3`;
    }

    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        contents: [{
          parts: [{
            text: prompt
          }]
        }],
        generationConfig: {
          temperature: 0.3,
          topK: 20,
          topP: 0.8,
          maxOutputTokens: 1024,
        }
      }),
    });

    const responseData = await response.json();
    
    if (responseData.candidates && responseData.candidates[0] && responseData.candidates[0].content) {
      let mermaidCode = responseData.candidates[0].content.parts[0].text;
      
      // Clean up the response to extract only the Mermaid code
      mermaidCode = mermaidCode.replace(/```mermaid\n?/g, '').replace(/```\n?/g, '').trim();
      
      // Additional cleanup - remove any extra text before/after the diagram
      const lines = mermaidCode.split('\n');
      let startIndex = -1;
      let endIndex = lines.length;
      
      // Find the start of the actual diagram
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].trim().match(/^(flowchart|graph|mindmap)/)) {
          startIndex = i;
          break;
        }
      }
      
      if (startIndex === -1) {
        throw new Error('No valid Mermaid diagram found in AI response');
      }
      
      // Extract the diagram code
      const diagramLines = lines.slice(startIndex, endIndex);
      mermaidCode = diagramLines.join('\n').trim();
      
      // Basic validation
      if (!mermaidCode || mermaidCode.length < 10) {
        throw new Error('Generated diagram code is too short or empty');
      }
      
      // Validate syntax start
      if (!mermaidCode.match(/^(flowchart|graph|mindmap)/)) {
        throw new Error('Invalid Mermaid syntax - diagram must start with flowchart, graph, or mindmap');
      }
      
      return mermaidCode;
    } else {
      throw new Error('Invalid response from Gemini API');
    }
  };

  // Fallback diagram generator for when AI fails
  const generateFallbackDiagram = (diagramType: 'flowchart' | 'graph' | 'mindmap'): string => {
    if (diagramType === 'flowchart') {
      return `flowchart TD
    A[Data Input] --> B[Processing]
    B --> C{Valid Data?}
    C -->|Yes| D[Analysis]
    C -->|No| E[Error Handling]
    D --> F[Results]
    E --> A`;
    } else if (diagramType === 'graph') {
      return `graph LR
    A[Data Source] --> B[API Processing]
    B --> C[Blockchain Data]
    C --> D[Visualization]
    D --> E[User Interface]`;
    } else {
      return `mindmap
  root)Data Analysis(
    Input Sources
      API Data
      Blockchain
      User Queries
    Processing
      Validation
      Analysis
      Formatting
    Output
      Charts
      Tables
      Diagrams`;
    }
  };



  // Render mermaid diagram
  const renderMermaidDiagram = async (mermaidCode: string) => {
    if (!mermaidRef.current || !mermaidCode) return;

    try {
      const element = mermaidRef.current;
      
      // Clear previous content
      element.innerHTML = '';
      
      // Create a unique ID for this diagram
      const diagramId = `mermaid-${Date.now()}`;
      
      // Validate and clean the mermaid code
      const cleanCode = mermaidCode.trim();
      if (!cleanCode) {
        throw new Error('Empty diagram code');
      }
      
      // Generate the diagram using mermaid render method
      const { svg } = await mermaid.render(diagramId, cleanCode);
      element.innerHTML = svg;
      
    } catch (error) {
      console.error('Error rendering mermaid diagram:', error);
      if (mermaidRef.current) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
        mermaidRef.current.innerHTML = `
          <div class="text-red-400 p-4 border border-red-400/30 rounded-lg bg-red-900/10">
            <div class="font-semibold mb-2">❌ Diagram Rendering Error</div>
            <div class="text-sm">${errorMessage}</div>
            <div class="text-xs mt-2 text-red-300">Try generating a different diagram type or check the data content.</div>
          </div>
        `;
      }
    }
  };

  // Re-render mermaid when code changes
  useEffect(() => {
    if (localConfig.mode === 'mermaid' && localConfig.mermaidCode) {
      renderMermaidDiagram(localConfig.mermaidCode);
    }
  }, [localConfig.mode, localConfig.mermaidCode]);

  const viewMode = localConfig.mode ?? 'formatted';

  const renderFormattedData = (obj: any, depth = 0): React.JSX.Element => {
    if (typeof obj === 'string') {
      // Check if it's a markdown-like formatted research response
      if (obj.includes('**') || obj.includes('🔍') || obj.includes('📊')) {
        return (
          <div className="space-y-4">
            {obj.split('\n\n').map((section, index) => (
              <div key={index} className="bg-gray-800/30 rounded-lg p-4 border border-gray-600/30">
                <div 
                  className="text-gray-200 whitespace-pre-wrap"
                  dangerouslySetInnerHTML={{
                    __html: section
                      .replace(/\*\*(.*?)\*\*/g, '<strong class="text-cyan-400">$1</strong>')
                      .replace(/🔍/g, '<span class="text-2xl">🔍</span>')
                      .replace(/📊/g, '<span class="text-2xl">📊</span>')
                      .replace(/🌐/g, '<span class="text-2xl">🌐</span>')
                      .replace(/📈/g, '<span class="text-2xl">📈</span>')
                      .replace(/🎯/g, '<span class="text-2xl">🎯</span>')
                      .replace(/📋/g, '<span class="text-2xl">📋</span>')
                      .replace(/💡/g, '<span class="text-2xl">💡</span>')
                      .replace(/•/g, '<span class="text-cyan-400">•</span>')
                      .replace(/\$([\d,]+\.?\d*)/g, '<span class="text-green-400 font-bold">$$$1</span>')
                      .replace(/#(\d+)/g, '<span class="text-purple-400 font-bold">#$1</span>')
                      .replace(/(\d+\.?\d*)%/g, '<span class="text-yellow-400 font-bold">$1%</span>')
                  }}
                />
              </div>
            ))}
          </div>
        );
      }
      return <div className="text-gray-300 whitespace-pre-wrap">{obj}</div>;
    }

    if (typeof obj !== 'object' || obj === null) {
      return <span className="text-green-400">{JSON.stringify(obj)}</span>;
    }

    if (Array.isArray(obj)) {
      return (
        <div className="space-y-2">
          {obj.map((item, index) => (
            <div key={index} className="flex items-start space-x-2">
              <span className="text-cyan-400 font-bold">[{index}]</span>
              <div className="flex-1">{renderFormattedData(item, depth + 1)}</div>
            </div>
          ))}
        </div>
      );
    }

    return (
      <div className={`space-y-2 ${depth > 0 ? 'ml-4 border-l border-gray-600 pl-4' : ''}`}>
        {Object.entries(obj).map(([key, value]) => (
          <div key={key} className="flex flex-col space-y-1">
            <div className="flex items-center space-x-2">
              <span className="text-purple-400 font-semibold">{key}:</span>
              {typeof value === 'object' && value !== null ? null : (
                <span className="text-gray-300">{renderFormattedData(value, depth + 1)}</span>
              )}
            </div>
            {typeof value === 'object' && value !== null && (
              <div className="ml-4">{renderFormattedData(value, depth + 1)}</div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderTable = (obj: any): React.JSX.Element => {
    if (typeof obj === 'string') {
      // Try to extract tabular data from formatted text
      const lines = obj.split('\n').filter(line => line.trim());
      const tableData: string[][] = [];
      
      lines.forEach(line => {
        if (line.includes(':') && !line.includes('**')) {
          const [key, value] = line.split(':').map(s => s.trim());
          if (key && value) {
            tableData.push([key.replace(/•\s*/, ''), value]);
          }
        }
      });

      if (tableData.length > 0) {
        return (
          <div className="overflow-x-auto">
            <table className="w-full bg-gray-900/50 rounded-lg overflow-hidden">
              <thead>
                <tr className="bg-gray-800/50">
                  <th className="px-4 py-3 text-left text-cyan-400 font-semibold">Metric</th>
                  <th className="px-4 py-3 text-left text-cyan-400 font-semibold">Value</th>
                </tr>
              </thead>
              <tbody>
                {tableData.map(([key, value], index) => (
                  <tr key={index} className={`border-t border-gray-700 ${index % 2 === 0 ? 'bg-gray-800/20' : ''}`}>
                    <td className="px-4 py-3 text-purple-300 font-medium">{key}</td>
                    <td className="px-4 py-3 text-gray-300">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
    }

    const flatData = flattenForTable(obj);
    const entries = Object.entries(flatData);

    if (entries.length === 0) {
      return <div className="text-gray-400">No tabular data available</div>;
    }

    return (
      <div className="overflow-x-auto">
        <table className="w-full bg-gray-900/50 rounded-lg overflow-hidden">
          <thead>
            <tr className="bg-gray-800/50">
              <th className="px-4 py-3 text-left text-cyan-400 font-semibold">Property</th>
              <th className="px-4 py-3 text-left text-cyan-400 font-semibold">Value</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, value], index) => (
              <tr key={index} className={`border-t border-gray-700 ${index % 2 === 0 ? 'bg-gray-800/20' : ''}`}>
                <td className="px-4 py-3 text-purple-300 font-medium">{key}</td>
                <td className="px-4 py-3 text-gray-300 break-all">{String(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const flattenForTable = (obj: any, prefix = ''): Record<string, any> => {
    let flattened: Record<string, any> = {};
    
    for (const key in obj) {
      if (obj.hasOwnProperty(key)) {
        const newKey = prefix ? `${prefix}.${key}` : key;
        
        if (typeof obj[key] === 'object' && obj[key] !== null && !Array.isArray(obj[key])) {
          Object.assign(flattened, flattenForTable(obj[key], newKey));
        } else {
          flattened[newKey] = obj[key];
        }
      }
    }
    
    return flattened;
  };

  // --- Chart + Metrics helpers
  const arrayCandidates = useMemo(() => {
    const results: { path: string; items: any[] }[] = [];
    const visit = (node: any, path: string) => {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) {
        if (node.length > 0 && typeof node[0] === 'object') {
          results.push({ path, items: node });
        }
        return; // don't dive into arrays of primitives
      }
      for (const [k, v] of Object.entries(node)) visit(v, path ? `${path}.${k}` : k);
    };
    visit(data, '');
    return results;
  }, [data]);

  const selectedArray = useMemo(() => {
    const chosenPath = localConfig.datasetPath ?? arrayCandidates[0]?.path ?? '';
    const found = arrayCandidates.find(a => a.path === chosenPath) ?? arrayCandidates[0];
    return found?.items ?? [];
  }, [arrayCandidates, localConfig.datasetPath]);

  const candidateKeys = useMemo(() => {
    const first = selectedArray?.[0] ?? {};
    const keys = Object.keys(first);
    const numericKeys = keys.filter(k => typeof first[k] === 'number');
    const timeKeys = keys.filter(k => {
      const val = first[k];
      if (typeof val === 'number') return /time|timestamp|block/i.test(k);
      if (typeof val === 'string') return /time|date|timestamp/i.test(k) || !isNaN(Date.parse(val));
      return false;
    });
    return { all: keys, numeric: numericKeys, time: timeKeys };
  }, [selectedArray]);

  const effectiveChartType: ChartType = localConfig.chartType ?? 'line';
  const effectiveXKey: string | undefined = localConfig.xKey ?? (candidateKeys.time[0] ?? candidateKeys.all[0]);
  const effectiveYKey: string | undefined = localConfig.yKey ?? (candidateKeys.numeric[0] ?? candidateKeys.all.find(k => typeof selectedArray?.[0]?.[k] === 'number'));

  const computedStats = useMemo(() => {
    if (!effectiveYKey || !Array.isArray(selectedArray)) return null;
    const values = selectedArray.map((d: any) => Number(d?.[effectiveYKey])).filter(v => !Number.isNaN(v));
    if (!values.length) return null;
    const sum = values.reduce((a, b) => a + b, 0);
    const avg = sum / values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { count: values.length, sum, avg, min, max };
  }, [selectedArray, effectiveYKey]);

  const colorPalette = ['#22d3ee', '#a78bfa', '#f472b6', '#34d399', '#f59e0b'];

  const ChartControls = () => (
    <div className="flex flex-wrap items-center gap-2">
      <select
        value={localConfig.datasetPath ?? arrayCandidates[0]?.path ?? ''}
        onChange={(e) => setConfig({ ...localConfig, mode: 'chart', datasetPath: e.target.value })}
        className="bg-gray-800/70 border border-gray-700 text-gray-200 rounded-lg px-2 py-1 text-sm"
      >
        {arrayCandidates.map((a, idx) => (
          <option key={idx} value={a.path} className="bg-black">{a.path || 'root'}</option>
        ))}
      </select>
      <select
        value={effectiveXKey ?? ''}
        onChange={(e) => setConfig({ ...localConfig, mode: 'chart', xKey: e.target.value })}
        className="bg-gray-800/70 border border-gray-700 text-gray-200 rounded-lg px-2 py-1 text-sm"
      >
        {candidateKeys.all.map(k => <option key={k} value={k} className="bg-black">X: {k}</option>)}
      </select>
      <select
        value={effectiveYKey ?? ''}
        onChange={(e) => setConfig({ ...localConfig, mode: 'chart', yKey: e.target.value })}
        className="bg-gray-800/70 border border-gray-700 text-gray-200 rounded-lg px-2 py-1 text-sm"
      >
        {candidateKeys.all.map(k => <option key={k} value={k} className="bg-black">Y: {k}</option>)}
      </select>
      <div className="flex items-center gap-1 ml-2">
        {(['line','bar','area','pie'] as ChartType[]).map(type => (
          <button
            key={type}
            onClick={() => setConfig({ ...localConfig, mode: 'chart', chartType: type })}
            className={`px-2.5 py-1.5 rounded-md text-xs border ${effectiveChartType === type ? 'border-cyan-500/50 bg-cyan-600/30 text-cyan-200' : 'border-gray-600/50 bg-gray-700/40 text-gray-300'}`}
          >
            {type.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
  );

  const renderChart = (): React.JSX.Element => {
    if (!selectedArray?.length || !effectiveXKey || !effectiveYKey) {
      return <div className="text-gray-400">No chartable dataset detected.</div>;
    }
    const chartData = selectedArray.map((d: any) => ({ ...d, [effectiveXKey]: d[effectiveXKey], [effectiveYKey]: Number(d[effectiveYKey]) }));

    if (effectiveChartType === 'pie') {
      return (
        <ResponsiveContainer width="100%" height={320}>
          <PieChart>
            <Pie dataKey={effectiveYKey} nameKey={effectiveXKey} data={chartData} outerRadius={120}>
              {chartData.slice(0, colorPalette.length).map((_, idx) => (
                <Cell key={`cell-${idx}`} fill={colorPalette[idx % colorPalette.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      );
    }

    const CommonAxes = (
      <>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey={effectiveXKey} tick={{ fill: '#94a3b8', fontSize: 12 }} />
        <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
        <Tooltip />
        <Legend />
      </>
    );

    if (effectiveChartType === 'bar') {
      return (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData}>
            {CommonAxes}
            <Bar dataKey={effectiveYKey} fill={colorPalette[0]} />
          </BarChart>
        </ResponsiveContainer>
      );
    }

    if (effectiveChartType === 'area') {
      return (
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={chartData}>
            {CommonAxes}
            <Area type="monotone" dataKey={effectiveYKey} stroke={colorPalette[0]} fill={colorPalette[0]} fillOpacity={0.25} />
          </AreaChart>
        </ResponsiveContainer>
      );
    }

    // default line
    return (
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          {CommonAxes}
          <Line type="monotone" dataKey={effectiveYKey} stroke={colorPalette[0]} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    );
  };

  const renderMetrics = (): React.JSX.Element => {
    if (!computedStats) return <div className="text-gray-400">No numeric series detected to compute metrics.</div>;
    const { count, sum, avg, min, max } = computedStats;
    const Card = ({ label, value }: { label: string; value: number }) => (
      <div className="rounded-xl border border-white/15 bg-white/5 p-4">
        <div className="text-xs text-white/60">{label}</div>
        <div className="text-lg font-semibold text-white mt-1">{Number(value).toLocaleString()}</div>
      </div>
    );
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Card label="Count" value={count} />
          <Card label="Sum" value={sum} />
          <Card label="Average" value={avg} />
          <Card label="Min" value={min} />
          <Card label="Max" value={max} />
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setConfig({ ...localConfig, mode: 'formatted' })}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'formatted'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          📋 Formatted
        </button>
        <button
          onClick={() => setConfig({ ...localConfig, mode: 'table' })}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'table'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          📊 Table
        </button>
        <button
          onClick={() => setConfig({ ...localConfig, mode: 'chart' })}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'chart'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          📈 Chart
        </button>
        <button
          onClick={() => setConfig({ ...localConfig, mode: 'metrics' })}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'metrics'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          🧮 Metrics
        </button>
        <button
          onClick={() => setConfig({ ...localConfig, mode: 'mermaid' })}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'mermaid'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
          disabled={isGeneratingMermaid}
        >
          🧩 Diagram
        </button>
        <button
          onClick={() => setConfig({ ...localConfig, mode: 'ai_suggestions' })}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'ai_suggestions'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          🤖 AI Suggestions
        </button>
        <button
          onClick={() => setConfig({ ...localConfig, mode: 'json' })}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'json'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          🔧 JSON
        </button>
        {viewMode === 'chart' && arrayCandidates.length > 0 && (
          <div className="ml-auto">
            <ChartControls />
          </div>
        )}
      </div>

      <div className="bg-gray-900/50 rounded-xl p-6 border border-gray-700/50 max-h-[28rem] overflow-auto">
        {viewMode === 'formatted' && renderFormattedData(data)}
        {viewMode === 'table' && renderTable(data)}
        {viewMode === 'json' && (
          <pre className="text-sm text-gray-300 whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre>
        )}
        {viewMode === 'chart' && (
          <div className="space-y-4">
            {computedStats && (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="rounded-xl border border-white/15 bg-white/5 p-3 text-center">
                  <div className="text-[11px] text-white/60">Count</div>
                  <div className="text-base font-semibold">{computedStats.count.toLocaleString()}</div>
                </div>
                <div className="rounded-xl border border-white/15 bg-white/5 p-3 text-center">
                  <div className="text-[11px] text-white/60">Sum</div>
                  <div className="text-base font-semibold">{Math.round(computedStats.sum * 100) / 100}</div>
                </div>
                <div className="rounded-xl border border-white/15 bg-white/5 p-3 text-center">
                  <div className="text-[11px] text-white/60">Average</div>
                  <div className="text-base font-semibold">{Math.round(computedStats.avg * 100) / 100}</div>
                </div>
                <div className="rounded-xl border border-white/15 bg-white/5 p-3 text-center">
                  <div className="text-[11px] text-white/60">Min</div>
                  <div className="text-base font-semibold">{computedStats.min}</div>
                </div>
                <div className="rounded-xl border border-white/15 bg-white/5 p-3 text-center">
                  <div className="text-[11px] text-white/60">Max</div>
                  <div className="text-base font-semibold">{computedStats.max}</div>
                </div>
              </div>
            )}
            {renderChart()}
          </div>
        )}
        {viewMode === 'metrics' && renderMetrics()}
        {viewMode === 'mermaid' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Interactive Diagram</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => generateMermaidDiagram('flowchart')}
                  className="px-3 py-1.5 bg-blue-600/30 hover:bg-blue-600/50 rounded-lg text-sm border border-blue-500/50 text-blue-300"
                  disabled={isGeneratingMermaid}
                >
                  🔄 Flowchart
                </button>
                <button
                  onClick={() => generateMermaidDiagram('graph')}
                  className="px-3 py-1.5 bg-green-600/30 hover:bg-green-600/50 rounded-lg text-sm border border-green-500/50 text-green-300"
                  disabled={isGeneratingMermaid}
                >
                  🌐 Network
                </button>
                <button
                  onClick={() => generateMermaidDiagram('mindmap')}
                  className="px-3 py-1.5 bg-purple-600/30 hover:bg-purple-600/50 rounded-lg text-sm border border-purple-500/50 text-purple-300"
                  disabled={isGeneratingMermaid}
                >
                  🧠 Mindmap
                </button>
              </div>
            </div>
            {isGeneratingMermaid ? (
              <div className="flex items-center justify-center py-8">
                <div className="w-6 h-6 border-2 border-white/20 border-t-white rounded-full animate-spin mr-3"></div>
                <span className="text-white/70">AI is analyzing your data and generating a custom diagram...</span>
              </div>
            ) : localConfig.mermaidCode ? (
              <div className="space-y-3">
                <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-600/30">
                  <div 
                    ref={mermaidRef} 
                    className="mermaid-diagram"
                    style={{ 
                      display: 'flex', 
                      justifyContent: 'center', 
                      background: 'transparent',
                      color: '#ffffff'
                    }}
                  >
                    {localConfig.mermaidCode}
                  </div>
                </div>
                <div className="text-xs text-gray-500 text-center">
                  ✨ This diagram was generated by AI based on your specific data content
                </div>
                {lastGeneratedCode && (
                  <details className="mt-3">
                    <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
                      🔍 View Generated Code
                    </summary>
                    <pre className="text-xs text-gray-400 mt-2 p-2 bg-gray-800/50 rounded border border-gray-600/30 overflow-x-auto">
                      {lastGeneratedCode}
                    </pre>
                  </details>
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-gray-400">
                <p className="mb-2">🤖 Ready to generate AI-powered diagrams</p>
                <p className="text-sm">Click one of the buttons above to create a custom diagram based on your data</p>
                {!process.env.NEXT_PUBLIC_GEMINI_API_KEY && (
                  <p className="text-xs text-yellow-400 mt-3">
                    ⚠️ Gemini API key not configured. Fallback diagrams will be used.
                  </p>
                )}
              </div>
            )}
          </div>
        )}
        {viewMode === 'ai_suggestions' && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xl">🤖</span>
              <h3 className="text-lg font-semibold text-white">Smart Visualization Recommendations</h3>
              <div className="ml-auto">
                <span className="px-2 py-1 bg-green-600/20 text-green-400 text-xs rounded-full border border-green-500/30">
                  ✨ AI-Powered
                </span>
              </div>
            </div>
            <p className="text-gray-400 text-sm mb-6">
              Our AI has analyzed your specific data content and suggests these optimal visualization approaches:
            </p>
            <div className="grid gap-3">
              {generateAISuggestions.map((suggestion) => (
                <div
                  key={suggestion.id}
                  className="group rounded-xl border border-gray-600/50 bg-gray-800/30 hover:bg-gray-700/40 hover:border-cyan-500/50 transition-all duration-300 p-4 cursor-pointer"
                  onClick={suggestion.action}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl flex-shrink-0">{suggestion.icon}</span>
                    <div className="flex-1">
                      <h4 className="font-semibold text-white group-hover:text-cyan-300 transition-colors">
                        {suggestion.title}
                      </h4>
                      <p className="text-gray-400 text-sm mt-1">{suggestion.description}</p>
                      {suggestion.id.startsWith('ai_') && (
                        <div className="flex items-center gap-1 mt-2">
                          <span className="text-xs text-purple-400">🔮 AI-Generated</span>
                          <span className="text-xs text-gray-500">• Custom for your data</span>
                        </div>
                      )}
                    </div>
                    <div className="text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity">
                      →
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {generateAISuggestions.length === 0 && (
              <div className="text-center py-8 text-gray-400">
                <p className="mb-2">🤔 No specific suggestions available</p>
                <p className="text-sm">Try the other visualization modes to explore your data</p>
              </div>
            )}
            <div className="text-xs text-gray-500 text-center mt-4 pt-4 border-t border-gray-700/50">
              💡 Suggestions are dynamically generated based on your query results and data structure
            </div>
          </div>
        )}
      </div>
    </div>
  );
}