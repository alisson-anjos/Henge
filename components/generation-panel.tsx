'use client';
import {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';
import type {DirectionRequest} from '../lib/history';
import type {Picture} from '../lib/media';
import type {Language} from '../lib/design-copy';
import {isFixedRecipe, type Mode} from '../lib/prompt';
import {readJson} from '../lib/http';
import {jobStatusLabel,jobStageLabel,formatEta} from '../lib/job-status';
import ShotPlan, {ShotClip} from './shot-plan';
import FiboPrep from './fibo-prep';
import MarksPreview from './marks-preview';
import {readableError} from '../lib/job-error';
import Select from './select';
import JobPipeline from './job-pipeline';

type Plan = {summary: string; prompt: string; source_kind: string; target_kind: string; use_fibo: boolean; representation: string; preparation_reason?: string; preparation_recommended?: boolean; warnings: string[]; picture_roles: {slot: number; role: string; description: string}[]};
/** What the studio assistant can do in this panel. */
export type PanelControls = {submit: () => Promise<string>; setAutoApprove: (value: boolean) => void; setEnhancePrompt: (value: boolean) => void; selectJob: (id: string) => void;
  getOptions: () => Record<string, unknown>; applyOptions: (patch: Record<string, unknown>) => void};
export type GenerationJob = {id: string; project: string; redone_shots?: Record<string, number>; run_seconds?: number; run_started?: number; updated?: number; mode?: string; duration?: number; quality?: string; options?: Record<string, unknown>; status: string; stage: string; message?: string; error?: string; progress: number; segment?: number; total_segments?: number; plan?: Plan; sampling_preview_url?: string; result_url?: string; comparison_url?: string; guide_preview_url?: string; fibo_preview_url?: string; created: number; step?: number; step_total?: number; eta_seconds?: number | null; prepared_reference_urls?: string[]; shot_urls?: string[]; mask_preview_url?: string; likeness_warning?: string; marks_preview_url?: string; marks_source_url?: string; seconds_per_step?: number | null};
type Health = {comfy_url?: string; provider?: string; online: boolean; training_busy: boolean; tara_ready?: boolean; fibo_ready: boolean; frame_editor?: string | null; models: Record<string, {label: string; task?: string; available?: boolean; method?: string}>; turbos?: Record<string, {label: string; steps: number; available: boolean}>; upscalers?: {h3: boolean; nvidia: boolean}; bases?: Record<string, {label: string; available: boolean}>};
const relativeTime = (created: number, lang: Language) => {
  const minutes = Math.round((Date.now() / 1000 - created) / 60);
  if (minutes < 60) return new Intl.RelativeTimeFormat(lang, {numeric: 'auto'}).format(-minutes, 'minute');
  if (minutes < 60 * 24) return new Intl.RelativeTimeFormat(lang, {numeric: 'auto'}).format(-Math.round(minutes / 60), 'hour');
  return new Date(created * 1000).toLocaleDateString(lang);
};
const MASK_DEFAULTS = {threshold: .5, shape: 'box', padding: .15, expand: 16, fill_holes: true, temporal_expand: 2, blockify: 0, invert: false, strength: 1};
const SETTINGS_KEY = 'henge-generation-settings';
const SELECTED_KEY = 'henge-selected-job';
/** Generation options (as sent to the bridge, exported or stored with a job) -> panel control values. */
function normalizeSettings(o: Record<string, unknown>) {
  const num = (v: unknown, lo: number, hi: number, fallback: number, round = false) => typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, round ? Math.round(v) : v)) : fallback;
  return {
    motionModel: typeof o.profile === 'string' && o.profile.startsWith('motion') ? o.profile : 'motion',
    fibo: o.fibo === 'off' ? 'off' : 'auto',
    conditioningMode: o.conditioning_mode === 'tara' ? 'tara' : 'guide',
    // Default: the text encoder also sees the guide (Latents + CLIP), in every mode.
    guideClip: (['auto', 'off'].includes(o.guide_clip as string) ? o.guide_clip : 'on') as 'auto' | 'on' | 'off',
    referenceScale: num(o.reference_scale, .25, 1, 1),
    seed: num(o.seed, 0, 4294967295, 42, true),
    steps: num(o.steps, 1, 60, 8, true),
    clipFps: typeof o.clip_fps === 'number' && [1, 2, 4, 8].includes(o.clip_fps) ? o.clip_fps : 2,
    enhancePrompt: o.enhance_prompt !== false,
    autoApprove: o.auto_approve === true,
    mask: {...MASK_DEFAULTS, ...(typeof o.mask === 'object' && o.mask ? o.mask as Partial<typeof MASK_DEFAULTS> : {})},
    cfg: num(o.cfg, 1, 12, 1),
    structureCfg: num(o.structure_cfg, 1, 3, 1),
    base: o.base === 'omniref' ? 'omniref' : 'h3',
    loraStrength: num(o.lora_strength, 0, 2, 1),
    upscaleMethod: (['h3', 'nvidia', 'none'] as const).find(m => m === o.upscale_method) ?? (o.latent_upscale === false ? 'none' : 'h3'),
    upscaleSteps: num(o.upscale_steps, 1, 8, 1),
    upscaleDenoise: num(o.upscale_denoise, 0, 1, .15),
    turbo: typeof o.turbo === 'string' ? o.turbo : 'dmd8',
    prepareReferences: o.prepare_references !== false,
    attention: o.attention === 'pytorch attention' ? 'pytorch attention' : 'comfy kitchen attention',
  };
}
export default function GenerationPanel({onEnhanceChange, registerControls, freshRevision = 0, initialSettings = {}, onSelectJob, onShareSettings, onImportSettings, mode, request, video, pictures, background, canSubmit, lang, onResult, requestedJobId, requestedProfile}: {background?: File | null; onEnhanceChange?: (on: boolean) => void; registerControls?: (controls: PanelControls) => void; freshRevision?: number; initialSettings?: Record<string, unknown>; onSelectJob?: (request: DirectionRequest, jobId: string) => void; onShareSettings?: (options: Record<string, unknown>) => void; onImportSettings?: () => void; mode: Mode; request: DirectionRequest | null; video: File | null; pictures: Picture[]; canSubmit: boolean; lang: Language; onResult: (job: GenerationJob) => void; requestedJobId?: string | null; requestedProfile?: string | null}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [jobs, setJobs] = useState<GenerationJob[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [showReferenceComparison, setShowReferenceComparison] = useState(false);
  const [settingsTarget, setSettingsTarget] = useState<HTMLElement | null>(null);
  const [actionsTarget, setActionsTarget] = useState<HTMLElement | null>(null);
  useEffect(() => {setSettingsTarget(document.getElementById('generation-settings')); setActionsTarget(document.getElementById('prompt-generation-actions'));}, []);
  const [initial] = useState(() => normalizeSettings(initialSettings));
  const [motionModel, setMotionModel] = useState(initial.motionModel);
  const profile = mode === 'swap' ? 'character' : mode === 'motion' ? motionModel : mode;
  const [fibo, setFibo] = useState(initial.fibo);
  const [conditioningMode, setConditioningMode] = useState(initial.conditioningMode);
  // Whether the text encoder (Qwen-VL) also sees guide frames with the prompt; auto = the model's default.
  const [guideClip, setGuideClip] = useState(initial.guideClip);
  const fixedRecipe = isFixedRecipe(mode);
  // Sharpness follows the source video with Guide Latents: no TARA there.
  const activeConditioning = mode === 'sharpness' ? 'guide' : conditioningMode;
  const taraWithMarks = activeConditioning === 'tara' && ['2d', '3d'].includes(request?.subject_guidance?.representation || '') && !!request?.subject_guidance?.bindings?.length;
  const [referenceScale, setReferenceScale] = useState(initial.referenceScale);
  const [seed, setSeed] = useState(initial.seed);
  const [steps, setSteps] = useState(initial.steps);
  const [clipFps, setClipFps] = useState(initial.clipFps);
  const [enhancePrompt, setEnhancePrompt] = useState(initial.enhancePrompt);
  const [autoApprove, setAutoApprove] = useState(initial.autoApprove);
  const [maskSettings, setMaskSettings] = useState<typeof MASK_DEFAULTS>(initial.mask);
  const usesMask = request?.subject_guidance?.representation === 'mask';
  const setMask = (patch: Partial<typeof MASK_DEFAULTS>) => setMaskSettings(current => ({...current, ...patch}));
  const [cfg, setCfg] = useState(initial.cfg);
  const [structureCfg, setStructureCfg] = useState(initial.structureCfg);
  const [base, setBase] = useState(initial.base);
  const [loraStrength, setLoraStrength] = useState(initial.loraStrength);
  const [upscaleMethod, setUpscaleMethod] = useState<'h3' | 'nvidia' | 'none'>(initial.upscaleMethod);
  const [upscaleSteps, setUpscaleSteps] = useState(initial.upscaleSteps);
  const [upscaleDenoise, setUpscaleDenoise] = useState(initial.upscaleDenoise);
  const [turbo, setTurbo] = useState(initial.turbo);
  const [prepareReferences, setPrepareReferences] = useState(initial.prepareReferences);
  const [attention, setAttention] = useState(initial.attention);
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const job = jobs.find(j => j.id === selected) || null;
  function applySettings(options: Record<string, unknown>) {
    const n = normalizeSettings(options);
    setMotionModel(n.motionModel); setFibo(n.fibo); setConditioningMode(n.conditioningMode); setGuideClip(n.guideClip); setReferenceScale(n.referenceScale); setSeed(n.seed); setSteps(n.steps);
    setClipFps(n.clipFps); setEnhancePrompt(n.enhancePrompt); setAutoApprove(n.autoApprove); setMaskSettings(n.mask); setCfg(n.cfg);
    setStructureCfg(n.structureCfg); setBase(n.base); setLoraStrength(n.loraStrength); setUpscaleMethod(n.upscaleMethod); setUpscaleSteps(n.upscaleSteps); setUpscaleDenoise(n.upscaleDenoise);
    setTurbo(n.turbo); setPrepareReferences(n.prepareReferences); setAttention(n.attention);
  }
  const modeLabel = (m: string) => ({swap: tr('Character Swap', 'Troca de personagem', 'Cambio de personaje'), motion: tr('Motion Transfer', 'Transferência de movimento', 'Transferencia de movimiento'), headswap: 'Head Swap', sharpness: tr('Sharpness', 'Nitidez', 'Nitidez')} as Record<string, string>)[m] || m;
  /** Model, turbo, method and sampling of a job, compactly, for the history list. */
  function jobDetails(j: GenerationJob) {
    const o = j.options || {};
    const model = typeof o.profile === 'string' && j.mode === 'motion' ? health?.models[o.profile]?.label || o.profile : '';
    const turbo = typeof o.turbo === 'string' ? (o.turbo === 'none' ? tr('no turbo', 'sem turbo', 'sin turbo') : o.turbo.toUpperCase()) : '';
    const method = o.conditioning_mode === 'tara' ? `TARA${typeof o.structure_cfg === 'number' && o.structure_cfg > 1 ? ` ×${o.structure_cfg}` : ''}` : '';
    return [model, turbo, method, typeof o.steps === 'number' ? `${o.steps} steps` : '', o.base === 'omniref' ? 'OmniRef' : '', j.quality || ''].filter(Boolean) as string[];
  }
  /** Selecting a job brings back everything it was made with: generation options here, the direction in the studio. */
  async function selectJob(id: string) {
    const ref = id.trim().toLowerCase().replace(/^#/, '');
    const matches = jobs.filter(j => j.id === ref || (ref.length === 8 && j.id.startsWith(ref)));
    const resolved = matches.length === 1 ? matches[0].id : id;
    setSelected(resolved);
    try {
      const detail = await readJson(await fetch(`/api/backend/jobs/${resolved}`));
      if (detail.options && typeof detail.options === 'object') applySettings(detail.options);
      if (detail.request && typeof detail.request === 'object') onSelectJob?.(detail.request, resolved);
    } catch {/* the job stays selected; its settings just are not restored */}
  }
  // Settings survive reloads; an imported configuration (initialSettings) wins over the stored one.
  const [restored, setRestored] = useState(false);
  useEffect(() => {
    if (!Object.keys(initialSettings).length) {
      try {const stored = JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null'); if (stored && typeof stored === 'object') applySettings(stored);} catch {/* private mode */}
    }
    setRestored(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {setShowReferenceComparison(false); if (selected) try {localStorage.setItem(SELECTED_KEY, selected);} catch {/* private mode */}}, [selected]);
  useEffect(() => {
    let disposed = false, first = true, timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function refresh() {
      try {
        const [h, list] = await Promise.all([fetch('/api/backend/health', {signal: controller.signal}), fetch('/api/backend/jobs', {signal: controller.signal})]);
        if (!h.ok || !list.ok) throw Error();
        const state: Health = await h.json(), rows: GenerationJob[] = await list.json();
        if (!disposed) {setHealth(state); rows.sort((a, b) => b.created - a.created); setJobs(rows); if (first) {first = false; let stored: string | null = null; try {stored = localStorage.getItem(SELECTED_KEY);} catch {/* private mode */} const initial = rows.find(r => r.id === stored)?.id; if (initial) selectJob(initial);}}
      } catch {if (!disposed) setHealth(null);}
      if (!disposed) timer = setTimeout(refresh, 3000);
    }
    refresh(); return () => {disposed = true; controller.abort(); clearTimeout(timer);};
  }, []);
  useEffect(() => {if (requestedJobId) setSelected(requestedJobId);}, [requestedJobId]);
  // A new guide video: show no previous job until one is chosen from the history.
  useEffect(() => {if (!freshRevision) return; setSelected(null); try {localStorage.removeItem(SELECTED_KEY);} catch {/* private mode */}}, [freshRevision]);
  useEffect(() => {if (requestedProfile) setMotionModel(requestedProfile);}, [requestedProfile]);
  useEffect(() => {if (job) onResult(job);}, [job?.id, job?.status, job?.progress, job?.result_url, job?.message, job?.guide_preview_url, job?.fibo_preview_url, job?.sampling_preview_url]);
  async function submit(): Promise<string> {
    if (!request || !video || !canSubmit || submitting) throw Error(!video ? 'Attach a guide video first' : !canSubmit ? 'The studio is not ready: check the pictures, marks and prompt' : 'A generation is being sent');
    setError(''); setSubmitting(true);
    try {
      const body = new FormData(); body.set('direction', JSON.stringify(enhancePrompt ? request : {...request, prompt: request.editor_prompt})); body.set('options', JSON.stringify({profile, fibo, seed, steps, clip_fps: activeConditioning === 'tara' ? 2 : clipFps, conditioning_mode: activeConditioning, guide_clip: guideClip, reference_scale: referenceScale, enhance_prompt: enhancePrompt, auto_approve: autoApprove, attention, prepare_references: prepareReferences, base, cfg, ...(activeConditioning === 'tara' ? {structure_cfg: structureCfg} : {}), ...(usesMask ? {mask: maskSettings} : {}), turbo,...(mode === 'sharpness' ? {lora_strength: loraStrength, upscale_method: upscaleMethod, upscale_steps: upscaleSteps, upscale_denoise: upscaleDenoise} : {})})); body.set('video', video); if (background) body.set('background', background);
      pictures.forEach(p => body.set(`picture_${p.slot}`, p.file));
      const response = await fetch('/api/backend/jobs', {method: 'POST', body}); const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || result.error || 'Unable to create job');
      setJobs(current => [result, ...current]); setSelected(result.id);
      return result.id as string;
    } catch (e) {setError(e instanceof Error ? e.message : 'Unable to submit'); throw e;} finally {setSubmitting(false);}
  }
  useEffect(() => {onEnhanceChange?.(enhancePrompt);}, [enhancePrompt]);
  // The assistant always calls the latest closures (they read this render's request and options).
  useEffect(() => {registerControls?.({submit, setAutoApprove, setEnhancePrompt, selectJob: id => void selectJob(id),
    getOptions: () => ({options: {...shareOptions, profile}, models: health?.models, turbos: health?.turbos, bases: health?.bases, upscalers: health?.upscalers, tara_ready: health?.tara_ready}),
    applyOptions: patch => applySettings({...shareOptions, profile, ...patch})});});
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
  async function redoShot(n: number) {
    if (!job) return;
    setSubmitting(true); setError('');
    try {
      const response = await fetch(`/api/backend/jobs/${job.id}/shots/${n}/redo`, {method: 'POST', headers: {'content-type': 'application/json'}, body: '{}'});
      const result = await readJson(response); if (!response.ok) throw Error(result.detail || 'Unable to redo the shot');
      setJobs(current => current.map(j => j.id === result.id ? result : j));
    } catch (e) {setError(e instanceof Error ? e.message : 'Unable to redo the shot');} finally {setSubmitting(false);}
  }
  async function action(name: 'approve' | 'cancel' | 'retry') {
    if (!job) return;
    setSubmitting(true); setError('');
    try {
      const response = await fetch(`/api/backend/jobs/${job.id}/${name}`, {method: 'POST'}); const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || result.error || 'Request failed');
      setJobs(current => current.map(j => j.id === result.id ? result : j));
    } catch (e) {setError(e instanceof Error ? e.message : 'Request failed');} finally {setSubmitting(false);}
  }
  /** The base models that run for the current mode and options (not LoRAs, turbos or guidance methods). */
  const engines: {name: string; role: string}[] = [
    ...(mode === 'sharpness' ? [] : [{name: 'Qwen3.5 9B', role: tr('plans the edit', 'planeja a edição', 'planifica la edición')}]),
    ...((mode === 'swap' || mode === 'motion') && prepareReferences ? [{name: 'BiRefNet', role: tr('reference background', 'fundo da referência', 'fondo de la referencia')}] : []),
    ...((mode === 'swap' || mode === 'motion') && fibo === 'auto' && health?.fibo_ready ? [{name: ({klein3: 'FLUX.3 Klein', klein: 'FLUX.2 Klein', fibo: 'FIBO 2'} as Record<string, string>)[health.frame_editor ?? 'fibo'] ?? 'FIBO 2', role: tr('reference adaptation', 'adaptação da referência', 'adaptación de la referencia')}] : []),
    ...(usesMask ? [{name: 'SAM 3.1', role: tr('subject mask', 'máscara do personagem', 'máscara del personaje')}] : []),
    ...(mode === 'sharpness' && upscaleMethod === 'nvidia' ? [{name: 'NVIDIA RTX VSR', role: tr('2K/4K upscale', 'upscale 2K/4K', 'escalado 2K/4K')}] : []),
    {name: base === 'omniref' && mode !== 'sharpness' ? 'MiniMax H3 OmniRef' : 'MiniMax H3', role: tr('video generation', 'geração do vídeo', 'generación del vídeo')},
  ];
  const settings = <div className="generation-settings-content">
    <div className="label-row"><h2>{tr('Settings', 'Configurações', 'Configuración')}</h2><span className="mono muted">{health?.online ? health.training_busy ? tr('Waiting for training', 'GPU reservada ao treino', 'GPU reservada al entrenamiento') : ({runpod: 'RunPod Serverless online', comfy_sdk: 'Comfy API online'} as Record<string, string>)[health.provider ?? ''] ?? 'ComfyUI online' : 'Backend offline'}</span></div>
    <button type="button" className="quiet-button connection-open" onClick={() => dispatchEvent(new CustomEvent('henge:open-settings', {detail: 'connection'}))}>{tr('Connection settings', 'Configurar conexão', 'Configurar conexión')} →</button>
    <div className="generation-setup">
      {fixedRecipe ? <div className="selected-model"><span className="control-label">{tr('Model', 'Modelo', 'Modelo')}</span><div><strong>{mode === 'headswap' ? 'Head Swap' : 'Little More Sharpness'}</strong><span className="model-version">{mode === 'headswap' ? 'v1.0 · r32' : 'H3 · LMS v1 dyn95'}</span></div>{mode === 'sharpness' ? <small>{tr('The source video guides it frame by frame', 'O vídeo de origem guia quadro a quadro', 'El vídeo de origen lo guía fotograma a fotograma')}</small> : <small>{tr('Turbo LoRA (DMD 8-step) applied', 'Turbo LoRA (DMD 8 passos) aplicado', 'Turbo LoRA (DMD 8 pasos) aplicado')}</small>}</div> : mode === 'swap' ? <div className="selected-model"><span className="control-label">{tr('Model', 'Modelo', 'Modelo')}</span><div><strong>Character Swap</strong><span className="model-version">v1.1</span></div><small>{tr('Selected automatically for this task', 'Selecionado automaticamente para esta tarefa', 'Seleccionado automáticamente para esta tarea')}</small></div> : <label className="motion-model-field"><span className="control-label">{tr('Model', 'Modelo', 'Modelo')}</span><Select aria-label={tr('Motion model', 'Modelo de movimento', 'Modelo de movimiento')} value={motionModel} onChange={e => {const next = e.target.value; const was = health?.models[motionModel]?.method; const method = health?.models[next]?.method; setMotionModel(next); if (method === 'tara' && health?.tara_ready) setConditioningMode('tara'); else if (was === 'tara' && !method) setConditioningMode('guide');}}>{Object.entries(health?.models || {motion: {label: 'Motion Transfer v1.0', task: 'motion'}}).filter(([, m]) => m.task === 'motion').map(([id, m]) => <option key={id} value={id} disabled={'available' in m && m.available === false}>{m.label}{'available' in m && m.available === false ? tr(' · not installed', ' · não instalado', ' · no instalado') : ''}</option>)}</Select><small>{tr('Choose which trained model to use', 'Escolha qual modelo treinado usar', 'Elige qué modelo entrenado usar')}</small></label>}
      {mode !== 'sharpness' && <div className="method-field"><span className="control-label">{tr('Method', 'Método', 'Método')}</span><div className="method-toggle" role="group" aria-label={tr('Generation method', 'Método de geração', 'Método de generación')}><button aria-pressed={conditioningMode === 'guide'} className={conditioningMode === 'guide' ? 'selected' : ''} onClick={() => setConditioningMode('guide')}>Guide Latents</button><button aria-pressed={conditioningMode === 'tara'} className={conditioningMode === 'tara' ? 'selected' : ''} disabled={!health?.tara_ready} onClick={() => setConditioningMode('tara')}>TARA <small>experimental</small></button></div><small>{conditioningMode === 'guide' ? tr('Default · follows the guide video directly', 'Padrão · segue diretamente o vídeo guia', 'Predeterminado · sigue directamente el vídeo guía') : tr('Experimental · temporally aligned native reference', 'Experimental · referência nativa com alinhamento temporal', 'Experimental · referencia nativa con alineación temporal')}</small></div>}
      {activeConditioning === 'guide' && <div className="method-field"><span className="control-label">{tr('Guide for the text encoder', 'Guia para o text encoder', 'Guía para el codificador de texto')}</span><div className="method-toggle" role="group" aria-label={tr('Guide for the text encoder', 'Guia para o text encoder', 'Guía para el codificador de texto')}>{(['on', 'off', 'auto'] as const).map(v => <button key={v} aria-pressed={guideClip === v} className={guideClip === v ? 'selected' : ''} onClick={() => setGuideClip(v)}>{v === 'auto' ? 'Auto' : v === 'off' ? tr('Latents only', 'Só latents', 'Solo latents') : 'Latents + CLIP'}{v === 'on' && <small> · {tr('default', 'padrão', 'predeterminado')}</small>}</button>)}</div><small>{guideClip === 'off' ? tr('The guide enters only as VAE latents in the conditioning: the model traces it frame by frame; the text encoder never sees the original person.', 'O guia entra só como latents do VAE no conditioning: o modelo traça frame a frame; o text encoder nunca vê a pessoa original.', 'La guía entra solo como latents del VAE: el modelo la calca cuadro a cuadro; el codificador de texto no ve a la persona original.') : guideClip === 'on' ? tr('Latents, plus guide frames shown to the text encoder (Qwen-VL) with the prompt: it understands the action better, but clothes or hair of the original person can leak.', 'Latents, mais frames do guia mostrados ao text encoder (Qwen-VL) junto com o prompt: entende melhor a ação, mas roupa ou cabelo da pessoa original podem vazar.', 'Latents, más cuadros de la guía para el codificador (Qwen-VL) con el prompt: entiende mejor la acción, pero ropa o pelo del original pueden filtrarse.') : tr('The model default: Motion Transfer uses latents + CLIP; Character Swap, Head Swap and Sharpness use latents only, so the original person does not leak.', 'Padrão do modelo: Motion Transfer usa latents + CLIP; Character Swap, Head Swap e Sharpness usam só latents, para a pessoa original não vazar.', 'Predeterminado: Motion Transfer usa latents + CLIP; Character Swap, Head Swap y Sharpness solo latents, para que no se filtre la persona original.')}</small></div>}
    </div>
    <div className="engines" aria-label={tr('Models used', 'Modelos usados', 'Modelos usados')}><span className="control-label">{tr('Models used', 'Modelos usados', 'Modelos usados')}</span><ol>{engines.map((e, i) => <li key={e.name + e.role}><span className="mono">{i + 1}</span><small>{e.role}</small><strong>{e.name}</strong></li>)}</ol></div>
    {mode !== 'sharpness' && <label className="prompt-assist-row"><input type="checkbox" checked={autoApprove} onChange={e => setAutoApprove(e.target.checked)}/><span><strong>{tr('Auto-approve plan', 'Aprovar plano automaticamente', 'Aprobar plan automáticamente')}</strong><small>{autoApprove ? tr('Generates right after planning, using the recommended reference preparation.', 'Gera logo após o planejamento, com a preparação de referência recomendada.', 'Genera justo después de planificar, con la preparación recomendada.') : tr('Pauses so you can review the plan before generating.', 'Pausa para você revisar o plano antes de gerar.', 'Se detiene para que revises el plan antes de generar.')}</small></span></label>}
    <details className="generation-advanced"><summary>{tr('Advanced', 'Avançado', 'Avanzado')}</summary><div className="generation-options">
      {conditioningMode === 'tara' && <label>{tr('Reference scale', 'Escala da referência', 'Escala de referencia')}<Select value={referenceScale} onChange={e => setReferenceScale(Number(e.target.value))}>{[1, .75, .5].map(n => <option key={n} value={n}>{n}</option>)}</Select></label>}
      {activeConditioning === 'tara' && ['2d', '3d'].includes(request?.subject_guidance?.representation || '') && !!request?.subject_guidance?.bindings?.length && <p className="validation" role="alert">{tr('TARA was trained without color marks. Use the Original or Mask guide with TARA, or switch to Guide Latents for 2D/3D marks.', 'O TARA foi treinado sem marcações de cor. Use o guia Original ou Mask com o TARA, ou troque para Guide Latents para marcações 2D/3D.', 'TARA se entrenó sin marcas de color. Usa la guía Original o Mask con TARA, o cambia a Guide Latents para marcas 2D/3D.')}</p>}
      {conditioningMode === 'tara' && <label>{tr('TARA structure guidance (1 = off · ~1.5 follows Video 1 more, 2× slower)', 'Structure guidance do TARA (1 = desligado · ~1,5 segue mais o Video 1, 2× mais lento)', 'Structure guidance de TARA (1 = apagado · ~1,5 sigue más el Video 1, 2× más lento)')}<Select value={structureCfg} onChange={e => setStructureCfg(Number(e.target.value))}>{[1, 1.25, 1.5, 2].map(n => <option key={n} value={n}>{n}</option>)}</Select></label>}
      {health?.fibo_ready && (mode === 'swap' || mode === 'motion') && <label>{tr('Prepare reference automatically', 'Preparar referência automaticamente', 'Preparar referencia automáticamente')}<input type="checkbox" checked={fibo === 'auto'} onChange={e => setFibo(e.target.checked ? 'auto' : 'off')}/><small>{tr('Suggest a compatible pose when the guide and reference have different anatomy.', 'Sugere uma pose compatível quando o guia e a referência têm anatomias diferentes.', 'Sugiere una pose compatible cuando la guía y la referencia tienen anatomías diferentes.')}</small></label>}
      <label>Seed<input type="number" min="0" max="4294967295" value={seed} onChange={e => setSeed(Math.min(4294967295, Math.max(0, Math.round(Number(e.target.value) || 0))))}/></label>
      <label>Steps<input type="number" min="1" max="60" value={steps} onChange={e => setSteps(Math.min(60, Math.max(1, Math.round(Number(e.target.value) || 8))))}/></label>
      {(mode === 'swap' || mode === 'motion') && <label>{tr('Remove reference background', 'Remover fundo da referência', 'Quitar fondo de la referencia')}<input type="checkbox" checked={prepareReferences} onChange={e => setPrepareReferences(e.target.checked)}/></label>}
      {mode !== 'sharpness' && <label>{tr('Base model', 'Modelo base', 'Modelo base')}<Select value={base} onChange={e => {setBase(e.target.value); if (e.target.value === 'omniref') setTurbo('none');}}>{Object.entries(health?.bases || {h3: {label: 'MiniMax H3 ref2va', available: true}}).map(([id, item]) => <option key={id} value={id} disabled={!item.available}>{item.label}{item.available ? '' : tr(' · not installed', ' · não instalado', ' · no instalado')}</option>)}</Select></label>}
      {<label>Turbo LoRA<Select value={turbo} onChange={e => {const next = e.target.value; setTurbo(next); if (next === 'none' && base === 'h3') {setSteps(30); setCfg(4);} else {const recommended = health?.turbos?.[next]?.steps; if (recommended) setSteps(recommended); setCfg(1);}}}>{Object.entries(health?.turbos || {dmd8: {label: 'DMD 8-step (drbaph)', steps: 8, available: true}}).map(([id, item]) => <option key={id} value={id} disabled={!item.available}>{item.label}{item.available ? '' : tr(' · not installed', ' · não instalado', ' · no instalado')}</option>)}</Select></label>}
      {usesMask && <fieldset className="mask-settings"><legend>{tr('Latent mask', 'Máscara latente', 'Máscara latente')}</legend>
        <label>{tr('Region', 'Região', 'Región')}<Select value={maskSettings.shape} onChange={e => setMask({shape: e.target.value})}><option value="box">{tr('Box around the subject (recommended)', 'Caixa em volta do personagem (recomendado)', 'Caja alrededor del personaje (recomendado)')}</option><option value="silhouette">{tr('Grown silhouette', 'Silhueta expandida', 'Silueta expandida')}</option></Select></label>
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
      {mode === 'sharpness' && <fieldset className="mask-settings"><legend>{tr('Sharpness', 'Nitidez', 'Nitidez')}</legend>
        <label>{tr('Sharpness strength (LoRA, 1.0 recommended)', 'Força do sharpness (LoRA, 1,0 recomendado)', 'Fuerza de nitidez (LoRA, 1,0 recomendado)')}<input type="number" min="0" max="2" step="0.05" value={loraStrength} onChange={e => setLoraStrength(Math.min(2, Math.max(0, Number(e.target.value) || 0)))}/></label>
        <label>{tr('2K/4K upscale (sharpens at half size, then doubles it)', 'Upscale 2K/4K (deixa nítido em meia resolução e depois dobra)', 'Escalado 2K/4K (da nitidez a media resolución y luego duplica)')}<Select value={upscaleMethod} onChange={e => setUpscaleMethod(e.target.value as 'h3' | 'nvidia' | 'none')}>
          <option value="h3" disabled={health?.upscalers?.h3 === false}>{tr('H3 · latent upscaler + short refine', 'H3 · upscaler latente + refino curto', 'H3 · upscaler latente + refinado corto')}{health?.upscalers?.h3 === false ? tr(' · not installed', ' · não instalado', ' · no instalado') : ''}</option>
          <option value="nvidia" disabled={health?.upscalers?.nvidia === false}>{tr('NVIDIA RTX Video Super Resolution · fast, no new detail', 'NVIDIA RTX Video Super Resolution · rápido, sem detalhe novo', 'NVIDIA RTX Video Super Resolution · rápido, sin detalle nuevo')}{health?.upscalers?.nvidia === false ? tr(' · not installed', ' · não instalado', ' · no instalado') : ''}</option>
          <option value="none">{tr('None · sharpen directly at the output size (slower)', 'Nenhum · nitidez direto no tamanho final (mais lento)', 'Ninguno · nitidez directa al tamaño final (más lento)')}</option></Select></label>
        {upscaleMethod === 'h3' && <><label>{tr('Refine steps', 'Passos do refino', 'Pasos del refinado')}<input type="number" min="1" max="8" value={upscaleSteps} onChange={e => setUpscaleSteps(Math.min(8, Math.max(1, Math.round(Number(e.target.value) || 1))))}/></label>
        <label>{tr('Refine denoise (0 = upscaler only, higher = more invented detail)', 'Denoise do refino (0 = só o upscaler, maior = mais detalhe inventado)', 'Denoise del refinado (0 = solo el upscaler, mayor = más detalle inventado)')}<input type="number" min="0" max="1" step="0.05" value={upscaleDenoise} onChange={e => setUpscaleDenoise(Math.min(1, Math.max(0, Number(e.target.value) || 0)))}/></label></>}
      </fieldset>}
      {mode !== 'sharpness' && <label>CFG<input type="number" min="1" max="12" step="0.5" value={cfg} onChange={e => setCfg(Math.min(12, Math.max(1, Number(e.target.value) || 1)))}/></label>}
      {mode !== 'sharpness' && <label>{tr('Attention', 'Atenção', 'Atención')}<Select value={attention} onChange={e => setAttention(e.target.value)}><option value="comfy kitchen attention">Comfy Kitchen (INT8)</option><option value="pytorch attention">PyTorch</option></Select></label>}
      {mode !== 'sharpness' && <label>CLIP video FPS<Select value={activeConditioning === 'tara' ? 2 : clipFps} disabled={activeConditioning === 'tara'} onChange={e => setClipFps(Number(e.target.value))}>{[1, 2, 4, 8].map(n => <option key={n} value={n}>{n}</option>)}</Select></label>}
    </div>{onImportSettings && <button className="quiet-button import-settings-button" onClick={onImportSettings}>{tr('Import settings', 'Importar configuração', 'Importar configuración')}</button>}</details>
  </div>;
  const shareOptions = {profile, fibo, seed, steps, clip_fps: clipFps, conditioning_mode: conditioningMode, guide_clip: guideClip, reference_scale: referenceScale, enhance_prompt: enhancePrompt, auto_approve: autoApprove, attention, turbo, prepare_references: prepareReferences, base, cfg, structure_cfg: structureCfg, mask: maskSettings, lora_strength: loraStrength, upscale_method: upscaleMethod, upscale_steps: upscaleSteps, upscale_denoise: upscaleDenoise};
  const storedOptions = JSON.stringify(shareOptions);
  useEffect(() => {if (restored) try {localStorage.setItem(SETTINGS_KEY, storedOptions);} catch {/* private mode */}}, [restored, storedOptions]);
  const actions = <><button className="quiet-button export-settings-button" disabled={!canSubmit} title={tr('Share the prompt and settings; media is not included', 'Compartilhar o pedido e os ajustes, sem incluir as mídias', 'Compartir la petición y ajustes, sin archivos multimedia')} onClick={() => onShareSettings?.(shareOptions)}>{tr('Export', 'Exportar', 'Exportar')}</button>{job && !['completed', 'failed', 'cancelled'].includes(job.status) && <button className="quiet-button" disabled={submitting} onClick={() => action('cancel')}>{tr('Cancel job', 'Cancelar pedido', 'Cancelar pedido')}</button>}<button className="primary" disabled={!health?.online || health?.models[profile]?.available === false || !canSubmit || submitting || taraWithMarks} onClick={() => {submit().catch(() => {});}}>{submitting ? tr('Sending…', 'Enviando…', 'Enviando…') : tr('Generate', 'Gerar', 'Generar')}</button></>;
  return <section className="generation-panel" aria-label={tr('Generation backend', 'Geração no backend', 'Generación en backend')}>
    {settingsTarget ? createPortal(settings, settingsTarget) : null}
    <p className="micro-copy">{tr('Your video and references are analyzed before generation. Review the plan and any recommended reference preparation.', 'O vídeo e as referências são analisados antes da geração. Revise o plano e a preparação recomendada.', 'El vídeo y las referencias se analizan antes de generar. Revisa el plan y la preparación recomendada.')}</p>
    {actionsTarget ? createPortal(actions, actionsTarget) : actions}

    {health?.training_busy && <p role="status">{tr('Jobs remain queued until the active training finishes. Training will not be interrupted.', 'Os pedidos aguardam o treino liberar a GPU. O treinamento não será interrompido.', 'Los pedidos esperan a que termine el entrenamiento. No se interrumpirá.')}</p>}
    {error && <p role="alert" className="validation">{error}</p>}

    {job && <article className={'generation-job status-' + job.status} aria-live="polite">
      <header className="job-head"><span className={'job-pill ' + job.status}><i aria-hidden="true"/>{jobStatusLabel(job.status, lang)}</span><span className="mono">#{job.id.slice(0, 8)}</span>{job.run_seconds ? <span className="mono muted">⏱ {formatEta(job.run_seconds)}</span> : null}</header>
      {job.likeness_warning && <p className="likeness-warning" role="alert">{job.likeness_warning}</p>}
      <JobPipeline job={job} lang={lang}/>
      {job.error ? <div className="job-callout error" role="alert"><strong>{tr('What happened', 'O que aconteceu', 'Qué pasó')}</strong><p>{readableError(job.error).summary}</p>
        <small>{tr('Retry runs it again from where it stopped. If it fails the same way, download the ComfyUI workflow to inspect it.', 'Tentar de novo roda outra vez a partir de onde parou. Se falhar igual, baixe o workflow do ComfyUI para investigar.', 'Reintentar lo ejecuta otra vez desde donde se detuvo. Si falla igual, descarga el workflow de ComfyUI para revisarlo.')}</small>
        {readableError(job.error).detail !== readableError(job.error).summary && <details><summary>{tr('Technical details', 'Detalhes técnicos', 'Detalles técnicos')}</summary><pre>{job.error}</pre></details>}</div>
        : job.message && !['completed', 'awaiting_approval'].includes(job.status) ? <p className="job-message">{job.message}</p> : null}
      {job.plan && <details className="job-section" open={job.status === 'awaiting_approval'}><summary>{tr('What the AI understood', 'O que a IA entendeu', 'Lo que entendió la IA')}{job.plan.use_fibo && <span className="job-chip on" title={tr('An adapted reference (pose matched to the guide) was sent to generation.', 'Uma referência adaptada (pose ajustada ao guia) foi enviada para a geração.', 'Se envió una referencia adaptada (pose ajustada a la guía).')}>{tr('Adapted reference used', 'Referência adaptada usada', 'Referencia adaptada usada')}</span>}</summary><p className="plan-summary">{job.plan.summary}</p>{job.plan.preparation_recommended && <div className="preparation-recommendation"><strong>{tr('Reference adaptation recommended', 'Adaptação da referência recomendada', 'Adaptación de referencia recomendada')}</strong><p>{job.plan.source_kind === 'human' && job.plan.target_kind === 'animal' ? tr('Your guide shows a human performer and your reference depicts an animal. Would you like to prepare a version with a human-compatible posture while preserving the animal’s identity? This may help transfer the performance.', 'O vídeo guia mostra uma pessoa e a referência representa um animal. Deseja preparar uma versão com postura compatível com o corpo humano, preservando a identidade do animal? Essa adaptação pode ajudar na transferência do movimento.', 'La guía muestra una persona y la referencia representa un animal. ¿Quieres preparar una versión con postura compatible con el cuerpo humano, conservando la identidad del animal? Puede ayudar a transferir el movimiento.') : tr('The guide and reference may benefit from a compatible pose. You can adapt the reference or keep the original image.', 'Uma pose compatível pode ajudar a combinar o guia e a referência. Você pode adaptar a referência ou manter a imagem original.', 'Una pose compatible puede ayudar a combinar la guía y la referencia. Puedes adaptar la referencia o conservar la imagen original.')}</p>{job.status === 'awaiting_approval' && <div className="plan-actions"><button className={job.plan.use_fibo ? 'primary' : 'quiet-button'} disabled={submitting} aria-pressed={job.plan.use_fibo} onClick={() => setPreparation(true)}>{tr('Adapt reference', 'Adaptar referência', 'Adaptar referencia')}</button><button className={!job.plan.use_fibo ? 'primary' : 'quiet-button'} disabled={submitting} aria-pressed={!job.plan.use_fibo} onClick={() => setPreparation(false)}>{tr('Use original image', 'Usar imagem original', 'Usar imagen original')}</button></div>}<small>{job.plan.use_fibo ? tr('Adaptation enabled. Your original image is preserved.', 'Adaptação ativada. Sua imagem original será preservada.', 'Adaptación activada. Tu imagen original se conserva.') : tr('Original images will be used.', 'As imagens originais serão usadas.', 'Se usarán las imágenes originales.')}</small></div>}{job.status === 'awaiting_approval' && job.plan.use_fibo && <FiboPrep key={`${job.id}-fibo`} jobId={job.id} lang={lang}/>}<ul className="plan-roles">{job.plan.picture_roles.map((p, i) => <li key={p.slot}>{job.prepared_reference_urls?.[i] ? <img src={job.prepared_reference_urls[i]} alt=""/> : <span className="plan-role-slot">{p.slot}</span>}<div><strong>Picture {p.slot} <span className="muted">· {p.role}</span></strong><p>{p.description}</p></div></li>)}</ul>{job.plan.warnings.map((w, i) => <p key={i} className="job-callout warn">{w}</p>)}<details><summary>{tr('Full edit description', 'Descrição completa da edição', 'Descripción completa de la edición')}</summary><pre className="native-preview">{job.plan.prompt}</pre></details></details>}
      {job.plan?.use_fibo && job.fibo_preview_url && <figure className="job-fibo"><img className="fibo-preview" src={job.fibo_preview_url} alt={tr('Adapted reference', 'Referência adaptada', 'Referencia adaptada')}/><figcaption className="muted">{tr('Adapted reference sent to generation', 'Referência adaptada enviada para a geração', 'Referencia adaptada enviada a la generación')}</figcaption></figure>}
      {job.marks_preview_url && job.marks_source_url && <MarksPreview key={job.marks_preview_url} jobId={job.id} sourceUrl={job.marks_source_url} marksUrl={job.marks_preview_url} initial={request?.subject_guidance?.mark_opacity ?? 0.35} editable={job.status === 'awaiting_approval'} lang={lang}/>}
      {job.mask_preview_url && <div className="mask-preview">
        <div className="label-row"><strong>{tr('Latent mask preview', 'Prévia da máscara latente', 'Vista previa de la máscara latente')}</strong><small className="muted">{tr('first shot', 'primeiro shot', 'primer plano')}</small></div>
        <video key={job.mask_preview_url} src={job.mask_preview_url} autoPlay loop muted playsInline/>
        <small className="muted">{tr('Only the highlighted area is regenerated; everything else stays exactly as in your video. Make sure it covers the whole person you want to replace.', 'Só a área destacada é regenerada; o resto fica igual ao seu vídeo. Confira se ela cobre a pessoa inteira que você quer trocar.', 'Solo el área resaltada se regenera; el resto queda igual que tu vídeo. Comprueba que cubre a toda la persona que quieres cambiar.')}</small>
        {job.status === 'awaiting_approval' && <div className="mask-preview-controls">
          <label>{tr('Region', 'Região', 'Región')}<Select value={maskSettings.shape} onChange={e => setMask({shape: e.target.value})}><option value="box">{tr('Box around the person', 'Caixa em volta da pessoa', 'Caja alrededor de la persona')}</option><option value="silhouette">{tr('Person outline', 'Contorno da pessoa', 'Contorno de la persona')}</option></Select></label>
          {maskSettings.shape === 'box' ? <label>{tr('Margin', 'Margem', 'Margen')} {Math.round(maskSettings.padding * 100)}%<input type="range" min="0" max="0.6" step="0.05" value={maskSettings.padding} onChange={e => setMask({padding: Number(e.target.value)})}/></label>
            : <label>{tr('Grow', 'Expandir', 'Expandir')} {maskSettings.expand}px<input type="range" min="0" max="64" step="4" value={maskSettings.expand} onChange={e => setMask({expand: Number(e.target.value)})}/></label>}
          <button className="quiet-button" disabled={submitting} onClick={updateMaskPreview}>{tr('Update preview', 'Atualizar prévia', 'Actualizar vista previa')}</button>
        </div>}
        <small className="muted">{tr('More options in Settings → Latent mask.', 'Mais opções em Configurações → Máscara latente.', 'Más opciones en Configuración → Máscara latente.')}</small>
      </div>}
      {job.prepared_reference_urls?.length ? <div className="prepared-references job-section-plain"><strong className="job-subhead">{tr('Pictures sent to the model', 'Imagens enviadas ao modelo', 'Imágenes enviadas al modelo')}<small className="muted"> · {tr('background removed, 0.5 MP', 'sem fundo, 0,5 MP', 'sin fondo, 0,5 MP')}</small></strong><div>{job.prepared_reference_urls.map((url, i) => <img key={url} src={url} alt={`Picture ${i + 1} prepared`}/>)}</div></div> : null}
      {job.status === 'awaiting_approval' ? <ShotPlan jobId={job.id} editable lang={lang}/> : ['queued_render', 'running'].includes(job.status) && job.plan ? <details><summary>{tr('Guide shots', 'Trechos do guia', 'Tramos de la guía')}</summary><ShotPlan jobId={job.id} editable={false} lang={lang}/></details> : null}
      {job.shot_urls?.length && (job.total_segments || 0) > 1 ? <div className="shot-strip"><div className="label-row"><small className="muted">{tr('Finished shots', 'Trechos prontos', 'Tramos listos')} · {job.shot_urls.length}/{job.total_segments}</small><a className="quiet-button" href={`/api/backend/jobs/${job.id}/shots.zip`} download>{tr('Download all (zip)', 'Baixar todos (zip)', 'Descargar todos (zip)')}</a></div>
        <div>{job.shot_urls.map((url, i) => <figure key={url}><ShotClip src={url} label={`${tr('Play shot', 'Tocar trecho', 'Reproducir tramo')} ${i + 1}`}/><figcaption><span className="mono">{tr('shot', 'trecho', 'tramo')} {i + 1}</span><a href={url} download aria-label={`${tr('Download shot', 'Baixar trecho', 'Descargar tramo')} ${i + 1}`}>↓</a>{['completed', 'failed'].includes(job.status) && <button type="button" className="shot-redo" disabled={submitting} title={tr('Render this shot again with a new seed; the other shots are kept', 'Gerar este trecho de novo com outra seed; os outros trechos ficam', 'Generar este tramo de nuevo con otra seed; los demás se mantienen')} aria-label={`${tr('Redo shot', 'Refazer trecho', 'Rehacer tramo')} ${i + 1}`} onClick={() => redoShot(i + 1)}>↻</button>}{job.redone_shots?.[String(i + 1)] !== undefined && <span className="shot-tag quiet" title={`seed ${job.redone_shots[String(i + 1)]}`}>{tr('redone', 'refeito', 'rehecho')}</span>}</figcaption></figure>)}</div></div> : null}
      <div className="generation-actions">{job.status === 'awaiting_approval' && <button className="primary" disabled={submitting} onClick={() => action('approve')}>{tr('Generate video', 'Gerar vídeo', 'Generar vídeo')}</button>}
      {['failed', 'cancelled'].includes(job.status) && <button className="primary" disabled={submitting} onClick={() => action('retry')}>{tr('Retry', 'Tentar de novo', 'Reintentar')}</button>}
      {['failed', 'cancelled'].includes(job.status) && job.total_segments ? <a className="quiet-button" href={`/api/backend/jobs/${job.id}/workflow?stage=h3_segment_000`} download title={tr('API-format graph that ran in ComfyUI. Drag the file into ComfyUI to open it.', 'Grafo (formato API) que rodou no ComfyUI. Arraste o arquivo para dentro do ComfyUI para abrir.', 'Grafo (formato API) que se ejecutó en ComfyUI. Arrastra el archivo a ComfyUI para abrirlo.')}>{tr('ComfyUI workflow', 'Workflow do ComfyUI', 'Workflow de ComfyUI')}</a> : null}</div>
      {job.result_url && <div className="finished-preview"><div className="finished-preview-modes" role="group" aria-label={tr('Result preview', 'Prévia do resultado', 'Vista previa del resultado')}><button aria-pressed={!showReferenceComparison} className={!showReferenceComparison ? 'selected' : ''} onClick={() => setShowReferenceComparison(false)}>{tr('Result', 'Resultado', 'Resultado')}</button>{job.comparison_url && <button aria-pressed={showReferenceComparison} className={showReferenceComparison ? 'selected' : ''} onClick={() => setShowReferenceComparison(true)}>{tr('Guide + result + references', 'Guia + resultado + referências', 'Guía + resultado + referencias')}</button>}</div><video key={job.id+String(showReferenceComparison)} controls playsInline preload="metadata" src={showReferenceComparison ? `/api/backend/jobs/${job.id}/comparison-with-refs` : job.result_url}/>{showReferenceComparison && <small>{tr('Preparing the comparison may take a few seconds on first viewing.', 'A comparação pode levar alguns segundos para ficar pronta na primeira visualização.', 'La comparación puede tardar unos segundos en la primera visualización.')}</small>}</div>}
      {job.comparison_url && <details><summary>{tr('Source / result comparison', 'Comparação guia / resultado', 'Comparación guía / resultado')}</summary><video controls playsInline src={job.comparison_url}/></details>}
      {job.fibo_preview_url && <img className="fibo-preview" src={job.fibo_preview_url} alt="FIBO prepared appearance and pose reference"/>}{job.guide_preview_url && <details className="prepared-guide"><summary>{job.plan?.representation === 'mask' ? tr('Guide with the mask', 'Guia com a máscara', 'Guía con la máscara') : ['2d', '3d'].includes(job.plan?.representation || '') ? tr('Guide with the color marks', 'Guia com as marcações de cor', 'Guía con las marcas de color') : tr('Prepared guide', 'Guia preparado', 'Guía preparada')}</summary><video controls src={job.guide_preview_url}/><a className="quiet-button" href={job.guide_preview_url} download={`henge-${job.id.slice(0, 8)}-guide.mp4`}>{tr('Download guide video', 'Baixar vídeo do guia', 'Descargar vídeo de la guía')}</a>{job.status !== 'completed' && <small className="muted">{tr('First shot so far; the whole guide is joined when the job finishes.', 'Por enquanto só o primeiro shot; o guia inteiro é montado ao terminar.', 'Por ahora solo el primer plano; la guía completa se une al terminar.')}</small>}</details>}
    </article>}
  </section>;
}
