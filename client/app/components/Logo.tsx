import Link from 'next/link';

/** The airaa mark: an ink tile with a rising line and an orange live dot. */
export function Mark({ size = 34 }: { size?: number }) {
  const dot = Math.round(size * 0.3);
  return (
    <span
      aria-hidden="true"
      className="relative flex shrink-0 items-center justify-center bg-ink"
      style={{ width: size, height: size, borderRadius: Math.round(size / 3) }}
    >
      <svg width={size / 2} height={size / 2} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 16l5-5 4 4 7-7" />
      </svg>
      <span className="absolute rounded-full border-2 border-white bg-accent" style={{ width: dot, height: dot, right: -3, top: -3 }} />
    </span>
  );
}

/** Mark plus wordmark; links home. */
export default function Logo({ size = 34 }: { size?: number }) {
  return (
    <Link href="/" className="flex items-center gap-2.5 text-ink no-underline" aria-label="airaa home">
      <Mark size={size} />
      <span className="font-display text-[21px] font-extrabold tracking-[-0.6px]">airaa</span>
    </Link>
  );
}
