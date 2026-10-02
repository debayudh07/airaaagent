'use client';

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { ChartSpec } from '../../lib/api';

const COLORS = ['#22d3ee', '#a78bfa', '#f472b6', '#34d399', '#f59e0b'];

function compactUsd(v: number) {
  const abs = Math.abs(v);
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  if (abs >= 1) return `$${v.toFixed(2)}`;
  return `$${v.toPrecision(3)}`;
}

function formatter(kind: ChartSpec['y_format']) {
  return (value: unknown) => {
    const v = Number(value);
    if (!Number.isFinite(v)) return String(value ?? '');
    if (kind === 'usd') return compactUsd(v);
    if (kind === 'percent') return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  };
}

/** Shorten "2026-09-03" to "Sep 3"; leave category labels alone. */
function tickLabel(x: unknown) {
  const s = String(x);
  if (!/^\d{4}-\d{2}-\d{2}/.test(s)) return s.length > 14 ? `${s.slice(0, 13)}…` : s;
  const d = new Date(s.length === 10 ? `${s}T00:00:00Z` : s.replace(' ', 'T') + ':00Z');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function ChartBody({ spec }: { spec: ChartSpec }) {
  const fmt = formatter(spec.y_format);
  const multi = spec.series.length > 1;
  const axes = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" vertical={false} />
      <XAxis dataKey={spec.x_key} tickFormatter={tickLabel} tick={{ fill: 'rgba(255,255,255,0.45)', fontSize: 11 }}
        tickLine={false} axisLine={false} minTickGap={24} interval={spec.kind === 'bar' ? 0 : 'preserveStartEnd'}
        angle={spec.kind === 'bar' && spec.data.length > 5 ? -30 : 0} textAnchor={spec.kind === 'bar' && spec.data.length > 5 ? 'end' : 'middle'}
        height={spec.kind === 'bar' && spec.data.length > 5 ? 56 : 28} />
      <YAxis tickFormatter={fmt} tick={{ fill: 'rgba(255,255,255,0.45)', fontSize: 11 }} tickLine={false} axisLine={false} width={64} />
      <Tooltip
        formatter={(v, name) => [fmt(v), name]}
        labelFormatter={(l) => String(l)}
        contentStyle={{ background: '#0b1220', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, fontSize: 12 }}
        labelStyle={{ color: 'rgba(255,255,255,0.7)' }}
        cursor={{ fill: 'rgba(255,255,255,0.04)' }}
      />
      {multi && <Legend wrapperStyle={{ fontSize: 12, color: 'rgba(255,255,255,0.7)' }} />}
    </>
  );

  if (spec.kind === 'bar') {
    return (
      <BarChart data={spec.data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        {axes}
        {spec.series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} maxBarSize={40} />
        ))}
      </BarChart>
    );
  }
  if (spec.kind === 'area') {
    return (
      <AreaChart data={spec.data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          {spec.series.map((s, i) => (
            <linearGradient key={s.key} id={`fill-${spec.id}-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COLORS[i % COLORS.length]} stopOpacity={0.35} />
              <stop offset="100%" stopColor={COLORS[i % COLORS.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        {axes}
        {spec.series.map((s, i) => (
          <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={COLORS[i % COLORS.length]}
            strokeWidth={2} fill={`url(#fill-${spec.id}-${i})`} dot={false} connectNulls />
        ))}
      </AreaChart>
    );
  }
  return (
    <LineChart data={spec.data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
      {axes}
      {spec.series.map((s, i) => (
        <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={COLORS[i % COLORS.length]}
          strokeWidth={2} dot={false} connectNulls />
      ))}
    </LineChart>
  );
}

/** Charts the agent built from the data it fetched (never model-drawn). */
export default function AgentCharts({ charts }: { charts?: ChartSpec[] }) {
  if (!charts?.length) return null;
  return (
    <div className={`grid gap-3 ${charts.length > 1 ? 'md:grid-cols-2' : ''}`}>
      {charts.map((spec, i) => (
        <figure
          key={spec.id}
          className={`rounded-xl border border-white/10 bg-black/20 p-3 ${charts.length === 3 && i === 0 ? 'md:col-span-2' : ''}`}
        >
          <figcaption className="mb-2 flex items-baseline justify-between gap-2">
            <span className="text-sm font-medium text-white/85">{spec.title}</span>
            {spec.subtitle && <span className="truncate text-[11px] text-white/40">{spec.subtitle}</span>}
          </figcaption>
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ChartBody spec={spec} />
            </ResponsiveContainer>
          </div>
        </figure>
      ))}
    </div>
  );
}
