'use client';

import { useEffect, useState } from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { ChartSpec } from '../../lib/api';

const COLORS = ['#22d3ee', '#a78bfa', '#f5a524', '#34d399', '#f472b6'];
const AXIS_TICK = { fill: '#7a889d', fontSize: 11 };
const VALUE_LABEL = { fill: '#c9d3e0', fontSize: 10, fontFamily: 'var(--font-code), monospace' };
/** Bars carry value labels instead of a y-axis up to this many categories. */
const MAX_LABELLED_BARS = 8;

function compactUsd(v: number) {
  const abs = Math.abs(v);
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  if (abs >= 1) return `$${v.toFixed(2)}`;
  return `$${v.toPrecision(3)}`;
}

function formatter(kind: ChartSpec['y_format'], signed: boolean) {
  return (value: unknown) => {
    const v = Number(value);
    if (!Number.isFinite(v)) return String(value ?? '');
    if (kind === 'usd') return compactUsd(v);
    if (kind === 'percent') return `${signed && v > 0 ? '+' : ''}${v.toFixed(2)}%`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  };
}

/** Full-precision value for tooltips. */
function exact(kind: ChartSpec['y_format'], signed: boolean) {
  const short = formatter(kind, signed);
  return (value: unknown) => {
    const v = Number(value);
    if (kind !== 'usd' || !Number.isFinite(v) || Math.abs(v) < 1) return short(value);
    return `$${v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) >= 1000 ? 0 : 2 })}`;
  };
}

/** Shorten "2026-09-03" to "Sep 3"; truncate long category labels. */
function tickLabel(max = 14) {
  return (x: unknown) => {
    const s = String(x);
    if (!/^\d{4}-\d{2}-\d{2}/.test(s)) return s.length > max ? `${s.slice(0, max - 1)}…` : s;
    const d = new Date(s.length === 10 ? `${s}T00:00:00Z` : s.replace(' ', 'T') + ':00Z');
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
  };
}

function useNarrow() {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 639px)');
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  return narrow;
}

const tooltip = (fmt: (v: unknown) => string, cursor: object) => (
  <Tooltip
    formatter={(v, name) => [fmt(v), name]}
    labelFormatter={(l) => String(l)}
    contentStyle={{ background: '#0d1422', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 10, fontSize: 12 }}
    labelStyle={{ color: '#9aa8bc' }}
    itemStyle={{ color: '#e6edf6' }}
    cursor={cursor}
  />
);

