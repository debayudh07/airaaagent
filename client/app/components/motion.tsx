'use client';

import { useEffect, useRef, useState } from 'react';

const ROLL_EASE = 'transform 0.6s cubic-bezier(0.65, 0, 0.25, 1)';

/** One digit as a vertical 0-9 strip that rolls to its value. */
function DigitColumn({ digit, ready }: { digit: number; ready: boolean }) {
  return (
    <span className="inline-block h-[1em] overflow-hidden align-top leading-none">
      <span
        className="flex flex-col"
        style={{ transform: `translateY(-${ready ? digit : 0}em)`, transition: ROLL_EASE }}
      >
        {Array.from({ length: 10 }, (_, d) => (
          <span key={d} className="block h-[1em] leading-none">{d}</span>
        ))}
      </span>
    </span>
  );
}

/**
 * A number whose digits roll into place on mount and whenever the value changes; the row
 * flashes green when it rises and red when it falls.
 */
export function RollingNumber({ value, text, className = '' }: { value: number; text: string; className?: string }) {
  const [ready, setReady] = useState(false);
  const [flash, setFlash] = useState<{ dir: 'up' | 'down'; n: number } | null>(null);
  const prev = useRef(value);

  useEffect(() => {
    const id = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    if (value !== prev.current) {
      setFlash((f) => ({ dir: value > prev.current ? 'up' : 'down', n: (f?.n ?? 0) + 1 }));
      prev.current = value;
    }
  }, [value]);

  const chars = text.split('');
  return (
    <span className={`tabular relative inline-flex px-1 -mx-1 leading-none ${className}`} aria-label={text}>
      {flash && (
        <span
          key={flash.n}
          aria-hidden="true"
          className={`absolute inset-x-0 -inset-y-1 rounded-lg ${flash.dir === 'up' ? 'anim-flash-up' : 'anim-flash-down'}`}
        />
      )}
      <span aria-hidden="true" className="relative inline-flex">
        {chars.map((c, i) => {
          const key = chars.length - i; // align from the right so digits keep their place
          return /\d/.test(c)
            ? <DigitColumn key={key} digit={Number(c)} ready={ready} />
            : <span key={key} className="inline-block leading-none">{c}</span>;
        })}
      </span>
    </span>
  );
}

/** Price line that draws itself left to right, with an orange dot on the latest point. */
export function Sparkline({ points, height = 56, label }: { points: number[]; height?: number; label: string }) {
  if (points.length < 2) return null;
  const w = 200;
  const pad = 4;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const xy = points.map((p, i) => [
    (i / (points.length - 1)) * (w - pad * 2) + pad,
    height - pad - ((p - min) / span) * (height - pad * 2),
  ]);
  const d = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" role="img" aria-label={label} className="block overflow-visible">
      <path d={d} pathLength={1} className="anim-draw" fill="none" stroke="var(--ink)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      <circle cx={lx} cy={ly} r="3.5" fill="var(--accent)" className="anim-rise" style={{ animationDelay: '1.6s' }} />
    </svg>
  );
}
