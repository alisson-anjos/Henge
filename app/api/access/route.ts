import {accessState, setAccess, unauthorized} from '../../../lib/access';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Whether the UI asks for a login, and (only for someone already logged in, or while it is open) changing it. */
export function GET(request: Request) {
  return unauthorized(request) ?? Response.json(accessState());
}

export async function POST(request: Request) {
  const denied = unauthorized(request); if (denied) return denied;
  try {
    const body = await request.json();
    setAccess(String(body.user || '').trim(), body.disable ? null : String(body.password || ''));
    return Response.json(accessState());
  } catch (e) {return Response.json({error: e instanceof Error ? e.message : String(e)}, {status: 400});}
}
