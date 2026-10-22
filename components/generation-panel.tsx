'use client';
import {useEffect, useState} from 'react';
import type {DirectionRequest} from '../lib/history';
import type {Picture} from '../lib/media';
import type {Language} from '../lib/design-copy';

type Plan = {summary: string; prompt: string; source_kind: string; target_kind: string; use_fibo: boolean; representation: string; warnings: string[]; picture_roles: {slot: number; role: string; description: string}[]};
export type GenerationJob = {id: string; project: string; status: string; stage: string; message?: string; error?: string; progress: number; segment?: number; total_segments?: number; plan?: Plan; result_url?: string; comparison_url?: string; guide_preview_url?: string; fibo_preview_url?: string; created: number; step?: number; step_total?: number};
type Health = {online: boolean; training_busy: boolean; fibo_ready: boolean; models: Record<string, {label: string}>};
const finished = ['completed', 'failed', 'cancelled', 'awaiting_approval'];
export default function GenerationPanel({request, video, pictures, canSubmit, lang, onResult, requestedJobId}: {request: DirectionRequest | null; video: File | null; pictures: Picture[]; canSubmit: boolean; lang: Language; onResult: (job: GenerationJob) => void; requestedJobId?: string | null}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [jobs, setJobs] = useState<GenerationJob[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [profile, setProfile] = useState('motion');
  const [fibo, setFibo] = useState('auto');
  const [seed, setSeed] = useState(42);
  const [steps, setSteps] = useState(8);
  const [clipFps, setClipFps] = useState(2);
  const [detectCuts, setDetectCuts] = useState(true);
  const [enhancePrompt, setEnhancePrompt] = useState(true);
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const job = jobs.find(j => j.id === selected) || null;
  useEffect(() => {
    let disposed = false, timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function refresh() {
      try {
        const [h, list] = await Promise.all([fetch('/api/backend/health', {signal: controller.signal}), fetch('/api/backend/jobs', {signal: controller.signal})]);
        if (!h.ok || !list.ok) throw Error();
        const state: Health = await h.json(), rows: GenerationJob[] = await list.json();
        if (!disposed) {setHealth(state); setJobs(rows); setSelected(current => current || rows[0]?.id || null);}
      } catch {if (!disposed) setHealth(null);}
      if (!disposed) timer = setTimeout(refresh, 3000);
    }
    refresh(); return () => {disposed = true; controller.abort(); clearTimeout(timer);};
  }, []);
  useEffect(() => {if (requestedJobId) setSelected(requestedJobId);}, [requestedJobId]);
  useEffect(() => {if (job) onResult(job);}, [job?.id, job?.status, job?.progress, job?.result_url, job?.message, job?.guide_preview_url, job?.fibo_preview_url]);
  async function submit() {
    if (!request || !video || !canSubmit || submitting) return;
    setError(''); setSubmitting(true);
    try {
      const body = new FormData(); body.set('direction', JSON.stringify(enhancePrompt ? request : {...request, prompt: request.editor_prompt})); body.set('options', JSON.stringify({profile, fibo, seed, steps, clip_fps: clipFps, detect_cuts: detectCuts, enhance_prompt: enhancePrompt})); body.set('video', video);
      pictures.forEach(p => body.set(`picture_${p.slot}`, p.file));
      const response = await fetch('/api/backend/jobs', {method: 'POST', body}); const result = await response.json();
      if (!response.ok) throw Error(result.detail || result.error || 'Unable to create job');
      setJobs(current => [result, ...current]); setSelected(result.id);
    } catch (e) {setError(e instanceof Error ? e.message : 'Unable to submit');} finally {setSubmitting(false);}
  }
  async function action(name: 'approve' | 'cancel') {
    if (!job) return;
    setSubmitting(true); setError('');
    try {
      const response = await fetch(`/api/backend/jobs/${job.id}/${name}`, {method: 'POST'}); const result = await response.json();
      if (!response.ok) throw Error(result.detail || result.error || 'Request failed');
      setJobs(current => current.map(j => j.id === result.id ? result : j));
    } catch (e) {setError(e instanceof Error ? e.message : 'Request failed');} finally {setSubmitting(false);}
  }
  return <section className="generation-panel surface" aria-label={tr('Generation backend', 'Geração no backend', 'Generación en backend')}>
    <div className="label-row"><h2>{tr('Generate with Kagemane', 'Gerar com Kagemane', 'Generar con Kagemane')}</h2><span className="mono muted">{health?.online ? health.training_busy ? tr('Waiting for training', 'GPU reservada ao treino', 'GPU reservada al entrenamiento') : 'ComfyUI online' : 'Backend offline'}</span></div>
    <div className="generation-options">
      <label>{tr('Video model', 'Modelo de vídeo', 'Modelo de vídeo')}<select value={profile} onChange={e => setProfile(e.target.value)}>{Object.entries(health?.models || {motion: {label: 'Motion transfer · checkpoint 8000'}, character: {label: 'Character Swap v1.1'}, mix50: {label: 'Character Swap 50/50 Dyn95'}}).map(([id, m]) => <option key={id} value={id}>{m.label}</option>)}</select></label>
      <label>FIBO 2.0 Edit<select value={fibo} onChange={e => setFibo(e.target.value)}><option value="auto">{tr('Automatic · VLM decision', 'Automático · decisão do VLM', 'Automático · decisión del VLM')}</option><option value="on">{tr('Prepare image', 'Preparar imagem', 'Preparar imagen')}</option><option value="off">{tr('Off', 'Desativado', 'Desactivado')}</option></select></label>
      <label>Enhance prompt<input type="checkbox" checked={enhancePrompt} onChange={e => setEnhancePrompt(e.target.checked)}/><small>{tr('On: adapt to H3. Off: send your exact text.', 'Ligado: adaptar ao H3. Desligado: enviar seu texto exato.', 'Activado: adaptar a H3. Desactivado: enviar tu texto exacto.')}</small></label>
      <label>Seed<input type="number" min="0" max="4294967295" value={seed} onChange={e => setSeed(Math.min(4294967295, Math.max(0, Math.round(Number(e.target.value) || 0))))}/></label>
      <label>Steps<input type="number" min="1" max="60" value={steps} onChange={e => setSteps(Math.min(60, Math.max(1, Math.round(Number(e.target.value) || 8))))}/></label>
      <label>CLIP video FPS<select value={clipFps} onChange={e => setClipFps(Number(e.target.value))}>{[1, 2, 4, 8].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
      <label>{tr('Detect camera cuts', 'Detectar cortes de câmera', 'Detectar cortes de cámara')}<input type="checkbox" checked={detectCuts} onChange={e => setDetectCuts(e.target.checked)}/></label>
    </div>
    <p className="micro-copy">{tr('The VLM reads your guide, references and direction. Review its plan, then generate. Species changes can add a FIBO appearance/pose image; this is not full skeletal retargeting.', 'O VLM lê guia, referências e intenção. Revise o plano e gere. Mudanças de espécie podem incluir uma imagem de aparência/pose com FIBO; isso não é retargeting completo do esqueleto.', 'El VLM analiza guía, referencias e intención. Revisa el plan y genera. Cambios de especie pueden añadir una imagen de apariencia/pose con FIBO; no es retargeting completo del esqueleto.')}</p>
    <button className="primary" disabled={!health?.online || !canSubmit || submitting} onClick={submit}>{submitting ? tr('Sending…', 'Enviando…', 'Enviando…') : tr('Upload and plan', 'Enviar e planejar', 'Enviar y planificar')}</button>
    {health?.training_busy && <p role="status">{tr('Jobs remain queued until the active training finishes. Training will not be interrupted.', 'Os pedidos aguardam o treino liberar a GPU. O treinamento não será interrompido.', 'Los pedidos esperan a que termine el entrenamiento. No se interrumpirá.')}</p>}
    {error && <p role="alert" className="validation">{error}</p>}
    {jobs.length > 0 && <div className="generation-jobs"><label>{tr('Server history', 'Histórico do servidor', 'Historial del servidor')}<select value={selected || ''} onChange={e => setSelected(e.target.value)}>{jobs.map(j => <option key={j.id} value={j.id}>{j.project} · {j.status} · {new Date(j.created * 1000).toLocaleString()}</option>)}</select></label></div>}
    {job && <article className="generation-job" aria-live="polite"><div className="label-row"><strong>{job.status} · {job.stage}</strong><span className="mono">{job.segment ? `${job.segment}/${job.total_segments}` : ''}</span></div><p>{job.error || job.message}{job.step_total ? ` · ${job.step}/${job.step_total}` : ''}</p>{!finished.includes(job.status) && <progress max="1" value={job.progress}/>}
      {job.plan && <details open={job.status === 'awaiting_approval'}><summary>{tr('Execution plan', 'Plano de execução', 'Plan de ejecución')}</summary><p>{job.plan.summary}</p><p className="mono">{job.plan.source_kind} → {job.plan.target_kind} · {job.plan.use_fibo ? 'FIBO Edit → ' : ''}{job.plan.representation} → H3</p><ul>{job.plan.picture_roles.map(p => <li key={p.slot}>Picture {p.slot} · {p.role}: {p.description}</li>)}</ul>{job.plan.warnings.map((w, i) => <p key={i}>{w}</p>)}<details><summary>H3 prompt</summary><pre className="native-preview">{job.plan.prompt}</pre></details></details>}
      <div className="generation-actions">{job.status === 'awaiting_approval' && <button className="primary" disabled={submitting} onClick={() => action('approve')}>{tr('Generate this plan', 'Gerar este plano', 'Generar este plan')}</button>}{!['completed', 'failed', 'cancelled'].includes(job.status) && <button className="quiet-button" disabled={submitting} onClick={() => action('cancel')}>{tr('Cancel job', 'Cancelar pedido', 'Cancelar pedido')}</button>}
      {job.result_url && <a className="quiet-button" href={job.result_url} download="kagemane-result.mp4">{tr('Download video', 'Baixar vídeo', 'Descargar vídeo')}</a>}{job.comparison_url && <a className="quiet-button" href={job.comparison_url} download="kagemane-comparison.mp4">{tr('Download comparison', 'Baixar comparação', 'Descargar comparación')}</a>}<a className="text-link" href={`/api/backend/jobs/${job.id}/workflow`} target="_blank" rel="noreferrer">Workflow JSON</a></div>
      {job.result_url && <video controls playsInline src={job.result_url}/>}
      {job.comparison_url && <details><summary>{tr('Source / result comparison', 'Comparação guia / resultado', 'Comparación guía / resultado')}</summary><video controls playsInline src={job.comparison_url}/></details>}
      {job.fibo_preview_url && <img className="fibo-preview" src={job.fibo_preview_url} alt="FIBO prepared appearance and pose reference"/>}{job.guide_preview_url && <details><summary>{tr('Prepared guide', 'Guia preparado', 'Guía preparada')}</summary><video controls src={job.guide_preview_url}/></details>}
    </article>}
  </section>;
}
