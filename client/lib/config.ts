/** Backend base URL (no trailing slash). Kept in its own module so lib/auth.ts and lib/api.ts do not import each other. */
export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || 'https://airaaagent.onrender.com'
).replace(/\/$/, '');
