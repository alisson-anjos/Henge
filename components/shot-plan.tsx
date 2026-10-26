'use client';
import {useEffect, useState} from 'react';
import type {Language} from '../lib/design-copy';

export type CutMode = 'fit' | 'every' | 'off';
type Shot = {index: number; start: number; end: number; context_seconds: number; after_cut: boolean};

export const cutModeLabel = (mode: CutMode, lang: Language) => ({
  fit: {en: 'Shot length, ending at camera cuts', pt: 'Tamanho do trecho, terminando em cortes de câmera', es: 'Longitud del tramo, terminando en cortes de cámara'},
  every: {en: 'New shot at every camera cut', pt: 'Novo trecho a cada corte de câmera', es: 'Nuevo tramo en cada corte de cámara'},
  off: {en: 'Fixed length (ignore camera cuts)', pt: 'Tamanho fixo (ignorar cortes de câmera)', es: 'Longitud fija (ignorar cortes de cámara)'},
})[mode][lang];

const clock = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`;

/** How the guide will be split into shots, each playable from the source, before rendering. While the job awaits
 * approval the split can be changed. */
export default function ShotPlan({jobId, editable, lang}: {jobId: string; editable: boolean; lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [plan, setPlan] = useState<{cut_mode: CutMode; shots: Shot[]} | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setPlan(null); setError('');
    fetch(`/api/backend/jobs/${jobId}/shots`).then(async r => {const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`); setPlan(reply);}).catch(e => setError(String(e.message || e)));
  }, [jobId]);

  async function change(mode: CutMode) {
    setBusy(true); setError('');
    try {
      const r = await fetch(`/api/backend/jobs/${jobId}/shots`, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({cut_mode: mode})});
      const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`); setPlan(reply);
    } catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
  }

  if (error) return <small className="muted">{error}</small>;
  if (!plan) return <small className="muted">{tr('Splitting the guide into shots…', 'Dividindo o guia em trechos…', 'Dividiendo la guía en tramos…')}</small>;
  return <div className="shot-plan">
    <div className="label-row"><small className="muted">{tr('Shots', 'Trechos', 'Tramos')} · {plan.shots.length}</small>
      {editable ? <select aria-label={tr('Camera cuts', 'Cortes de câmera', 'Cortes de cámara')} value={plan.cut_mode} disabled={busy} onChange={e => change(e.target.value as CutMode)}>{(['fit', 'every', 'off'] as CutMode[]).map(m => <option key={m} value={m}>{cutModeLabel(m, lang)}</option>)}</select>
        : <small className="muted">{cutModeLabel(plan.cut_mode, lang)}</small>}</div>
    <div>{plan.shots.map(s => <figure key={`${s.index}-${s.start}`}>
      <video controls playsInline preload="metadata" src={`/api/backend/jobs/${jobId}/source/video#t=${s.start},${s.end}`}/>
      <figcaption><span className="mono">{s.index} · {clock(s.start)}–{clock(s.end)}</span>{s.after_cut ? <span className="shot-tag">{tr('cut', 'corte', 'corte')}</span> : s.context_seconds > 0 ? <span className="shot-tag quiet" title={tr('Continues the previous shot', 'Continua o trecho anterior', 'Continúa el tramo anterior')}>+{s.context_seconds.toFixed(1)}s</span> : null}</figcaption>
    </figure>)}</div>
  </div>;
}
