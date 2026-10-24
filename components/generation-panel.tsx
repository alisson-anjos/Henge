'use client';
import {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';
import type {DirectionRequest} from '../lib/history';
import type {Picture} from '../lib/media';
import type {Language} from '../lib/design-copy';
import {isFixedRecipe, type Mode} from '../lib/prompt';
import {readJson} from '../lib/http';
import {jobStatusLabel,jobStageLabel} from '../lib/job-status';

type Plan = {summary: string; prompt: string; source_kind: string; target_kind: string; use_fibo: boolean; representation: string; preparation_reason?: string; preparation_recommended?: boolean; warnings: string[]; picture_roles: {slot: number; role: string; description: string}[]};
export type GenerationJob = {id: string; project: string; status: string; stage: string; message?: string; error?: string; progress: number; segment?: number; total_segments?: number; plan?: Plan; sampling_preview_url?: string; result_url?: string; comparison_url?: string; guide_preview_url?: string; fibo_preview_url?: string; created: number; step?: number; step_total?: number; eta_seconds?: number | null; prepared_reference_urls?: string[]; mask_preview_url?: string; seconds_per_step?: number | null};
type Health = {comfy_url?: string; online: boolean; training_busy: boolean; tara_ready?: boolean; fibo_ready: boolean; models: Record<string, {label: string; task?: string; available?: boolean}>; turbos?: Record<string, {label: string; steps: number; available: boolean}>; bases?: Record<string, {label: string; available: boolean}>};
const finished = ['completed', 'failed', 'cancelled', 'awaiting_approval'];
const formatEta = (seconds: number) => seconds >= 90 ? `${Math.floor(seconds / 60)}m ${String(Math.round(seconds % 60)).padStart(2, '0')}s` : `${Math.max(1, Math.round(seconds))}s`;
export default function GenerationPanel({initialSettings = {}, onShareSettings, onImportSettings, mode, request, video, pictures, canSubmit, lang, onResult, requestedJobId}: {initialSettings?: Record<string, unknown>; onShareSettings?: (options: Record<string, unknown>) => void; onImportSettings?: () => void; mode: Mode; request: DirectionRequest | null; video: File | null; pictures: Picture[]; canSubmit: boolean; lang: Language; onResult: (job: GenerationJob) => void; requestedJobId?: string | null}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [jobs, setJobs] = useState<GenerationJob[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [comfyUrl, setComfyUrl] = useState('');
  const [connectionMessage, setConnectionMessage] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [showReferenceComparison, setShowReferenceComparison] = useState(false);
  const [settingsTarget, setSettingsTarget] = useState<HTMLElement | null>(null);
  const [actionsTarget, setActionsTarget] = useState<HTMLElement | null>(null);
  useEffect(() => {setSettingsTarget(document.getElementById('generation-settings')); setActionsTarget(document.getElementById('prompt-generation-actions'));}, []);
  const [motionModel, setMotionModel] = useState(initialSettings.profile === 'motion_tara4500' ? 'motion_tara4500' : 'motion');
  const profile = mode === 'swap' ? 'character' : mode === 'motion' ? motionModel : mode;
  const [fibo, setFibo] = useState(initialSettings.fibo === 'off' ? 'off' : 'auto');
  const [conditioningMode, setConditioningMode] = useState(initialSettings.conditioning_mode === 'tara' ? 'tara' : 'guide');
  const fixedRecipe = isFixedRecipe(mode);
  const activeConditioning = conditioningMode;
  const [referenceScale, setReferenceScale] = useState(typeof initialSettings.reference_scale === 'number' ? Math.min(1,Math.max(.25,initialSettings.reference_scale)) : 1);
  const [seed, setSeed] = useState(typeof initialSettings.seed === 'number' ? Math.min(4294967295,Math.max(0,Math.round(initialSettings.seed))) : 42);
  const [steps, setSteps] = useState(typeof initialSettings.steps === 'number' ? Math.min(60,Math.max(1,Math.round(initialSettings.steps))) : 8);
  const [clipFps, setClipFps] = useState(typeof initialSettings.clip_fps === 'number' && [1,2,4,8].includes(initialSettings.clip_fps) ? initialSettings.clip_fps : 2);
  const [detectCuts, setDetectCuts] = useState(initialSettings.detect_cuts !== false);
  const [enhancePrompt, setEnhancePrompt] = useState(initialSettings.enhance_prompt !== false);
  const [autoApprove, setAutoApprove] = useState(initialSettings.auto_approve === true);
  const MASK_DEFAULTS = {threshold: .5, shape: 'box', padding: .15, expand: 16, fill_holes: true, temporal_expand: 2, blockify: 0, invert: false, strength: 1};
  const [maskSettings, setMaskSettings] = useState<typeof MASK_DEFAULTS>({...MASK_DEFAULTS, ...(typeof initialSettings.mask === 'object' && initialSettings.mask ? initialSettings.mask as Partial<typeof MASK_DEFAULTS> : {})});
  const usesMask = request?.subject_guidance?.representation === 'mask';
  const setMask = (patch: Partial<typeof MASK_DEFAULTS>) => setMaskSettings(current => ({...current, ...patch}));
  const [cfg, setCfg] = useState(typeof initialSettings.cfg === 'number' ? Math.min(12, Math.max(1, initialSettings.cfg)) : 1);
  const [base, setBase] = useState(initialSettings.base === 'omniref' ? 'omniref' : 'h3');
  const [turbo, setTurbo] = useState(typeof initialSettings.turbo === 'string' ? initialSettings.turbo : 'dmd8');
  const [prepareReferences, setPrepareReferences] = useState(initialSettings.prepare_references !== false);
  const [attention, setAttention] = useState(initialSettings.attention === 'pytorch attention' ? 'pytorch attention' : 'comfy kitchen attention');
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const job = jobs.find(j => j.id === selected) || null;
  useEffect(() => {setShowReferenceComparison(false);}, [selected]);
  useEffect(() => {
    let disposed = false, timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function refresh() {
      try {
        const [h, list] = await Promise.all([fetch('/api/backend/health', {signal: controller.signal}), fetch('/api/backend/jobs', {signal: controller.signal})]);
        if (!h.ok || !list.ok) throw Error();
        const state: Health = await h.json(), rows: GenerationJob[] = await list.json();
        if (!disposed) {setHealth(state); setComfyUrl(current => current || state.comfy_url || 'http://127.0.0.1:8189'); setJobs(rows); setSelected(current => current || rows[0]?.id || null);}
      } catch {if (!disposed) setHealth(null);}
      if (!disposed) timer = setTimeout(refresh, 3000);
    }
    refresh(); return () => {disposed = true; controller.abort(); clearTimeout(timer);};
  }, []);
  useEffect(() => {if (requestedJobId) setSelected(requestedJobId);}, [requestedJobId]);
  useEffect(() => {if (job) onResult(job);}, [job?.id, job?.status, job?.progress, job?.result_url, job?.message, job?.guide_preview_url, job?.fibo_preview_url, job?.sampling_preview_url]);
  async function submit() {
    if (!request || !video || !canSubmit || submitting) return;
    setError(''); setSubmitting(true);
    try {
      const body = new FormData(); body.set('direction', JSON.stringify(enhancePrompt ? request : {...request, prompt: request.editor_prompt})); body.set('options', JSON.stringify({profile, fibo, seed, steps, clip_fps: activeConditioning === 'tara' ? 2 : clipFps, conditioning_mode: activeConditioning, reference_scale: referenceScale, detect_cuts: detectCuts, enhance_prompt: enhancePrompt, auto_approve: autoApprove, attention, prepare_references: prepareReferences, base, cfg, ...(usesMask ? {mask: maskSettings} : {}), ...(mode === 'motion' ? {} : {turbo})})); body.set('video', video);
      pictures.forEach(p => body.set(`picture_${p.slot}`, p.file));
      const response = await fetch('/api/backend/jobs', {method: 'POST', body}); const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || result.error || 'Unable to create job');
      setJobs(current => [result, ...current]); setSelected(result.id);
    } catch (e) {setError(e instanceof Error ? e.message : 'Unable to submit');} finally {setSubmitting(false);}
  }
  async function saveConnection() {
    setConnecting(true); setConnectionMessage('');
    try {
      const response = await fetch('/api/backend/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({comfy_url: comfyUrl})});
      const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || 'Unable to connect');
      setConnectionMessage(tr('Connected. Settings saved.', 'Conectado. Configuração salva.', 'Conectado. Configuración guardada.'));
    } catch (e) {setConnectionMessage(e instanceof Error ? e.message : 'Unable to connect');} finally {setConnecting(false);}
  }
  async function setPreparation(enabled: boolean) {
    if (!job || submitting) return;
    setSubmitting(true); setError('');
    try {
      const response = await fetch(`/api/backend/jobs/${job.id}/preparation`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled})});
      const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || 'Unable to update reference preparation');
      setJobs(current => current.map(j => j.id === result.id ? result : j));
    } catch (e) {setError(e instanceof Error ? e.message : 'Unable to update preparation');} finally {setSubmitting(false);}
  }
  async function updateMaskPreview() {
    if (!job) return;
    setSubmitting(true); setError('');
    try {
      const response = await fetch(`/api/backend/jobs/${job.id}/mask-preview`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mask: maskSettings})});
      const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || 'Unable to update the mask preview');
      setJobs(current => current.map(j => j.id === result.id ? result : j));
    } catch (e) {setError(e instanceof Error ? e.message : 'Unable to update the mask preview');} finally {setSubmitting(false);}
  }
  async function action(name: 'approve' | 'cancel') {
    if (!job) return;
    setSubmitting(true); setError('');
    try {
      const response = await fetch(`/api/backend/jobs/${job.id}/${name}`, {method: 'POST'}); const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || result.error || 'Request failed');
      setJobs(current => current.map(j => j.id === result.id ? result : j));
    } catch (e) {setError(e instanceof Error ? e.message : 'Request failed');} finally {setSubmitting(false);}
  }
  const settings = <div className="generation-settings-content">
    <div className="label-row"><h2>{tr('Settings', 'Configurações', 'Configuración')}</h2><span className="mono muted">{health?.online ? health.training_busy ? tr('Waiting for training', 'GPU reservada ao treino', 'GPU reservada al entrenamiento') : 'ComfyUI online' : 'Backend offline'}</span></div>
    <details className="connection-settings"><summary>{tr('Connection settings', 'Configurar conexão', 'Configurar conexión')}</summary><label>{tr('ComfyUI API address', 'Endereço da API do ComfyUI', 'Dirección de la API de ComfyUI')}<input type="url" value={comfyUrl} placeholder="http://127.0.0.1:8189" onChange={e => setComfyUrl(e.target.value)}/></label><small>{tr('Use the address reachable by the Henge backend. Its configured ComfyUI folder must also be accessible there.', 'Use o endereço acessível pelo backend do Henge. A pasta do ComfyUI configurada no backend também precisa estar acessível.', 'Usa una dirección accesible desde el backend de Henge. Su carpeta de ComfyUI configurada también debe ser accesible.')}</small><button className="quiet-button" disabled={connecting} onClick={saveConnection}>{connecting ? tr('Connecting…', 'Conectando…', 'Conectando…') : tr('Test and save', 'Testar e salvar', 'Probar y guardar')}</button>{connectionMessage && <p role="status">{connectionMessage}</p>}</details>
    <div className="generation-setup">
      {fixedRecipe ? <div className="selected-model"><span className="control-label">{tr('Model', 'Modelo', 'Modelo')}</span><div><strong>{mode === 'headswap' ? 'Head Swap' : 'LMS Sharpness'}</strong><span className="model-version">{mode === 'headswap' ? 'v1.0 · r32' : 'v1 · fro dyn95'}</span></div><small>{tr('Turbo LoRA (DMD 8-step) applied', 'Turbo LoRA (DMD 8 passos) aplicado', 'Turbo LoRA (DMD 8 pasos) aplicado')}</small></div> : mode === 'swap' ? <div className="selected-model"><span className="control-label">{tr('Model', 'Modelo', 'Modelo')}</span><div><strong>Character Swap</strong><span className="model-version">v1.1</span></div><small>{tr('Selected automatically for this task', 'Selecionado automaticamente para esta tarefa', 'Seleccionado automáticamente para esta tarea')}</small></div> : <label className="motion-model-field"><span className="control-label">{tr('Model', 'Modelo', 'Modelo')}</span><select aria-label={tr('Motion model', 'Modelo de movimento', 'Modelo de movimiento')} value={motionModel} onChange={e => setMotionModel(e.target.value)}>{Object.entries(health?.models || {motion: {label: 'Original · 10500', task: 'motion'}, motion_tara4500: {label: 'TARA-trained · 4500', task: 'motion'}}).filter(([, m]) => m.task === 'motion').map(([id, m]) => <option key={id} value={id} disabled={'available' in m && m.available === false}>{m.label}{'available' in m && m.available === false ? tr(' · not installed', ' · não instalado', ' · no instalado') : ''}</option>)}</select><small>{tr('Choose which trained model to use', 'Escolha qual modelo treinado usar', 'Elige qué modelo entrenado usar')}</small></label>}
      <div className="method-field"><span className="control-label">{tr('Method', 'Método', 'Método')}</span><div className="method-toggle" role="group" aria-label={tr('Generation method', 'Método de geração', 'Método de generación')}><button aria-pressed={conditioningMode === 'guide'} className={conditioningMode === 'guide' ? 'selected' : ''} onClick={() => setConditioningMode('guide')}>Guide Latents</button><button aria-pressed={conditioningMode === 'tara'} className={conditioningMode === 'tara' ? 'selected' : ''} disabled={!health?.tara_ready} onClick={() => setConditioningMode('tara')}>TARA <small>experimental</small></button></div><small>{conditioningMode === 'guide' ? tr('Default · follows the guide video directly', 'Padrão · segue diretamente o vídeo guia', 'Predeterminado · sigue directamente el vídeo guía') : tr('Experimental · temporally aligned native reference', 'Experimental · referência nativa com alinhamento temporal', 'Experimental · referencia nativa con alineación temporal')}</small></div>
    </div>
    {!fixedRecipe && <label className="prompt-assist-row"><input type="checkbox" checked={enhancePrompt} onChange={e => setEnhancePrompt(e.target.checked)}/><span><strong>{tr('Improve my prompt', 'Aprimorar meu pedido', 'Mejorar mi petición')}</strong><small>{enhancePrompt ? tr('Uses the video and references to organize your edit.', 'Usa o vídeo e as referências para organizar sua edição.', 'Usa el vídeo y las referencias para organizar tu edición.') : tr('Uses your text exactly as written.', 'Usa seu texto exatamente como foi escrito.', 'Usa tu texto exactamente como está escrito.')}</small></span></label>}
    {mode !== 'sharpness' && <label className="prompt-assist-row"><input type="checkbox" checked={autoApprove} onChange={e => setAutoApprove(e.target.checked)}/><span><strong>{tr('Auto-approve plan', 'Aprovar plano automaticamente', 'Aprobar plan automáticamente')}</strong><small>{autoApprove ? tr('Generates right after planning, using the recommended reference preparation.', 'Gera logo após o planejamento, com a preparação de referência recomendada.', 'Genera justo después de planificar, con la preparación recomendada.') : tr('Pauses so you can review the plan before generating.', 'Pausa para você revisar o plano antes de gerar.', 'Se detiene para que revises el plan antes de generar.')}</small></span></label>}
    <details className="generation-advanced"><summary>{tr('Advanced', 'Avançado', 'Avanzado')}</summary><div className="generation-options">
      {conditioningMode === 'tara' && <label>{tr('Reference scale', 'Escala da referência', 'Escala de referencia')}<select value={referenceScale} onChange={e => setReferenceScale(Number(e.target.value))}>{[1, .75, .5].map(n => <option key={n} value={n}>{n}</option>)}</select></label>}
      <label>{tr('Prepare reference automatically', 'Preparar referência automaticamente', 'Preparar referencia automáticamente')}<input type="checkbox" checked={fibo === 'auto'} onChange={e => setFibo(e.target.checked ? 'auto' : 'off')}/><small>{tr('Suggest a compatible pose when the guide and reference have different anatomy.', 'Sugere uma pose compatível quando o guia e a referência têm anatomias diferentes.', 'Sugiere una pose compatible cuando la guía y la referencia tienen anatomías diferentes.')}</small></label>
      <label>Seed<input type="number" min="0" max="4294967295" value={seed} onChange={e => setSeed(Math.min(4294967295, Math.max(0, Math.round(Number(e.target.value) || 0))))}/></label>
      <label>Steps<input type="number" min="1" max="60" value={steps} onChange={e => setSteps(Math.min(60, Math.max(1, Math.round(Number(e.target.value) || 8))))}/></label>
      {mode === 'swap' && <label>{tr('Remove reference background', 'Remover fundo da referência', 'Quitar fondo de la referencia')}<input type="checkbox" checked={prepareReferences} onChange={e => setPrepareReferences(e.target.checked)}/></label>}
      <label>{tr('Base model', 'Modelo base', 'Modelo base')}<select value={base} onChange={e => {setBase(e.target.value); if (e.target.value === 'omniref' && mode !== 'motion') setTurbo('none');}}>{Object.entries(health?.bases || {h3: {label: 'MiniMax H3 ref2va', available: true}}).map(([id, item]) => <option key={id} value={id} disabled={!item.available}>{item.label}{item.available ? '' : tr(' · not installed', ' · não instalado', ' · no instalado')}</option>)}</select></label>
      {mode !== 'motion' && <label>Turbo LoRA<select value={turbo} onChange={e => {const next = e.target.value; setTurbo(next); if (next === 'none' && base === 'h3') {setSteps(30); setCfg(4);} else {const recommended = health?.turbos?.[next]?.steps; if (recommended) setSteps(recommended); setCfg(1);}}}>{Object.entries(health?.turbos || {dmd8: {label: 'DMD 8-step (drbaph)', steps: 8, available: true}}).map(([id, item]) => <option key={id} value={id} disabled={!item.available}>{item.label}{item.available ? '' : tr(' · not installed', ' · não instalado', ' · no instalado')}</option>)}</select></label>}
      {usesMask && <fieldset className="mask-settings"><legend>{tr('Latent mask', 'Máscara latente', 'Máscara latente')}</legend>
        <label>{tr('Region', 'Região', 'Región')}<select value={maskSettings.shape} onChange={e => setMask({shape: e.target.value})}><option value="box">{tr('Box around the subject (recommended)', 'Caixa em volta do personagem (recomendado)', 'Caja alrededor del personaje (recomendado)')}</option><option value="silhouette">{tr('Grown silhouette', 'Silhueta expandida', 'Silueta expandida')}</option></select></label>
        {maskSettings.shape === 'box' ? <label>{tr('Box padding', 'Margem da caixa', 'Margen de la caja')}<input type="number" min="0" max="1" step="0.05" value={maskSettings.padding} onChange={e => setMask({padding: Math.min(1, Math.max(0, Number(e.target.value) || 0))})}/></label>
          : <label>{tr('Expand (px)', 'Expandir (px)', 'Expandir (px)')}<input type="number" min="0" max="128" value={maskSettings.expand} onChange={e => setMask({expand: Math.min(128, Math.max(0, Number(e.target.value) || 0))})}/></label>}
        <label>{tr('Detection threshold', 'Limiar de detecção', 'Umbral de detección')}<input type="number" min="0.05" max="0.95" step="0.05" value={maskSettings.threshold} onChange={e => setMask({threshold: Math.min(.95, Math.max(.05, Number(e.target.value) || .5))})}/></label>
        <label>{tr('Temporal expand (frames)', 'Expansão temporal (frames)', 'Expansión temporal (frames)')}<input type="number" min="0" max="24" value={maskSettings.temporal_expand} onChange={e => setMask({temporal_expand: Math.min(24, Math.max(0, Math.round(Number(e.target.value) || 0)))})}/></label>
        <label>Blockify (px)<input type="number" min="0" max="64" value={maskSettings.blockify} onChange={e => setMask({blockify: Math.min(64, Math.max(0, Math.round(Number(e.target.value) || 0)))})}/></label>
        <label>{tr('Strength', 'Força', 'Fuerza')}<input type="number" min="0" max="1" step="0.05" value={maskSettings.strength} onChange={e => setMask({strength: Math.min(1, Math.max(0, Number(e.target.value) || 0))})}/></label>
        <label>{tr('Fill holes', 'Preencher buracos', 'Rellenar huecos')}<input type="checkbox" checked={maskSettings.fill_holes} onChange={e => setMask({fill_holes: e.target.checked})}/></label>
        <label>{tr('Invert (regenerate everything except the subject)', 'Inverter (regenera tudo menos o personagem)', 'Invertir (regenera todo menos el personaje)')}<input type="checkbox" checked={maskSettings.invert} onChange={e => setMask({invert: e.target.checked})}/></label>
        <button type="button" className="text-link" onClick={() => setMaskSettings(MASK_DEFAULTS)}>{tr('Reset to BFS planner defaults', 'Voltar aos padrões do planner BFS', 'Volver a los valores del planner BFS')}</button>
      </fieldset>}
      <label>CFG<input type="number" min="1" max="12" step="0.5" value={cfg} onChange={e => setCfg(Math.min(12, Math.max(1, Number(e.target.value) || 1)))}/></label>
      <label>{tr('Attention', 'Atenção', 'Atención')}<select value={attention} onChange={e => setAttention(e.target.value)}><option value="comfy kitchen attention">Comfy Kitchen (INT8)</option><option value="pytorch attention">PyTorch</option></select></label>
      <label>CLIP video FPS<select value={activeConditioning === 'tara' ? 2 : clipFps} disabled={activeConditioning === 'tara'} onChange={e => setClipFps(Number(e.target.value))}>{[1, 2, 4, 8].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
      <label>{tr('Detect camera cuts', 'Detectar cortes de câmera', 'Detectar cortes de cámara')}<input type="checkbox" checked={detectCuts} onChange={e => setDetectCuts(e.target.checked)}/></label>
    </div>{onImportSettings && <button className="quiet-button import-settings-button" onClick={onImportSettings}>{tr('Import settings', 'Importar configuração', 'Importar configuración')}</button>}</details>
  </div>;
  const shareOptions = {profile, fibo, seed, steps, clip_fps: clipFps, conditioning_mode: conditioningMode, reference_scale: referenceScale, detect_cuts: detectCuts, enhance_prompt: enhancePrompt, auto_approve: autoApprove, attention, turbo, prepare_references: prepareReferences, base, cfg, mask: maskSettings};
  const actions = <><button className="quiet-button export-settings-button" disabled={!canSubmit} title={tr('Share the prompt and settings; media is not included', 'Compartilhar o pedido e os ajustes, sem incluir as mídias', 'Compartir la petición y ajustes, sin archivos multimedia')} onClick={() => onShareSettings?.(shareOptions)}>{tr('Export', 'Exportar', 'Exportar')}</button><button className="primary" disabled={!health?.online || health?.models[profile]?.available === false || !canSubmit || submitting} onClick={submit}>{submitting ? tr('Sending…', 'Enviando…', 'Enviando…') : tr('Generate', 'Gerar', 'Generar')}</button></>;
  return <section className="generation-panel" aria-label={tr('Generation backend', 'Geração no backend', 'Generación en backend')}>
    {settingsTarget ? createPortal(settings, settingsTarget) : null}
    <p className="micro-copy">{tr('Your video and references are analyzed before generation. Review the plan and any recommended reference preparation.', 'O vídeo e as referências são analisados antes da geração. Revise o plano e a preparação recomendada.', 'El vídeo y las referencias se analizan antes de generar. Revisa el plan y la preparación recomendada.')}</p>
    {actionsTarget ? createPortal(actions, actionsTarget) : actions}

    {health?.training_busy && <p role="status">{tr('Jobs remain queued until the active training finishes. Training will not be interrupted.', 'Os pedidos aguardam o treino liberar a GPU. O treinamento não será interrompido.', 'Los pedidos esperan a que termine el entrenamiento. No se interrumpirá.')}</p>}
    {error && <p role="alert" className="validation">{error}</p>}

    {job && <article className="generation-job" aria-live="polite"><div className="label-row"><strong>{jobStatusLabel(job.status,lang)}{job.status === 'running' ? ' · '+jobStageLabel(job.stage,lang) : ''}</strong><span className="mono">{job.segment ? `${job.segment}/${job.total_segments}` : ''}</span></div><p>{job.error || job.message}{job.step_total ? ` · ${job.step}/${job.step_total}` : ''}{job.seconds_per_step && !finished.includes(job.status) ? ` · ${job.seconds_per_step >= 1 ? `${job.seconds_per_step.toFixed(1)} s/it` : `${(1 / job.seconds_per_step).toFixed(2)} it/s`}` : ''}{job.eta_seconds && !finished.includes(job.status) ? ` · ~${formatEta(job.eta_seconds)} ${tr('left', 'restantes', 'restantes')}` : ''}</p>{!finished.includes(job.status) && <progress max="1" value={job.progress}/>}
      {job.plan && <details open={job.status === 'awaiting_approval'}><summary>{tr('Execution plan', 'Plano de execução', 'Plan de ejecución')}</summary><p>{job.plan.summary}</p>{job.plan.preparation_recommended && <div className="preparation-recommendation"><strong>{tr('Reference adaptation recommended', 'Adaptação da referência recomendada', 'Adaptación de referencia recomendada')}</strong><p>{job.plan.source_kind === 'human' && job.plan.target_kind === 'animal' ? tr('Your guide shows a human performer and your reference depicts an animal. Would you like to prepare a version with a human-compatible posture while preserving the animal’s identity? This may help transfer the performance.', 'O vídeo guia mostra uma pessoa e a referência representa um animal. Deseja preparar uma versão com postura compatível com o corpo humano, preservando a identidade do animal? Essa adaptação pode ajudar na transferência do movimento.', 'La guía muestra una persona y la referencia representa un animal. ¿Quieres preparar una versión con postura compatible con el cuerpo humano, conservando la identidad del animal? Puede ayudar a transferir el movimiento.') : tr('The guide and reference may benefit from a compatible pose. You can adapt the reference or keep the original image.', 'Uma pose compatível pode ajudar a combinar o guia e a referência. Você pode adaptar a referência ou manter a imagem original.', 'Una pose compatible puede ayudar a combinar la guía y la referencia. Puedes adaptar la referencia o conservar la imagen original.')}</p>{job.status === 'awaiting_approval' && <div className="plan-actions"><button className={job.plan.use_fibo ? 'primary' : 'quiet-button'} disabled={submitting} aria-pressed={job.plan.use_fibo} onClick={() => setPreparation(true)}>{tr('Adapt reference', 'Adaptar referência', 'Adaptar referencia')}</button><button className={!job.plan.use_fibo ? 'primary' : 'quiet-button'} disabled={submitting} aria-pressed={!job.plan.use_fibo} onClick={() => setPreparation(false)}>{tr('Use original image', 'Usar imagem original', 'Usar imagen original')}</button></div>}<small>{job.plan.use_fibo ? tr('Adaptation enabled. Your original image is preserved.', 'Adaptação ativada. Sua imagem original será preservada.', 'Adaptación activada. Tu imagen original se conserva.') : tr('Original images will be used.', 'As imagens originais serão usadas.', 'Se usarán las imágenes originales.')}</small></div>}<ul>{job.plan.picture_roles.map(p => <li key={p.slot}>Picture {p.slot} · {p.role}: {p.description}</li>)}</ul>{job.plan.warnings.map((w, i) => <p key={i}>{w}</p>)}<details><summary>{tr('Full edit description', 'Descrição completa da edição', 'Descripción completa de la edición')}</summary><pre className="native-preview">{job.plan.prompt}</pre></details></details>}
      {job.mask_preview_url && <div className="mask-preview">
        <div className="label-row"><strong>{tr('Latent mask preview', 'Prévia da máscara latente', 'Vista previa de la máscara latente')}</strong><small className="muted">{tr('first shot', 'primeiro shot', 'primer plano')}</small></div>
        <video key={job.mask_preview_url} src={job.mask_preview_url} autoPlay loop muted playsInline/>
        <small className="muted">{tr('Only the highlighted area is regenerated; everything else stays exactly as in your video. Make sure it covers the whole person you want to replace.', 'Só a área destacada é regenerada; o resto fica igual ao seu vídeo. Confira se ela cobre a pessoa inteira que você quer trocar.', 'Solo el área resaltada se regenera; el resto queda igual que tu vídeo. Comprueba que cubre a toda la persona que quieres cambiar.')}</small>
        {job.status === 'awaiting_approval' && <div className="mask-preview-controls">
          <label>{tr('Region', 'Região', 'Región')}<select value={maskSettings.shape} onChange={e => setMask({shape: e.target.value})}><option value="box">{tr('Box around the person', 'Caixa em volta da pessoa', 'Caja alrededor de la persona')}</option><option value="silhouette">{tr('Person outline', 'Contorno da pessoa', 'Contorno de la persona')}</option></select></label>
          {maskSettings.shape === 'box' ? <label>{tr('Margin', 'Margem', 'Margen')} {Math.round(maskSettings.padding * 100)}%<input type="range" min="0" max="0.6" step="0.05" value={maskSettings.padding} onChange={e => setMask({padding: Number(e.target.value)})}/></label>
            : <label>{tr('Grow', 'Expandir', 'Expandir')} {maskSettings.expand}px<input type="range" min="0" max="64" step="4" value={maskSettings.expand} onChange={e => setMask({expand: Number(e.target.value)})}/></label>}
          <button className="quiet-button" disabled={submitting} onClick={updateMaskPreview}>{tr('Update preview', 'Atualizar prévia', 'Actualizar vista previa')}</button>
        </div>}
        <small className="muted">{tr('More options in Settings → Latent mask.', 'Mais opções em Configurações → Máscara latente.', 'Más opciones en Configuración → Máscara latente.')}</small>
      </div>}
      {job.prepared_reference_urls?.length ? <div className="prepared-references"><small className="muted">{tr('References sent to H3 (background removed, 0.5 MP)', 'Referências enviadas ao H3 (sem fundo, 0,5 MP)', 'Referencias enviadas a H3 (sin fondo, 0,5 MP)')}</small><div>{job.prepared_reference_urls.map((url, i) => <img key={url} src={url} alt={`Picture ${i + 1} prepared`}/>)}</div></div> : null}
      <div className="generation-actions">{job.status === 'awaiting_approval' && <button className="primary" disabled={submitting} onClick={() => action('approve')}>{tr('Generate video', 'Gerar vídeo', 'Generar vídeo')}</button>}{!['completed', 'failed', 'cancelled'].includes(job.status) && <button className="quiet-button" disabled={submitting} onClick={() => action('cancel')}>{tr('Cancel job', 'Cancelar pedido', 'Cancelar pedido')}</button>}
      {job.result_url && <a className="quiet-button" href={job.result_url} download="henge-result.mp4">{tr('Download video', 'Baixar vídeo', 'Descargar vídeo')}</a>}{job.comparison_url && <a className="quiet-button" href={job.comparison_url} download="henge-comparison.mp4">{tr('Download comparison', 'Baixar comparação', 'Descargar comparación')}</a>}{['completed', 'failed', 'cancelled'].includes(job.status) && (job.total_segments || job.result_url) ? <a className="quiet-button" href={`/api/backend/jobs/${job.id}/workflow?stage=h3_segment_000`} download title={tr('API-format graph that ran in ComfyUI. Drag the file into ComfyUI to open it.', 'Grafo (formato API) que rodou no ComfyUI. Arraste o arquivo para dentro do ComfyUI para abrir.', 'Grafo (formato API) que se ejecutó en ComfyUI. Arrastra el archivo a ComfyUI para abrirlo.')}>{tr('ComfyUI workflow', 'Workflow do ComfyUI', 'Workflow de ComfyUI')}</a> : null}{job.status === 'completed' && job.comparison_url && <a className="quiet-button" href={`/api/backend/jobs/${job.id}/comparison-with-refs`} download="henge-guide-result-references.mp4">{tr('Download comparison + references', 'Baixar comparação + referências', 'Descargar comparación + referencias')}</a>}</div>
      {job.result_url && <div className="finished-preview"><div className="finished-preview-modes" role="group" aria-label={tr('Result preview', 'Prévia do resultado', 'Vista previa del resultado')}><button aria-pressed={!showReferenceComparison} className={!showReferenceComparison ? 'selected' : ''} onClick={() => setShowReferenceComparison(false)}>{tr('Result', 'Resultado', 'Resultado')}</button>{job.comparison_url && <button aria-pressed={showReferenceComparison} className={showReferenceComparison ? 'selected' : ''} onClick={() => setShowReferenceComparison(true)}>{tr('Guide + result + references', 'Guia + resultado + referências', 'Guía + resultado + referencias')}</button>}</div><video key={job.id+String(showReferenceComparison)} controls playsInline preload="metadata" src={showReferenceComparison ? `/api/backend/jobs/${job.id}/comparison-with-refs` : job.result_url}/>{showReferenceComparison && <small>{tr('Preparing the comparison may take a few seconds on first viewing.', 'A comparação pode levar alguns segundos para ficar pronta na primeira visualização.', 'La comparación puede tardar unos segundos en la primera visualización.')}</small>}</div>}
      {job.comparison_url && <details><summary>{tr('Source / result comparison', 'Comparação guia / resultado', 'Comparación guía / resultado')}</summary><video controls playsInline src={job.comparison_url}/></details>}
      {job.fibo_preview_url && <img className="fibo-preview" src={job.fibo_preview_url} alt="FIBO prepared appearance and pose reference"/>}{job.guide_preview_url && <details><summary>{tr('Prepared guide', 'Guia preparado', 'Guía preparada')}</summary><video controls src={job.guide_preview_url}/></details>}
    </article>}
    {jobs.length > 0 && <div className="generation-jobs"><label>{tr('Server history', 'Histórico do servidor', 'Historial del servidor')}<select value={selected || ''} onChange={e => setSelected(e.target.value)}>{jobs.map(j => <option key={j.id} value={j.id}>{j.project} · {jobStatusLabel(j.status,lang)} · {new Date(j.created * 1000).toLocaleString()}</option>)}</select></label></div>}
  </section>;
}
