/**
 * Keep-warm pinger for the AIRAA backend.
 *
 * Render's free tier puts a web service to sleep after 15 minutes without traffic, and the
 * next request then waits 30-60s for a cold start. A Cron Trigger pings /api/health every
 * 10 minutes so the service never idles long enough to sleep.
 *
 * TARGET_URLS: comma-separated health URLs (set in wrangler.toml [vars] or the dashboard).
 */

async function ping(url) {
  const started = Date.now();
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "airaa-keepalive/1.0" },
      signal: AbortSignal.timeout(90_000), // a cold start can take ~60s; let it finish waking up
    });
    return { url, status: res.status, ms: Date.now() - started };
  } catch (err) {
    return { url, status: 0, ms: Date.now() - started, error: String(err) };
  }
}

function targets(env) {
  return String(env.TARGET_URLS || "")
    .split(",")
    .map((u) => u.trim())
    .filter(Boolean);
}

export default {
  // Cron Trigger entry point
  async scheduled(_event, env, ctx) {
    const results = await Promise.all(targets(env).map(ping));
    for (const r of results) console.log(JSON.stringify(r));
  },

  // Visiting the worker URL runs a ping on demand, handy for checking the setup.
  async fetch(_request, env) {
    const results = await Promise.all(targets(env).map(ping));
    return Response.json({ pinged: results }, { status: results.every((r) => r.status === 200) ? 200 : 502 });
  },
};
