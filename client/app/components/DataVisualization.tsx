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

export type ChartType = 'line' | 'bar' | 'area' | 'pie';
export interface VisualizationConfig {
  mode: 'formatted' | 'table' | 'json' | 'chart' | 'metrics' | 'ai_suggestions';
  chartType?: ChartType;
  datasetPath?: string; // JSON path to the array used for charting
  xKey?: string;
  yKey?: string;
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



    return basicSuggestions;
  }, [data, localConfig]);













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