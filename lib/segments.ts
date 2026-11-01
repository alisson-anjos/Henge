/** SAM 3.1 character segments of one frame (HengeFindPeople's label map): shared by the frame editor and the assistant. */
export type Segments = {labels: Uint8Array; width: number; height: number; count: number};

const load = (src: string) => new Promise<HTMLImageElement>((resolve, reject) => {const image = new window.Image(); image.onload = () => resolve(image); image.onerror = reject; image.src = src;});

/** Segment the characters (people and animals) of a frame. Numbers run left to right, like find_people. */
export async function segmentFrame(frame: Blob): Promise<Segments & {overlay: string}> {
  const body = new FormData(); body.set('frame', frame, 'frame.png'); body.set('kind', 'character'); body.set('labels', '1');
  const response = await fetch('/api/backend/assistant/people', {method: 'POST', body});
  const reply = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(reply.detail || reply.error || `HTTP ${response.status}`);
  if (typeof reply.labels !== 'string') throw Error('This worker cannot return segments yet (update its image); describe or paint the character instead.');
  const im = await load(reply.labels);
  const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
  const g = c.getContext('2d', {willReadFrequently: true}); if (!g) throw Error('Canvas unavailable');
  g.drawImage(im, 0, 0); const rgba = g.getImageData(0, 0, c.width, c.height).data;
  const labels = new Uint8Array(c.width * c.height); for (let i = 0; i < labels.length; i++) labels[i] = rgba[i * 4];
  return {labels, width: c.width, height: c.height, count: Array.isArray(reply.people) ? reply.people.length : 0, overlay: reply.overlay};
}

/** The image with segment `number` painted magenta (60 %, so its outline and pose stay readable), as a PNG. */
export async function paintMagenta(src: string, segments: Segments, number: number): Promise<Blob> {
  const im = await load(src);
  const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
  const g = c.getContext('2d'); if (!g) throw Error('Canvas unavailable');
  g.drawImage(im, 0, 0); const data = g.getImageData(0, 0, c.width, c.height), d = data.data;
  for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
    const sx = Math.min(segments.width - 1, Math.floor(x * segments.width / c.width)), sy = Math.min(segments.height - 1, Math.floor(y * segments.height / c.height));
    if (segments.labels[sy * segments.width + sx] !== number) continue;
    const i = (y * c.width + x) * 4; d[i] = d[i] * .4 + 255 * .6; d[i + 1] = d[i + 1] * .4; d[i + 2] = d[i + 2] * .4 + 255 * .6;
  }
  g.putImageData(data, 0, 0);
  return new Promise((resolve, reject) => c.toBlob(b => b ? resolve(b) : reject(Error('Could not encode the frame')), 'image/png'));
}