function BarBody({ spec, color, horizontal }: { spec: ChartSpec; color: (i: number) => string; horizontal: boolean }) {
  const fmt = formatter(spec.y_format, false);
  const tip = tooltip(exact(spec.y_format, false), { fill: 'rgba(255,255,255,0.04)' });
  const multi = spec.series.length > 1;
  const labelled = !multi && spec.data.length <= MAX_LABELLED_BARS;

  if (horizontal) {
    return (
      <BarChart data={spec.data} layout="vertical" margin={{ top: 0, right: labelled ? 52 : 8, bottom: 0, left: 0 }} barCategoryGap={6}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey={spec.x_key} width={104} tickFormatter={tickLabel(15)}
          tick={{ ...AXIS_TICK, fill: '#9aa8bc', fontSize: 12 }} tickLine={false} axisLine={false} interval={0} />
        {tip}
        {multi && <Legend wrapperStyle={{ fontSize: 12, color: '#9aa8bc' }} />}
        {spec.series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={color(i)} radius={[0, 3, 3, 0]} maxBarSize={14}>
            {labelled && <LabelList dataKey={s.key} position="right" formatter={fmt} style={VALUE_LABEL} />}
          </Bar>
        ))}
      </BarChart>
    );
  }

  const tilt = spec.data.length > 6;
  return (
    <BarChart data={spec.data} margin={{ top: labelled ? 18 : 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="14%">
      {!labelled && <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />}
      <XAxis dataKey={spec.x_key} tickFormatter={tickLabel(16)} tick={{ ...AXIS_TICK, fill: '#9aa8bc' }}
        tickLine={false} axisLine={{ stroke: 'rgba(255,255,255,0.1)' }} interval={0}
        angle={tilt ? -30 : 0} textAnchor={tilt ? 'end' : 'middle'} height={tilt ? 56 : 28} />
      <YAxis hide={labelled} tickFormatter={fmt} tick={AXIS_TICK} tickLine={false} axisLine={false} width={60} />
      {tip}
      {multi && <Legend wrapperStyle={{ fontSize: 12, color: '#9aa8bc' }} />}
      {spec.series.map((s, i) => (
        <Bar key={s.key} dataKey={s.key} name={s.label} fill={color(i)} radius={[5, 5, 0, 0]} maxBarSize={72} minPointSize={3}>
          {labelled && <LabelList dataKey={s.key} position="top" formatter={fmt} style={VALUE_LABEL} />}
        </Bar>
      ))}
    </BarChart>
  );
}

function SeriesBody({ spec, color }: { spec: ChartSpec; color: (i: number) => string }) {
  const signed = spec.kind === 'line';
  const fmt = formatter(spec.y_format, signed);
  const multi = spec.series.length > 1;
  const axes = (
    <>
      <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
      <XAxis dataKey={spec.x_key} tickFormatter={tickLabel()} tick={AXIS_TICK} tickLine={false}
        axisLine={{ stroke: 'rgba(255,255,255,0.1)' }} minTickGap={28} interval="preserveStartEnd" />
      <YAxis tickFormatter={fmt} tick={AXIS_TICK} tickLine={false} axisLine={false} width={60} domain={['auto', 'auto']} />
      {tooltip(exact(spec.y_format, signed), { stroke: 'rgba(255,255,255,0.2)' })}
      {multi && <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: '#9aa8bc' }} />}
    </>
  );

  if (spec.kind === 'area') {
    return (
      <AreaChart data={spec.data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          {spec.series.map((s, i) => (
            <linearGradient key={s.key} id={`fill-${spec.id}-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color(i)} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color(i)} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        {axes}
        {spec.series.map((s, i) => (
          <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={color(i)}
            strokeWidth={2} fill={`url(#fill-${spec.id}-${i})`} dot={false} connectNulls />
        ))}
      </AreaChart>
    );
  }
  return (
    <LineChart data={spec.data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
      {axes}
      {spec.series.map((s, i) => (
        <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={color(i)}
          strokeWidth={2} dot={false} connectNulls />
      ))}
    </LineChart>
  );
}

function ChartCard({ spec, index, wide, narrow }: { spec: ChartSpec; index: number; wide: boolean; narrow: boolean }) {
  // One series: colour by chart position so neighbouring charts differ. Several: colour by series.
  const color = (i: number) => COLORS[(spec.series.length > 1 ? i : index) % COLORS.length];
  const horizontal = spec.kind === 'bar' && narrow;
  const height = horizontal ? Math.max(120, spec.data.length * 24 + 8) : 208;

  return (
    <figure className={`m-0 min-w-0 rounded-[14px] border border-line bg-surface px-3.5 py-3 sm:px-4 sm:py-3.5 ${wide ? 'md:col-span-2' : ''}`}>
      <figcaption className="mb-3 flex flex-col gap-0.5 sm:mb-3.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-2">
        <span className="text-[13px] font-medium text-ink sm:text-sm">{spec.title}</span>
        {spec.subtitle && <span className="truncate text-[11px] text-subtle">{spec.subtitle}</span>}
      </figcaption>
      <div className="w-full" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {spec.kind === 'bar'
            ? <BarBody spec={spec} color={color} horizontal={horizontal} />
            : <SeriesBody spec={spec} color={color} />}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/** Charts the agent built from the data it fetched (never model-drawn). */
export default function AgentCharts({ charts }: { charts?: ChartSpec[] }) {
  const narrow = useNarrow();
  if (!charts?.length) return null;
  return (
    <div className={`grid gap-3 ${charts.length > 1 ? 'md:grid-cols-2' : ''}`}>
      {charts.map((spec, i) => (
        <ChartCard key={spec.id} spec={spec} index={i} narrow={narrow} wide={charts.length % 2 === 1 && charts.length > 1 && i === 0} />
      ))}
    </div>
  );
}
