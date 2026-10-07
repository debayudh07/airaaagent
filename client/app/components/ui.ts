/** Shared Tailwind class sets for the account pages (memory, vault, alerts), matching the chat's button/field look. */
export const BTN =
  'inline-flex min-h-11 sm:min-h-10 items-center justify-center gap-1.5 rounded-full px-4 text-sm font-semibold transition-[background-color,transform] active:scale-95 touch-manipulation disabled:cursor-not-allowed disabled:opacity-50';
export const BTN_PRIMARY = `${BTN} bg-ink text-white hover:bg-accent hover:text-ink`;
export const BTN_SECONDARY = `${BTN} bg-field text-ink hover:bg-field-hover`;
export const BTN_DANGER = `${BTN} bg-[#ffe4e1] text-[#a3231a] hover:bg-[#ffd3cf]`;
export const INPUT =
  'min-h-11 w-full rounded-2xl border border-[#dcdde2] bg-white px-4 py-2 text-base text-ink placeholder:text-muted focus:border-ink focus:outline-none';
export const CARD = 'rounded-3xl border border-line bg-white p-5 sm:p-6';
export const LABEL = 'mb-1.5 block text-[13px] font-semibold text-ink-3';
export const NOTE_ERROR = 'rounded-2xl bg-[#ffe4e1] px-4 py-3 text-sm text-[#a3231a]';
export const NOTE_INFO = 'rounded-2xl bg-sky px-4 py-3 text-sm text-[#1e3a8a]';
export const NOTE_OK = 'rounded-2xl bg-mint px-4 py-3 text-sm text-[#0f5b3a]';

export const formatBytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

export const formatWhen = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—';

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
