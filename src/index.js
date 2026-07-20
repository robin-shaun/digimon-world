/**
 * Digimon World - Cloudflare Worker
 *
 * Proxies /api/* requests to the backend tunnel and serves static assets.
 * This avoids CORS issues and browser JS challenges from Cloudflare Tunnel.
 */
const BACKEND = 'https://relevant-comparisons-translator-batch.trycloudflare.com';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // Proxy API requests to the backend tunnel
    if (pathname.startsWith('/api/')) {
      const backendUrl = BACKEND + pathname + url.search;
      const backendReq = new Request(backendUrl, {
        method: request.method,
        headers: request.headers,
        body: request.method !== 'GET' && request.method !== 'HEAD' ? await request.clone().arrayBuffer() : undefined,
      });

      try {
        const resp = await fetch(backendReq);
        // Return the response with CORS headers
        const newHeaders = new Headers(resp.headers);
        newHeaders.set('Access-Control-Allow-Origin', '*');
        newHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
        newHeaders.set('Access-Control-Allow-Headers', '*');
        return new Response(resp.body, {
          status: resp.status,
          statusText: resp.statusText,
          headers: newHeaders,
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: 'Backend unreachable', detail: err.message }), {
          status: 502,
          headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
        });
      }
    }

    // Handle CORS preflight for API paths
    if (request.method === 'OPTIONS' && pathname.startsWith('/api/')) {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
          'Access-Control-Allow-Headers': '*',
          'Access-Control-Max-Age': '86400',
        },
      });
    }

    // Serve static assets for everything else
    return env.ASSETS.fetch(request);
  },
};
