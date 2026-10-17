export type Picture = {slot: number; file: File; url: string};
export async function imageData(file: File, max = 1024): Promise<string> {
  const image = await createImageBitmap(file);
  try {
    const scale = Math.min(1, max / Math.max(image.width, image.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale));
    const ctx = canvas.getContext('2d'); if (!ctx) throw Error('Canvas unavailable.');
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', .85);
  } finally {image.close();}
}
export async function videoFrames(file: File, range?: {start:number;end:number}, count = 6): Promise<{time: number; data: string}[]> {
  const url = URL.createObjectURL(file), video = document.createElement('video');
  video.preload = 'auto'; video.muted = true; video.playsInline = true;
  const event = (name: string) => new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => done(Error('Video decoding timed out.')), 20000);
    const success = () => done(); const failure = () => done(Error('This video cannot be decoded by your browser.'));
    const done = (error?: Error) => {clearTimeout(timer); video.removeEventListener(name, success); video.removeEventListener('error', failure); error ? reject(error) : resolve();};
    video.addEventListener(name, success, {once:true}); video.addEventListener('error', failure, {once:true});
  });
  try {
    const loaded = event('loadeddata'); video.src = url; await loaded;
    if (!Number.isFinite(video.duration) || video.duration <= 0) throw Error('Invalid video duration.');
    const canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
    if (!ctx) throw Error('Canvas unavailable.');
    const scale = Math.min(1, 768 / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale)); canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const start = range?.start ?? 0, end = range?.end ?? video.duration;
    if (start < 0 || end > video.duration || end <= start) throw Error('Invalid guide interval.');
    const frames = [];
    for (let i = 0; i < count; i++) {
      const time = Math.min(start + (end-start) * (i / (count-1)), Math.max(start, end - .05));
      if (Math.abs(time-video.currentTime) > .001) {const sought=event('seeked'); video.currentTime=time; await sought;}
      ctx.drawImage(video,0,0,canvas.width,canvas.height); frames.push({time,data:canvas.toDataURL('image/jpeg',.8)});
    }
    return frames;
  } finally {video.removeAttribute('src'); video.load(); URL.revokeObjectURL(url);}
}
