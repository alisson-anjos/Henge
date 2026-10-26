'use client';
import {useEffect, useRef, useState} from 'react';
import type {Language} from '../lib/design-copy';

/** Approval screen for a 2D color guide: the tracked marks (rendered once at full opacity) laid over the same source
 * clip. CSS opacity on the top video is the same blend HengeGuide makes, so the slider shows the real result live. */
export default function MarksPreview({jobId, sourceUrl, marksUrl, initial, editable, lang}: {jobId: string; sourceUrl: string; marksUrl: string; initial: number; editable: boolean; lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const base = useRef<HTMLVideoElement>(null), top = useRef<HTMLVideoElement>(null);
  const [opacity, setOpacity] = useState(initial);
  const [error, setError] = useState('');
  const saved = useRef(initial);

  // Keep the two clips on the same frame (they have the same length and frame rate).
  useEffect(() => {
    const a = base.current, b = top.current; if (!a || !b) return;
    const sync = () => {if (Math.abs(a.currentTime - b.currentTime) > .08) b.currentTime = a.currentTime;};
    const play = () => {b.play().catch(() => {});}, pause = () => b.pause();
    a.addEventListener('timeupdate', sync); a.addEventListener('seeked', sync); a.addEventListener('play', play); a.addEventListener('pause', pause);
    return () => {a.removeEventListener('timeupdate', sync); a.removeEventListener('seeked', sync); a.removeEventListener('play', play); a.removeEventListener('pause', pause);};
  }, [sourceUrl, marksUrl]);

  // Store the chosen opacity on the job a moment after the slider stops.
  useEffect(() => {
    if (!editable || opacity === saved.current) return;
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(`/api/backend/jobs/${jobId}/marks`, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({mark_opacity: opacity})});
        if (!r.ok) throw Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
        saved.current = opacity; setError('');
      } catch (e) {setError(e instanceof Error ? e.message : String(e));}
    }, 400);
    return () => clearTimeout(timer);
  }, [opacity, editable, jobId]);

  return <div className="mask-preview marks-preview">
    <div className="label-row"><strong>{tr('Color guide preview', 'Prévia do guia por cores', 'Vista previa de la guía por colores')}</strong><small className="muted">{tr('first shot', 'primeiro shot', 'primer plano')}</small></div>
    <div className="marks-stack">
      <video ref={base} src={sourceUrl} autoPlay loop muted playsInline controls/>
      <video ref={top} src={marksUrl} autoPlay loop muted playsInline aria-hidden="true" style={{opacity}}/>
    </div>
    <label className="marks-opacity"><span>{tr('Mark opacity', 'Opacidade da marcação', 'Opacidad de la marca')} <b className="mono">{Math.round(opacity * 100)}%</b></span>
      <input type="range" min="0.1" max="1" step="0.05" value={opacity} disabled={!editable} onChange={e => setOpacity(Number(e.target.value))}/></label>
    <small className="muted">{tr('This is what H3 receives as the guide. Each color must stay on its own person for the whole shot; lower opacity keeps the face and expression, but more of the original look can leak into the result.', 'É isto que o H3 recebe como guia. Cada cor precisa ficar na sua pessoa durante todo o shot; opacidade menor mantém rosto e expressão, mas mais da aparência original pode vazar no resultado.', 'Esto es lo que H3 recibe como guía. Cada color debe quedarse en su persona durante todo el plano; menos opacidad conserva la cara y la expresión, pero más del aspecto original puede filtrarse.')}</small>
    {error && <p className="validation" role="alert">{error}</p>}
  </div>;
}
