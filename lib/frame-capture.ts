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
