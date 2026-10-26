/** A short, readable job error. Serverless failures arrive as the worker's JSON (with a Python traceback); keep the
 * message and turn the common causes into plain advice. The full text stays available as `detail`. */
export function readableError(raw: string | undefined | null): {summary: string; detail: string} {
  const detail = String(raw || '');
  let message = detail;
  const json = detail.indexOf('{');
  if (json >= 0) {
    try {const parsed = JSON.parse(detail.slice(json)); if (typeof parsed.error_message === 'string') message = parsed.error_message;}
    catch {/* not JSON: keep the text */}
  }
  message = message.split(/\n\s*Traceback|\\nTraceback/)[0].replace(/\\n/g, ' ').replace(/\s+/g, ' ').trim();
  const model = message.match(/Model in folder '([^']+)' with filename '([^']+)' not found/);
  if (model) return {summary: `The GPU worker is missing the model ${model[2]} (folder ${model[1]}). Install its model profile on the volume, then retry.`, detail};
  if (/out of memory|CUDA error: out of memory/i.test(message)) return {summary: 'The GPU ran out of memory. Try a lower quality, fewer frames per shot, or a larger GPU.', detail};
  if (/progress connection closed/i.test(message)) return {summary: 'ComfyUI stopped while running (often out of RAM). Retry; if it repeats, lower the quality or shot length.', detail};
  return {summary: message.length > 400 ? message.slice(0, 400) + '…' : message, detail};
}
