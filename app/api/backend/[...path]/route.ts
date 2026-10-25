import {unauthorized} from '../../../../lib/access';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const base = (process.env.HENGE_BACKEND_URL || 'http://127.0.0.1:8766').replace(/\/$/, '');
async function proxy(request: Request, context: {params: Promise<{path: string[]}>}) {
  const denied = unauthorized(request); if (denied) return denied;
  const {path} = await context.params;
  const route = path.join('/');
  if (!/^(health|settings|jobs(?:\/[a-f0-9]{32}(?:\/(?:approve|cancel|retry|preparation|mask-preview|comparison-with-refs|workflow|source\/(?:video|picture_(?:[1-9]|1[01]))|files\/(?:result\.mp4|comparison\.mp4|guide_preview\.mp4|fibo_preview\.png|sampling_preview\.jpg|mask_preview\.mp4|reference_(?:[1-9]|1[01])_prepared\.png)))?)?)$/.test(route)) return Response.json({error: 'Unknown backend route'}, {status: 404});
  try {
    const headers = new Headers();
    for (const name of ['content-type', 'range', 'if-range']) {const value = request.headers.get(name); if (value) headers.set(name, value);}
    const options: RequestInit & {duplex?: 'half'} = {method: request.method, headers, cache: 'no-store', signal: request.signal};
    if (!['GET', 'HEAD'].includes(request.method)) {options.body = request.body; options.duplex = 'half';}
    const response = await fetch(`${base}/${route}${new URL(request.url).search}`, options);
    const outputHeaders = new Headers();
    for (const name of ['content-type', 'content-length', 'content-range', 'accept-ranges', 'content-disposition']) {const value = response.headers.get(name); if (value) outputHeaders.set(name, value);}
    return new Response(response.body, {status: response.status, headers: outputHeaders});
  } catch { return Response.json({error: 'Henge backend is offline. Start the backend services.'}, {status: 503}); }
}
export const GET = proxy;
export const POST = proxy;
