'use client';

import { useState } from 'react';

interface DataVisualizationProps {
  data: any;
  title: string;
}

export default function DataVisualization({ data, title }: DataVisualizationProps) {
  const [viewMode, setViewMode] = useState<'formatted' | 'table' | 'json'>('formatted');

  const renderFormattedData = (obj: any, depth = 0): JSX.Element => {
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

  const renderTable = (obj: any): JSX.Element => {
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

  return (
    <div className="space-y-4">
      {/* View Mode Selector */}
      <div className="flex space-x-2">
        <button
          onClick={() => setViewMode('formatted')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'formatted'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          📋 Formatted
        </button>
        <button
          onClick={() => setViewMode('table')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'table'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          📊 Table
        </button>
        <button
          onClick={() => setViewMode('json')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
            viewMode === 'json'
              ? 'bg-cyan-600/50 text-cyan-300 border border-cyan-500/50'
              : 'bg-gray-700/50 text-gray-400 border border-gray-600/50 hover:bg-gray-600/50'
          }`}
        >
          🔧 JSON
        </button>
      </div>

      {/* Content Display */}
      <div className="bg-gray-900/50 rounded-xl p-6 border border-gray-700/50 max-h-96 overflow-auto">
        {viewMode === 'formatted' && renderFormattedData(data)}
        {viewMode === 'table' && renderTable(data)}
        {viewMode === 'json' && (
          <pre className="text-sm text-gray-300 whitespace-pre-wrap">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}