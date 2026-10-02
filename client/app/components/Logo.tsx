import Link from 'next/link';

/** AIRAA mark plus wordmark; links home. */
export default function Logo({ size = 'md' }: { size?: 'md' | 'lg' }) {
  const box = size === 'lg' ? 'h-8 w-8 rounded-[9px]' : 'h-7 w-7 rounded-lg';
  const icon = size === 'lg' ? 18 : 16;
  return (
    <Link href="/" className="flex items-center gap-2.5 text-ink no-underline" aria-label="AIRAA home">
      <span className={`flex ${box} items-center justify-center bg-accent/[0.14]`}>
        <svg width={icon} height={icon} viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 17l6-6 4 4 8-8" />
          <path d="M14 7h7v7" />
        </svg>
      </span>
      <span className={`font-display font-bold ${size === 'lg' ? 'text-[19px] tracking-[0.5px]' : 'text-[17px]'}`}>AIRAA</span>
    </Link>
  );
}
