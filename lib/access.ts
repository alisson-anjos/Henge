import {createHash, randomBytes, scryptSync, timingSafeEqual} from 'node:crypto';
import {readFileSync, renameSync, statSync, unlinkSync, writeFileSync} from 'node:fs';
import path from 'node:path';

/** Optional login for the whole UI. HENGE_PASSWORD (user HENGE_USER, default "henge") wins; otherwise the user and
 * password saved from the UI in access.json in the bridge data folder (scrypt hash). Neither means open access. */
type Saved = {user: string; salt: string; hash: string};
export type AccessState = {enabled: boolean; source: 'env' | 'ui' | null; user: string};

const file = () => path.join(process.env.HENGE_DATA_DIR || '/data/henge-data', 'access.json');
let cache: {mtime: number; saved: Saved | null} | null = null;
// Headers that already passed, so scrypt runs once per browser session and not on every request.
let accepted = new Set<string>();

function saved(): Saved | null {
  try {
    const mtime = statSync(file()).mtimeMs;
    if (cache?.mtime !== mtime) {cache = {mtime, saved: JSON.parse(readFileSync(file(), 'utf8'))}; accepted = new Set();}
    return cache.saved;
  } catch {cache = null; return null;}
}

export function accessState(): AccessState {
  if (process.env.HENGE_PASSWORD) return {enabled: true, source: 'env', user: process.env.HENGE_USER || 'henge'};
  const s = saved();
  return s ? {enabled: true, source: 'ui', user: s.user} : {enabled: false, source: null, user: ''};
}

const same = (a: Buffer, b: Buffer) => a.length === b.length && timingSafeEqual(a, b);

function valid(user: string, password: string): boolean {
  if (process.env.HENGE_PASSWORD) return same(Buffer.from(`${user}:${password}`), Buffer.from(`${process.env.HENGE_USER || 'henge'}:${process.env.HENGE_PASSWORD}`));
  const s = saved();
  return !s || (user === s.user && same(scryptSync(password, Buffer.from(s.salt, 'hex'), 32), Buffer.from(s.hash, 'hex')));
}

export function unauthorized(request: Request): Response | null {
  if (!accessState().enabled) return null;
  const header = request.headers.get('authorization') || '';
  const key = createHash('sha256').update(header).digest('hex');
  if (accepted.has(key)) return null;
  const given = header.startsWith('Basic ') ? Buffer.from(header.slice(6), 'base64').toString() : '';
  const colon = given.indexOf(':');
  if (colon > 0 && valid(given.slice(0, colon), given.slice(colon + 1))) {accepted.add(key); return null;}
  return new Response('Authentication required', {status: 401, headers: {'WWW-Authenticate': 'Basic realm="Henge", charset="UTF-8"'}});
}

/** Save (or with no password, remove) the UI login. The env password cannot be changed from here. */
export function setAccess(user: string, password: string | null) {
  if (process.env.HENGE_PASSWORD) throw Error('The password is set by HENGE_PASSWORD on the server; change it there.');
  if (password === null) {try {unlinkSync(file());} catch {/* already open */} cache = null; accepted = new Set(); return;}
  if (!/^[\w.@-]{1,64}$/.test(user)) throw Error('Use a user name of letters, digits, . _ - or @.');
  if (password.length < 8) throw Error('Use a password of at least 8 characters.');
  const salt = randomBytes(16);
  const tmp = file() + '.tmp';
  writeFileSync(tmp, JSON.stringify({user, salt: salt.toString('hex'), hash: scryptSync(password, salt, 32).toString('hex')}), {mode: 0o600});
  renameSync(tmp, file());
}
