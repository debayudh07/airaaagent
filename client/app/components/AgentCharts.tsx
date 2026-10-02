'use client';

import { useEffect, useState } from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { ChartSpec } from '../../lib/api';

const COLORS = ['#0b0d12', '#7c5ce0', '#ff5a1f', '#2448c8', '#077a4b'];
/** Pastel tile behind each chart, matching the board's pins. */
const TILES = ['#dcf3e6', '#ece5ff', '#e2eaff', '#fff1bf', '#ffe7db'];
const AXIS_TICK = { fill: '#5b616e', fontSize: 11 };
const VALUE_LABEL = { fill: '#0b0d12', fontSize: 11, fontWeight: 700 };
/** Bars carry value labels instead of a y-axis up to this many categories. */
const MAX_LABELLED_BARS = 8;
/** Ranked bar charts show at most this many rows, and go horizontal past HORIZONTAL_FROM categories. */
const MAX_BARS = 8;
const HORIZONTAL_FROM = 5;
const ROW_PX = 34;

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
    contentStyle={{ background: '#ffffff', border: '1px solid #e7e8ec', borderRadius: 10, fontSize: 12 }}
    labelStyle={{ color: '#2a2e37' }}
    itemStyle={{ color: '#0b0d12' }}
    cursor={cursor}
  />
);

function barChart({ spec, color, horizontal, narrow }: { spec: ChartSpec; color: (i: number) => string; horizontal: boolean; narrow: boolean }) {
  const fmt = formatter(spec.y_format, false);
  const tip = tooltip(exact(spec.y_format, false), { fill: 'rgba(11,13,18,0.05)' });
  const multi = spec.series.length > 1;
  const labelled = !multi && spec.data.length <= MAX_LABELLED_BARS;

  if (horizontal) {
    return (
      <BarChart data={spec.data} layout="vertical" margin={{ top: 0, right: labelled ? 52 : 8, bottom: 0, left: 0 }} barCategoryGap={6}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey={spec.x_key} width={narrow ? 104 : 150} tickFormatter={tickLabel(narrow ? 15 : 22)}
          tick={{ ...AXIS_TICK, fill: '#2a2e37', fontSize: 12 }} tickLine={false} axisLine={false} interval={0} />
        {tip}
        {multi && <Legend wrapperStyle={{ fontSize: 12, color: '#2a2e37' }} />}
        {spec.series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={color(i)} radius={[0, 6, 6, 0]} maxBarSize={18}>
            {labelled && <LabelList dataKey={s.key} position="right" formatter={fmt} style={VALUE_LABEL} />}
          </Bar>
        ))}
      </BarChart>
    );
  }

  const tilt = spec.data.length > 6;
  return (
    <BarChart data={spec.data} margin={{ top: labelled ? 18 : 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="14%">
      {!labelled && <CartesianGrid stroke="rgba(11,13,18,0.1)" vertical={false} />}
      <XAxis dataKey={spec.x_key} tickFormatter={tickLabel(16)} tick={{ ...AXIS_TICK, fill: '#2a2e37' }}
        tickLine={false} axisLine={{ stroke: 'rgba(11,13,18,0.18)' }} interval={0}
        angle={tilt ? -30 : 0} textAnchor={tilt ? 'end' : 'middle'} height={tilt ? 56 : 28} />
      <YAxis hide={labelled} tickFormatter={fmt} tick={AXIS_TICK} tickLine={false} axisLine={false} width={60} />
      {tip}
      {multi && <Legend wrapperStyle={{ fontSize: 12, color: '#2a2e37' }} />}
      {spec.series.map((s, i) => (
        <Bar key={s.key} dataKey={s.key} name={s.label} fill={color(i)} radius={[10, 10, 3, 3]} maxBarSize={72} minPointSize={3}>
          {labelled && <LabelList dataKey={s.key} position="top" formatter={fmt} style={VALUE_LABEL} />}
        </Bar>
      ))}
    </BarChart>
  );
}

function seriesChart({ spec, color }: { spec: ChartSpec; color: (i: number) => string }) {
  const signed = spec.kind === 'line';
  const fmt = formatter(spec.y_format, signed);
  const multi = spec.series.length > 1;
  const axes = (
    <>
      <CartesianGrid stroke="rgba(11,13,18,0.1)" vertical={false} />
      <XAxis dataKey={spec.x_key} tickFormatter={tickLabel()} tick={AXIS_TICK} tickLine={false}
        axisLine={{ stroke: 'rgba(11,13,18,0.18)' }} minTickGap={28} interval="preserveStartEnd" />
      <YAxis tickFormatter={fmt} tick={AXIS_TICK} tickLine={false} axisLine={false} width={60} domain={['auto', 'auto']} />
      {tooltip(exact(spec.y_format, signed), { stroke: 'rgba(11,13,18,0.3)' })}
      {multi && <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: '#2a2e37' }} />}
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

function ChartCard({ spec, index, narrow }: { spec: ChartSpec; index: number; narrow: boolean }) {
  // One series: ink on the pastel tile. Several: one colour per series.
  const color = (i: number) => COLORS[(spec.series.length > 1 ? i : 0) % COLORS.length];
  const shown = spec.kind === 'bar' ? { ...spec, data: spec.data.slice(0, MAX_BARS) } : spec;
  const horizontal = shown.kind === 'bar' && (narrow || shown.data.length > HORIZONTAL_FROM);
  const height = horizontal ? Math.max(120, shown.data.length * ROW_PX + 8) : 208;

  return (
    <figure
      className={`anim-rise m-0 min-w-0 rounded-3xl p-4 sm:p-[22px] `}
      style={{ background: TILES[index % TILES.length], animationDelay: `${index * 80}ms` }}
    >
      <figcaption className="mb-3 flex flex-col gap-0.5 sm:mb-4">
        <span className="font-display text-base font-bold text-ink sm:text-lg">{spec.title}</span>
        {spec.subtitle && <span className="text-xs text-ink-3/70">{spec.subtitle}</span>}
      </figcaption>
      <div className="w-full" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {/* Called, not mounted as components: ResponsiveContainer must hand its width/height straight to the chart element. */}
          {spec.kind === 'bar'
            ? barChart({ spec: shown, color, horizontal, narrow })
            : seriesChart({ spec, color })}
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
    <div className="grid gap-3">
      {charts.map((spec, i) => (
        <ChartCard key={spec.id} spec={spec} index={i} narrow={narrow} />
      ))}
    </div>
  );
}
