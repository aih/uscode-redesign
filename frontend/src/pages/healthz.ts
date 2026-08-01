// Health of this SSR process only — must not call the API. Astro's base
// (/app) makes this reachable at /app/healthz.
export function GET() {
  return new Response("ok", { headers: { "cache-control": "no-store" } });
}
