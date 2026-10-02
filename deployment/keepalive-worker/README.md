# Keep-warm worker

Render's free tier sleeps a service after 15 minutes without traffic; the next visitor then waits
30-60 seconds. This Cloudflare Worker pings `/api/health` every 10 minutes so that never happens.
It fits in Cloudflare's free plan (cron triggers included, a few thousand requests a month).

## Deploy (once)

```bash
cd deployment/keepalive-worker
npx wrangler login          # opens the browser to authorise your Cloudflare account
npx wrangler deploy         # creates the worker and its cron trigger
```

Change the backend URL in `wrangler.toml` (`TARGET_URLS`, comma-separated for several) if yours differs.
Open the worker's `*.workers.dev` URL to trigger a ping by hand and see the result.

## Notes

- One always-on service uses ~730 of Render's 750 free instance-hours per month, so keep only one
  free service warm this way.
- Alternative without Cloudflare: `.github/workflows/keepalive.yml` does the same with GitHub Actions
  (scheduled runs can be delayed by GitHub, and private repos spend Actions minutes).
