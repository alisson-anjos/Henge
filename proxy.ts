import {unauthorized} from './lib/access';

// Pages and static files. API routes check the password themselves: going through proxy would cap their
// request bodies at 10 MB (proxyClientMaxBodySize), which breaks guide video uploads.
export function proxy(request: Request) {
  return unauthorized(request) ?? undefined;
}

export const config = {matcher: ['/((?!api/).*)']};
