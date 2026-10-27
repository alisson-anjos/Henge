/** Still frames and thumbnails in the browser, for the studio assistant. */

function canvasBlob(canvas: HTMLCanvasElement, type: string, quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) => canvas.toBlob(b => b ? resolve(b) : reject(Error('Unable to encode the frame')), type, quality));
}

/** One frame of a video at `time` seconds, at its full size, as PNG. */
export async function captureFrame(url: string, time: number): Promise<{blob: Blob; width: number; height: number}> {
  const video = document.createElement('video');
  video.muted = true; video.playsInline = true; video.preload = 'auto'; video.src = url;
  await new Promise<void>((resolve, reject) => {video.onloadeddata = () => resolve(); video.onerror = () => reject(Error('Unable to read the video'));});
  await new Promise<void>(resolve => {video.onseeked = () => resolve(); video.currentTime = Math.min(Math.max(0, time), Math.max(0, video.duration - .05));});
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext('2d')?.drawImage(video, 0, 0);
  const blob = await canvasBlob(canvas, 'image/png');
  video.removeAttribute('src'); video.load();
  return {blob, width: canvas.width, height: canvas.height};
}

/** A JPEG data URL no larger than `max` pixels on its long side (for sending pictures to the model). */
export async function thumbnail(source: Blob, max = 640): Promise<string> {
  const bitmap = await createImageBitmap(source);
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await canvasBlob(canvas, 'image/jpeg', .85);
  return await new Promise<string>((resolve, reject) => {const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = () => reject(r.error); r.readAsDataURL(blob);});
}

/** A JPEG data URL of `source` (longest side `max`) with `draw` painted over it in its own pixel size. */
export async function annotated(source: Blob, max: number, draw: (g: CanvasRenderingContext2D, w: number, h: number) => void): Promise<string> {
  const bitmap = await createImageBitmap(source);
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
  const g = canvas.getContext('2d'); if (!g) throw Error('No canvas');
  g.drawImage(bitmap, 0, 0, canvas.width, canvas.height); bitmap.close();
  draw(g, canvas.width, canvas.height);
  const blob = await canvasBlob(canvas, 'image/jpeg', .85);
  return await new Promise<string>((resolve, reject) => {const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = () => reject(r.error); r.readAsDataURL(blob);});
}

/** A coordinate grid (0-1, a line every 0.1, labelled) for the assistant to read positions. */
export function drawGrid(g: CanvasRenderingContext2D, w: number, h: number) {
  g.lineWidth = 1; g.font = `${Math.max(11, Math.round(w / 80))}px sans-serif`;
  for (let i = 1; i < 10; i++) {
    const x = Math.round(w * i / 10) + .5, y = Math.round(h * i / 10) + .5, label = (i / 10).toFixed(1);
    g.strokeStyle = i === 5 ? 'rgba(255,255,0,.75)' : 'rgba(255,255,255,.45)';
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
    for (const [text, tx, ty] of [[label, x + 3, 14], [label, 3, y - 3]] as const) {g.fillStyle = 'rgba(0,0,0,.65)'; g.fillRect(tx - 2, ty - 12, g.measureText(text).width + 4, 15); g.fillStyle = '#fff'; g.fillText(text, tx, ty);}
  }
}

/** A marked point (0-1) with a label, as mark_subject shows it back. */
export function drawPoint(g: CanvasRenderingContext2D, w: number, h: number, x: number, y: number, color: string, label: string) {
  const px = x * w, py = y * h, r = Math.max(7, w / 90);
  g.lineWidth = 3; g.strokeStyle = '#000'; g.fillStyle = color;
  g.beginPath(); g.arc(px, py, r, 0, Math.PI * 2); g.fill(); g.stroke();
  g.font = `bold ${Math.max(13, Math.round(w / 60))}px sans-serif`; g.lineWidth = 4; g.strokeText(label, px + r + 4, py + 5); g.fillStyle = '#fff'; g.fillText(label, px + r + 4, py + 5);
}
