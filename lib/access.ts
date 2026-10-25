import {timingSafeEqual} from 'node:crypto';

/** Optional password for the whole UI (HENGE_PASSWORD; HENGE_USER defaults to "henge"). Unset means open access. */
export function unauthorized(request: Request): Response | null {
  const password = process.env.HENGE_PASSWORD;
  if (!password) return null;
  const expected = Buffer.from(`${process.env.HENGE_USER || 'henge'}:${password}`);
  const header = request.headers.get('authorization') || '';
  const given = header.startsWith('Basic ') ? Buffer.from(header.slice(6), 'base64') : Buffer.alloc(0);
  if (given.length === expected.length && timingSafeEqual(given, expected)) return null;
  return new Response('Authentication required', {status: 401, headers: {'WWW-Authenticate': 'Basic realm="Henge", charset="UTF-8"'}});
}
