/** Parse a backend reply; a proxy or server error page becomes a readable message instead of a JSON SyntaxError. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function readJson<T = any>(response: Response): Promise<T> {
  const text = await response.text();
  try { return (text ? JSON.parse(text) : {}) as T; }
  catch { return {detail: response.ok ? text : `Backend error ${response.status}${text ? ': ' + text.slice(0, 200) : ''}`} as T; }
}
