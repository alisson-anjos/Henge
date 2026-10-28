'use client';

import {useEffect, useRef, useState, type CSSProperties} from 'react';
import {MAX_PICTURES, nativePrompt, invalidReferences, isFixedRecipe, type Mode} from '../lib/prompt';
import {imageData, videoFrames, type Picture} from '../lib/media';
import {DESIGN_COPY, type Language} from '../lib/design-copy';
import {TEMPLATES} from '../lib/templates';
import {downloadJSON, FEEDBACK, HISTORY_KEY, HISTORY_LIMIT, readHistory, type DirectionRequest, type SavedDirection} from '../lib/history';
import VideoTrimModal, {type ClipRange} from './video-trim-modal';
import {COMMUNITY, type CommunityPreset} from '../lib/community';
import FirstFrameModal, {coverFit} from './first-frame-modal';
const FIRST_FRAME_KEY = 'henge-first-frame';
import GenerationPanel, {type GenerationJob, type PanelControls} from './generation-panel';
import AssistantPanel, {type StudioCall, type StudioController, type StudioResult} from './assistant-panel';
import {annotated, captureFrame, drawGrid, drawPoint, thumbnail} from '../lib/frame-capture';
import {readableError} from '../lib/job-error';
import JobProgress from './job-progress';
import {readJson} from '../lib/http';
import {jobStatusLabel} from '../lib/job-status';
import SubjectBindings, {SubjectVideo} from './subject-bindings';
import {SUBJECT_COLORS, bindingPrompt, readSubjectBindings, type SubjectBinding, type GuideRepresentation} from '../lib/subject-bindings';
import SetupScreen from './setup-screen';
import AccessSettings from './access-settings';
import ThemeSwitcher from './theme-switcher';
import {DialogHost, confirmDialog} from './dialog';
import SettingsCenter, {SETUP_KEY} from './settings-center';
import {cutModeLabel, type CutMode} from './shot-plan';
import Select from './select';

function Icon({name, size = 20}: {name: string; size?: number}) {
  const paths: Record<string, React.ReactNode> = {
    plus: <path d="M12 5v14M5 12h14"/>, arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
    film: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 4v16M17 4v16M3 9h4m10 0h4M3 15h4m10 0h4"/></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1"/><path d="m3 17 5-5 4 4 4-6 5 7"/></>,
    swap: <path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>,
    motion: <path d="M3 12h4l3-8 4 16 3-8h4"/>,
    headswap: <><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/><path d="m16 4 3-2m0 4h3"/></>,
    sharpness: <><path d="M12 2 4 12l8 10 8-10z"/><path d="M12 2v20M4 12h16"/></>,
    spark: <path d="M12 2v20M2 12h20M5 5l14 14M19 5 5 19"/>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    download: <path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>,
    upload: <path d="M12 16V4M7 9l5-5 5 5M4 16v4h16v-4"/>,
    code: <path d="m8 7-5 5 5 5m8-10 5 5-5 5M14 4l-4 16"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    scissors: <><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8 16M14 14l6 6M8 8l4 4"/></>,
    trash: <><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.5 10.5 7-4M8.5 13.5l7 4"/></>,
    github: <path d="M9 19c-4 1.5-4-2-6-2.5M15 22v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V22"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.spark}</svg>;
}

type GuideVideo = {file: File; url: string; duration?: number; range?: ClipRange};
const MODES: Mode[] = ['swap', 'motion', 'headswap', 'sharpness'];
const QUALITY_SHORT: Record<string, number> = {'480p': 480, '720p': 720, '1080p': 1080, '1440p': 1440, '2160p': 2160};
/** Output frame size, as the backend computes it: short side scaled to the target, both sides multiples of 32; above
 * 720p Sharpness renders at half size and doubles it (so the sides are multiples of 64). */
function outputSize(width: number, height: number, short: number, upscaled: boolean) {
  const fit = (s: number) => {const k = s / Math.min(width, height); return [Math.max(32, Math.round(width * k / 32) * 32), Math.max(32, Math.round(height * k / 32) * 32)];};
  if (!upscaled) return fit(short);
  const [w, h] = fit(Math.floor(short / 2)); return [w * 2, h * 2];
}
// Each mode's accent: `accent` for dark themes, `ink` (same hue, darker) for light ones; CSS picks one per theme.
const MODE_STYLE: Record<Mode, {accent: string; rgb: string; ink: string; inkRgb: string}> = {
  swap: {accent: '#D6FF4B', rgb: '214,255,75', ink: '#4d7c0f', inkRgb: '77,124,15'}, motion: {accent: '#AA8BFF', rgb: '170,139,255', ink: '#6d28d9', inkRgb: '109,40,217'},
  headswap: {accent: '#FF9F6B', rgb: '255,159,107', ink: '#c2410c', inkRgb: '194,65,12'}, sharpness: {accent: '#6BE4FF', rgb: '107,228,255', ink: '#0e7490', inkRgb: '14,116,144'},
};
const accentVars = (m: Mode, name: string) => {const a = MODE_STYLE[m] || MODE_STYLE.swap; return {[`--${name}-base`]: a.accent, [`--${name}-base-rgb`]: a.rgb, [`--${name}-ink`]: a.ink, [`--${name}-ink-rgb`]: a.inkRgb};};
type GeneratedVideo = {id: string; project?: string; mode?: Mode; duration?: number; result_url: string; created: number};
type View = 'studio' | 'history' | 'community';
const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, '0')}`;

export default function Studio() {
  const importSettingsInput = useRef<HTMLInputElement>(null);
  const [importedSettings, setImportedSettings] = useState<Record<string, unknown>>({});
  const [importRevision, setImportRevision] = useState(0);
  const [lang, setLang] = useState<Language>('en');
  const [mode, setMode] = useState<Mode>('swap');
  const [view, setView] = useState<View>('studio');
  const [pictures, setPictures] = useState<Picture[]>([]);
  const [expectedSlots, setExpectedSlots] = useState<number[]>([]);
  // Community examples leave some pictures to the user (e.g. Picture 1 = "You"): shown as empty tiles to fill.
  // Mirrors the panel's 'Improve my prompt', to explain what Write / Auto prompt do at Generate.
  const [enhanceOn, setEnhanceOn] = useState(true);
  const [bringSlots, setBringSlots] = useState<{slot: number; label: Record<Language, string>}[]>([]);
  const [video, setVideo] = useState<GuideVideo | null>(null);
  const [firstFrameSlot, setFirstFrameSlot] = useState<number | null>(null);
  const [editSlot, setEditSlot] = useState<number | null>(null);
  const [frameModal, setFrameModal] = useState(false);
  const [requestedProfile, setRequestedProfile] = useState<string | null>(null);
  const [editingVideo, setEditingVideo] = useState(false);
  const [subjects, setSubjects] = useState<SubjectBinding[]>([]);
  const [guideRepresentation, setGuideRepresentation] = useState<GuideRepresentation>('original');
  // 2D color marks: 1 = solid; lower keeps the guide person visible under a translucent tint (BFS Colored Mark used 0.35).
  const [markOpacity, setMarkOpacity] = useState(0.35);
  const [markLabels, setMarkLabels] = useState(false);
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  // A new guide starts a new generation: the panel drops the selected job (its plan, shots and result) until one is
  // picked again from the history.
  const [freshRevision, setFreshRevision] = useState(0);
  const startFresh = () => {setGenerationJob(null); setFreshRevision(n => n + 1); setBringSlots([]);};
  // Settings center (gear) and the first-run wizard, also opened by the offline banner and the generation panel.
  const [settingsOpen, setSettingsOpen] = useState<null | {wizard: boolean; tab: 'connection' | 'assistant' | 'access'}>(null);
  useEffect(() => {
    try {if (!localStorage.getItem(SETUP_KEY)) setSettingsOpen({wizard: true, tab: 'connection'});} catch {/* private mode */}
    const open = (e: Event) => setSettingsOpen({wizard: false, tab: ((e as CustomEvent).detail || 'connection')});
    addEventListener('henge:open-settings', open); return () => removeEventListener('henge:open-settings', open);
  }, []);
  // Recent: the latest generations on the bridge (exported directions live in History).
  const [serverJobs, setServerJobs] = useState<GenerationJob[]>([]);
  // History: search by project name (or job id) and an infinite list that grows 24 at a time.
  const [historySearch, setHistorySearch] = useState('');
  const [historyShown, setHistoryShown] = useState(24);
  const historyEnd = useRef<HTMLDivElement>(null);
  const recentJobs = serverJobs.slice(0, 4);
  useEffect(() => {
    if (view === 'community') return;
    let alive = true;
    const load = () => fetch('/api/backend/jobs', {cache: 'no-store'}).then(r => r.ok ? r.json() : []).then((rows: GenerationJob[]) => {if (alive && Array.isArray(rows)) setServerJobs([...rows].sort((a, b) => b.created - a.created));}).catch(() => {});
    load(); const timer = setInterval(load, 15000);
    return () => {alive = false; clearInterval(timer);};
  }, [view, generationJob?.id, generationJob?.status]);
  const [pendingAutoPromptJob, setPendingAutoPromptJob] = useState<string | null>(null);
  const [pickingId, setPickingId] = useState<string | null>(null);
  const [guideSignature, setGuideSignature] = useState('');
  const [prompt, setPrompt] = useState('');
  const [intent, setIntent] = useState('');
  const [auto, setAuto] = useState(false);
  // Prompt modes (one text field): improve = rewritten in English/H3 at Generate; auto = written now into the field
  // (then sent as is); exact = sent as written. autoSource keeps the user's own text for Undo.
  const [promptMode, setPromptMode] = useState<'improve' | 'auto' | 'exact'>('improve');
  const [autoSource, setAutoSource] = useState<string | null>(null);
  const [readLang, setReadLang] = useState<Language>('pt');
  const [translation, setTranslation] = useState<{text: string; lang: string; source: string} | null>(null);
  const [translating, setTranslating] = useState(false);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState('');
  const [native, setNative] = useState(false);
  const [quality, setQuality] = useState('480p');
  const [project, setProject] = useState('');
  const [ready, setReady] = useState(false);
  const [draggingPictures, setDraggingPictures] = useState(false);
  const [audioConditioning, setAudioConditioning] = useState(false);
  const [keepAudio, setKeepAudio] = useState(true);
  // The soundtrack H3 generates with each shot (joined at the cuts) instead of the guide's sound.
  const [generateAudio, setGenerateAudio] = useState(false);
  // Moving plate: an optional new background picture that follows the guide's camera (built on the bridge).
  const [background, setBackground] = useState<{file: File; url: string} | null>(null);
  const backgroundInput = useRef<HTMLInputElement>(null);
  const [shotSeconds, setShotSeconds] = useState(4.5);
  const [timelineFps, setTimelineFps] = useState(24);
  const [contextFrames, setContextFrames] = useState(22);
  const [cutMode, setCutMode] = useState<CutMode>('fit');
  // Split points inside a take (seconds from the selection start), suggested by Molmo2 or the assistant.
  const [splitPoints, setSplitPoints] = useState<number[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const suggestRequest = useRef<{id: string; controller: AbortController} | null>(null);
  const [serverGenerationActive, setServerGenerationActive] = useState(false);
  const generationActive = serverGenerationActive || (!!generationJob && !['completed', 'failed', 'cancelled'].includes(generationJob.status));
  useEffect(() => {
    let disposed = false, timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const response = await fetch('/api/backend/jobs', {cache: 'no-store'});
        const jobs = response.ok ? await response.json() as {status: string}[] : [];
        if (!disposed) setServerGenerationActive(jobs.some(job => !['completed', 'failed', 'cancelled'].includes(job.status)));
      } catch { /* The bridge's health state reports connection problems separately. */ }
      if (!disposed) timer = setTimeout(refresh, 2500);
    }
    void refresh();
    return () => {disposed = true; clearTimeout(timer);};
  }, []);
  // Molmo2 set up and turned on (Settings → Molmo2): the split suggestion needs it.
  const [molmoReady, setMolmoReady] = useState(false);
  useEffect(() => {fetch('/api/backend/assistant/pointing').then(r => r.json()).then(s => setMolmoReady(!!s.configured)).catch(() => {});}, []);
  useEffect(() => {setSplitPoints([]);}, [video?.url, video?.range?.start, video?.range?.end]);
  const [history, setHistory] = useState<SavedDirection[]>([]);
  const [generatedOpen, setGeneratedOpen] = useState(false);
  const [generated, setGenerated] = useState<GeneratedVideo[] | null>(null);
  const [loadingGenerated, setLoadingGenerated] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState<Mode | 'all'>('all');
  const [activeTemplate, setActiveTemplate] = useState<string | null>(null);
  const [modal, setModal] = useState<'share' | 'delete' | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const pictureDragDepth = useRef(0);
  const live = useRef({pictures, video});
  live.current = {pictures, video};
  const t = DESIGN_COPY[lang];
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const style = accentVars(mode, 'accent') as CSSProperties;
  const modeName = (value: Mode) => ({swap: t.swap, motion: t.motion, headswap: tr('Head Swap', 'Troca de cabeça', 'Cambio de cabeza'), sharpness: tr('Sharpness', 'Nitidez', 'Nitidez')})[value];
  const modeHint = (value: Mode) => ({
    swap: tr('Replace characters', 'Trocar personagens', 'Cambiar personajes'),
    motion: tr('Transfer movement', 'Transferir movimento', 'Transferir movimiento'),
    headswap: tr('Change the face', 'Mudar o rosto', 'Cambiar el rostro'),
    sharpness: tr('Enhance details', 'Realçar detalhes', 'Realzar detalles'),
  })[value];
  // Model names for History (from the bridge's model list), to search and filter generations by model.
  const [modelLabels, setModelLabels] = useState<Record<string, string>>({});
  const [historyModel, setHistoryModel] = useState('all');
  useEffect(() => {
    if (view !== 'history') return;
    fetch('/api/backend/health', {cache: 'no-store'}).then(r => r.ok ? r.json() : null).then(h => {if (h?.models) setModelLabels(Object.fromEntries(Object.entries(h.models as Record<string, {label: string}>).map(([k, m]) => [k, m.label])));}).catch(() => {});
  }, [view]);
  const jobModel = (j: GenerationJob) => {const id = typeof j.options?.profile === 'string' ? j.options.profile : ''; return {id, label: modelLabels[id] || id};};
  const TERMINAL_STATUS = ['completed', 'failed', 'cancelled'];
  async function deleteJob(j: GenerationJob) {
    if (!await confirmDialog({tone: 'danger', title: tr('Delete this generation?', 'Apagar esta geração?', '¿Borrar esta generación?'), message: tr('Its result, shots and files are removed from this Henge. This cannot be undone.', 'O resultado, os trechos e os arquivos saem deste Henge. Não dá para desfazer.', 'Su resultado, tramos y archivos se borran de este Henge. No se puede deshacer.'), confirm: tr('Delete', 'Apagar', 'Borrar'), cancel: tr('Keep', 'Manter', 'Conservar')})) return;
    const r = await fetch(`/api/backend/jobs/${j.id}`, {method: 'DELETE'});
    if (r.ok) setServerJobs(rows => rows.filter(x => x.id !== j.id));
    else {const reply = await r.json().catch(() => ({})); setNotice(reply.detail || `HTTP ${r.status}`);}
  }
  async function clearHistory() {
    const done = serverJobs.filter(j => TERMINAL_STATUS.includes(j.status)).length;
    if (!done || !await confirmDialog({tone: 'danger', title: tr(`Clear the history (${done})?`, `Limpar o histórico (${done})?`, `¿Vaciar el historial (${done})?`), message: tr('Every finished, failed or cancelled generation and its files are removed from this Henge. Running ones stay. This cannot be undone.', 'Todas as gerações concluídas, com falha ou canceladas e seus arquivos saem deste Henge. As que estão rodando ficam. Não dá para desfazer.', 'Todas las generaciones terminadas, fallidas o canceladas y sus archivos se borran de este Henge. Las que están en curso se quedan. No se puede deshacer.'), confirm: tr('Clear history', 'Limpar histórico', 'Vaciar historial'), cancel: tr('Keep', 'Manter', 'Conservar')})) return;
    const r = await fetch('/api/backend/jobs', {method: 'DELETE'});
    if (r.ok) {const {deleted} = await r.json() as {deleted: string[]}; setServerJobs(rows => rows.filter(x => !deleted.includes(x.id)));}
  }
  const historyModels = [...new Set(serverJobs.map(j => jobModel(j).id).filter(Boolean))];
  const historyJobs = serverJobs.filter(j => (historyFilter === 'all' || j.mode === historyFilter) && (historyModel === 'all' || jobModel(j).id === historyModel)
    && (!historySearch.trim() || `${j.project || ''} ${j.id} ${modeName((j.mode || 'swap') as Mode)} ${jobModel(j).label} ${j.options?.conditioning_mode === 'tara' ? 'tara' : ''} ${j.options?.turbo || ''}`.toLowerCase().includes(historySearch.trim().toLowerCase())));
  useEffect(() => {setHistoryShown(24);}, [historyFilter, historySearch, historyModel]);
  useEffect(() => {
    const end = historyEnd.current; if (view !== 'history' || !end) return;
    const observer = new IntersectionObserver(([entry]) => {if (entry.isIntersecting) setHistoryShown(n => n + 24);}, {rootMargin: '400px'});
    observer.observe(end); return () => observer.disconnect();
  }, [view, historyJobs.length]);
  const modeDescription = ({swap: t.swapDesc, motion: t.motionDesc,
    headswap: tr('Replace only the head with a face picture. Body, clothing, motion and scene stay untouched.', 'Troque só a cabeça por uma foto de rosto. Corpo, roupa, movimento e cena ficam intactos.', 'Cambia solo la cabeza por una foto de rostro. Cuerpo, ropa, movimiento y escena quedan intactos.'),
    sharpness: tr('Sharpen any clip — an upload or one of your generations — keeping its motion and look.', 'Deixe qualquer clipe mais nítido — um upload ou uma das suas gerações — mantendo movimento e aparência.', 'Da nitidez a cualquier clip — una subida o una de tus generaciones — conservando su movimiento y aspecto.')})[mode];
  const fixedRecipe = isFixedRecipe(mode);
  const maxPictures = mode === 'headswap' ? 1 : mode === 'sharpness' ? 0 : MAX_PICTURES;
  const activePictures = pictures.filter(p => p.slot <= maxPictures);
  const busy = working;

  useEffect(() => () => {
    live.current.pictures.forEach(p => URL.revokeObjectURL(p.url));
    if (live.current.video) URL.revokeObjectURL(live.current.video.url);
  }, []);
  useEffect(() => {
    try {
      const s = JSON.parse(localStorage.getItem('henge-draft') || 'null');
      if (s && typeof s === 'object') {
        setPrompt(typeof s.prompt === 'string' ? s.prompt : '');
        setSubjects(readSubjectBindings(s.subjects));
        setGuideRepresentation(['2d', '3d', 'mask'].includes(s.guideRepresentation) ? s.guideRepresentation : 'original');
        setGuideSignature(typeof s.guideSignature === 'string' ? s.guideSignature : '');
        setIntent(typeof s.intent === 'string' ? s.intent : '');
        setMode(MODES.includes(s.mode) ? s.mode : 'swap');
        setProject(typeof s.project === 'string' && s.project !== 'Untitled project' ? s.project : '');
        setQuality(['480p', '720p', '1080p', '1440p', '2160p'].includes(s.quality) ? s.quality : '480p');
        setAudioConditioning(s.audioConditioning === true);
        // Keep original audio is not restored from the draft: every session and every mode starts with it on.
        setShotSeconds(Math.min(15, Math.max(1, Number(s.shotSeconds) || 4.5)));
        setTimelineFps(Math.min(120, Math.max(1, Number(s.timelineFps) || 24)));
        setContextFrames([5, 22, 39].includes(s.contextFrames) ? s.contextFrames : 22);
        if (['fit', 'every', 'off'].includes(s.cutMode)) setCutMode(s.cutMode);
        if (['en', 'pt', 'es'].includes(s.lang)) setLang(s.lang);
      }
      const saved = readHistory(localStorage.getItem(HISTORY_KEY));
      setHistory(saved); setSelectedId(saved[0]?.id || null);
    } catch { /* An unavailable browser store does not block local editing. */ }
    setReady(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    document.documentElement.lang = lang;
    try { localStorage.setItem('henge-draft', JSON.stringify({schema_version: 2, prompt, intent, mode, project, quality, audioConditioning, keepAudio, shotSeconds, timelineFps, contextFrames, cutMode, lang, subjects, guideRepresentation, guideSignature})); } catch { /* Editing still works without draft persistence. */ }
  }, [ready, prompt, intent, mode, project, quality, audioConditioning, keepAudio, shotSeconds, timelineFps, contextFrames, cutMode, lang, subjects, guideRepresentation, guideSignature]);
  useEffect(() => {
    if (!ready) return;
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); }
    catch { setNotice(tr('Browser storage is full. Download your directions before leaving.', 'O armazenamento do navegador está cheio. Baixe suas direções antes de sair.', 'El almacenamiento del navegador está lleno. Descarga tus direcciones antes de salir.')); }
  }, [history, ready]); // Persist only real local exports, not mock generations.
  useEffect(() => {
    if (modal) dialog.current?.showModal();
    else dialog.current?.close();
  }, [modal]);

  const invalid = invalidReferences(prompt, pictures.map(p => p.slot));
  const selectedDuration = video?.range ? video.range.end - video.range.start : 0;

  // --- Studio assistant: it reads this render's state and acts through the same setters as the controls. ---
  const panelControls = useRef<PanelControls | null>(null);
  const studioLive = useRef({splitPoints, mode, prompt, video, pictures, subjects, guideRepresentation, markOpacity, quality, generationJob, maxPictures, promptMode, shotSeconds, cutMode, contextFrames, keepAudio, audioConditioning, timelineFps, project});
  studioLive.current = {splitPoints, mode, prompt, video, pictures, subjects, guideRepresentation, markOpacity, quality, generationJob, maxPictures, promptMode, shotSeconds, cutMode, contextFrames, keepAudio, audioConditioning, timelineFps, project};
  const found = useRef(new Map<string, {width: number; height: number; people: {number: number; x: number; y: number}[]}>());
  // Explanation images from the chat (never Pictures): match_people can use them as photos of the people to find.
  const explained = useRef(new Map<string, File>());
  const settle = () => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  const studioState = () => {
    const c = studioLive.current;
    return {mode: c.mode, guide_video: c.video ? {name: c.video.file.name, duration: c.video.duration ?? null, selected: c.video.range ?? null} : null,
      pictures: c.pictures.map(p => ({slot: p.slot, name: p.file.name})), max_pictures: c.maxPictures,
      subjects: c.subjects.map((s, i) => ({subject: i + 1, label: s.label, color: s.color, picture_slots: s.picture_slots, marks: s.anchors.map(a => a.time_seconds)})),
      guide_representation: c.guideRepresentation, mark_opacity: c.markOpacity, prompt: c.prompt, prompt_mode: c.promptMode, quality: c.quality,
      shots: {seconds: c.shotSeconds, cut_mode: c.cutMode, context_frames: c.contextFrames, split_points: c.splitPoints}, output: {keep_audio: c.keepAudio, audio_conditioning: c.audioConditioning, timeline_fps: c.timelineFps}, project: c.project,
      selected_job: c.generationJob ? {id: c.generationJob.id, reference: `#${c.generationJob.id.slice(0, 8)}`, status: c.generationJob.status, stage: c.generationJob.stage, message: c.generationJob.message} : null};
  };
  /** Molmo2's split points for the selection with the current shot length: {points, camera_cuts, shots, molmo}. */
  async function suggestSplits(longest: number, requestId = crypto.randomUUID(), signal?: AbortSignal) {
    if (generationActive || working) throw Error('Molmo2 cannot suggest cuts while a generation is running.');
    const v = studioLive.current.video; if (!v?.range) throw Error('Attach and trim the guide video first');
    const body = new FormData(); body.set('video', v.file); body.set('start', String(v.range.start)); body.set('end', String(v.range.end)); body.set('max_seconds', String(Math.min(15, Math.max(1, longest)))); body.set('request_id', requestId);
    const response = await fetch('/api/backend/assistant/suggest-cuts', {method: 'POST', body, ...(signal ? {signal} : {})}); const reply = await response.json();
    if (!response.ok) throw Error(reply.detail || `HTTP ${response.status}`);
    return reply as {points: number[]; camera_cuts: number[]; breaks: number[]; molmo: string; shots: {start: number; end: number; context_seconds: number}[]};
  }
  function cancelSuggestion() {
    const active = suggestRequest.current; if (!active) return;
    active.controller.abort();
    void fetch('/api/backend/assistant/cancel', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({request_id: active.id})}).catch(() => {});
    setNotice(tr('Cancelling Molmo2…', 'A cancelar o Molmo2…', 'Cancelando Molmo2…'));
  }
  useEffect(() => {if (generationActive && suggestRequest.current) cancelSuggestion();}, [generationActive]);
  async function runStudioCall(call: StudioCall): Promise<StudioResult> {
    const c = studioLive.current, input = call.input;
    const num = (k: string) => Number(input[k]);
    const jobId = (value: unknown) => {const ref=String(value ?? '').trim().toLowerCase().replace(/^#/, ''); return ref.length === 8 && c.generationJob?.id.startsWith(ref) ? c.generationJob.id : ref;};
    const inRange = (t: number) => {if (!c.video?.range) throw Error('Attach and trim the guide video first'); if (!Number.isFinite(t) || t < c.video.range.start || t > c.video.range.end) throw Error(`Use a time inside the selected interval ${c.video.range.start.toFixed(2)}–${c.video.range.end.toFixed(2)} s`); return t;};
    switch (call.name) {
      case 'get_studio_state': return {text: JSON.stringify(studioState())};
      case 'view_pictures': {
        if (!c.pictures.length) return {text: 'No pictures attached.'};
        return {text: c.pictures.map((p, i) => `Image ${i + 1} = Picture ${p.slot} (${p.file.name})`).join('; '), images: await Promise.all(c.pictures.map(p => thumbnail(p.file, 640)))};
      }
      case 'view_frame': {
        const t = inRange(num('time')); const frame = await captureFrame(c.video!.url, t);
        return {text: `Guide frame at ${t.toFixed(2)} s (${frame.width}x${frame.height})${input.grid ? ', with a 0-1 grid' : ''}.`, images: [input.grid ? await annotated(frame.blob, 960, drawGrid) : await thumbnail(frame.blob, 960)]};
      }
      case 'point_video': {
        const start = inRange(num('start')), end = inRange(num('end'));
        if (end <= start || end - start > 30) throw Error('Point one shot at a time, at most 30 seconds');
        const body = new FormData(); body.set('video', c.video!.file); body.set('query', String(input.query ?? ''));
        body.set('start', String(start)); body.set('end', String(end));
        const response = await fetch('/api/backend/assistant/point-video', {method: 'POST', body});
        const reply = await response.json();
        if (!response.ok) throw Error(reply.detail || `HTTP ${response.status}`);
        const {previews, ...report} = reply;
        return {text: JSON.stringify(report), images: previews ?? []};
      }
      case 'ask_video': {
        // Molmo2 watches the whole interval (with timestamps) and answers in text.
        const range = c.video?.range; if (!range) throw Error('Attach and trim the guide video first');
        const start = input.start === undefined ? range.start : inRange(num('start')), end = input.end === undefined ? range.end : inRange(num('end'));
        const body = new FormData(); body.set('video', c.video!.file); body.set('question', String(input.question ?? '')); body.set('start', String(start)); body.set('end', String(end));
        const response = await fetch('/api/backend/assistant/ask-video', {method: 'POST', body}); const reply = await response.json();
        if (!response.ok) throw Error(reply.detail || `HTTP ${response.status}`);
        return {text: `Molmo2 (${start.toFixed(2)}–${end.toFixed(2)} s; times are seconds from ${start.toFixed(2)} s): ${reply.answer}`};
      }
      case 'suggest_cuts': {
        const reply = await suggestSplits(input.max_seconds === undefined ? c.shotSeconds : num('max_seconds'));
        if (input.apply !== false) {setSplitPoints(reply.points); if (input.max_seconds !== undefined) setShotSeconds(Math.min(15, Math.max(1, num('max_seconds')))); await settle();}
        return {text: `Shots (seconds from the selection start): ${reply.shots.map(s => `${s.start}–${s.end}${s.context_seconds ? ` (+${s.context_seconds}s context)` : ''}`).join(', ')}. Split points ${input.apply === false ? 'proposed' : 'applied'}: ${reply.points.join(', ') || 'none'}; camera cuts: ${reply.camera_cuts.join(', ') || 'none'}. Molmo2 saw breaks at ${reply.breaks.join(', ') || 'none'}.`};
      }
      case 'match_people': {
        // Find each person shown in a photo in every shot (local Molmo2), then mark them: SAM tracks from the marks.
        const people = Array.isArray(input.people) ? input.people as {photo?: string; picture_slots?: number[]; label?: string}[] : [];
        if (!people.length) throw Error('Give people: [{photo, picture_slots}]');
        const range = c.video?.range; if (!range) throw Error('Attach and trim the guide video first');
        const start = input.start === undefined ? range.start : inRange(num('start')), end = input.end === undefined ? range.end : inRange(num('end'));
        const photo = (name: string) => {
          const slot = /^\s*@?picture\s*(\d+)\s*$/i.exec(name);
          if (slot) {const p = c.pictures.find(x => x.slot === Number(slot[1])); if (!p) throw Error(`Picture ${slot[1]} is not attached`); return p.file;}
          const picture = c.pictures.find(x => x.file.name === name.trim()); if (picture) return picture.file;
          const file = explained.current.get(name.trim()); if (!file) throw Error(`No explanation image named ${name}. Use the exact file name, or "Picture N"`); return file;
        };
        const body = new FormData(); body.set('video', c.video!.file); body.set('start', String(start)); body.set('end', String(end));
        people.forEach(p => body.append('people', photo(String(p.photo ?? ''))));
        const response = await fetch('/api/backend/assistant/match-people', {method: 'POST', body}); const reply = await response.json();
        if (!response.ok) throw Error(reply.detail || `HTTP ${response.status}`);
        const lines: string[] = []; let current = [...c.subjects];
        reply.people.forEach((found: {person: number; anchors: {x: number; y: number; time_seconds: number}[]; missing_shots: number[]}, i: number) => {
          const want = people[i], slots = (want.picture_slots ?? []).map(Number).filter(Number.isFinite);
          const label = want.label || String(want.photo);
          if (!found.anchors.length) {lines.push(`${label}: not found in any shot.`); return;}
          if (input.apply === false || !slots.length) {lines.push(`${label}: ${found.anchors.map(a => `(${a.x.toFixed(3)}, ${a.y.toFixed(3)}) @ ${a.time_seconds.toFixed(2)} s`).join('; ')}${slots.length ? '' : ' (no picture_slots: not marked)'}.`); return;}
          if (slots.some(n => !c.pictures.some(p => p.slot === n))) throw Error('Use attached picture slots');
          const anchors = found.anchors.map(a => ({x: a.x, y: a.y, time_seconds: a.time_seconds, frame_width: reply.frame_width, frame_height: reply.frame_height}));
          const index = current.findIndex(s => s.picture_slots.length === slots.length && s.picture_slots.every(n => slots.includes(n)));
          if (index >= 0) {
            const merged = [...current[index].anchors.filter(a => !anchors.some(b => Math.abs(a.time_seconds - b.time_seconds) < .05)), ...anchors].sort((p, q) => p.time_seconds - q.time_seconds);
            current = current.map((s, k) => k === index ? {...s, anchors: merged} : s);
            lines.push(`${label} -> subject ${index + 1} (${current[index].color}, Picture ${slots.join(', ')}): marks at ${anchors.map(a => a.time_seconds.toFixed(2) + ' s').join(', ')}; not in shots ${found.missing_shots.join(', ') || 'none'}.`);
          } else {
            const color = SUBJECT_COLORS.find(col => !current.some(s => s.color === col.name)); if (!color) throw Error('Every color is in use');
            current = [...current, {id: crypto.randomUUID(), label: want.label || `Subject ${current.length + 1}`, color: color.name, picture_slots: slots, anchors}];
            lines.push(`${label} -> subject ${current.length} (${color.name}, Picture ${slots.join(', ')}): marks at ${anchors.map(a => a.time_seconds.toFixed(2) + ' s').join(', ')}; not in shots ${found.missing_shots.join(', ') || 'none'}.`);
          }
        });
        if (input.apply !== false) {setSubjects(current); await settle();}
        return {text: `Shots: ${reply.shots.map((s: {shot: number; start: number; end: number}) => `${s.shot}=${s.start.toFixed(2)}–${s.end.toFixed(2)} s`).join(', ')}. ${lines.join(' ')} Check the previews (one per shot); remove a wrong mark with remove_subject or re-mark it with mark_subject.`, images: reply.previews ?? []};
      }
      case 'find_people': {
        const t = inRange(num('time')); const frame = await captureFrame(c.video!.url, t);
        const body = new FormData(); body.set('frame', frame.blob, 'frame.png'); body.set('kind', input.kind === 'animal' ? 'animal' : 'person');
        const response = await fetch('/api/backend/assistant/people', {method: 'POST', body}); const reply = await response.json();
        if (!response.ok) throw Error(reply.detail || `HTTP ${response.status}`);
        found.current.set(t.toFixed(2), {width: frame.width, height: frame.height, people: reply.people});
        return {text: reply.people.length ? `${reply.people.length} found at ${t.toFixed(2)} s, numbered left to right: ${reply.people.map((p: {number: number; box: number[]}) => `#${p.number} box x=${p.box[0]} w=${p.box[2]}`).join('; ')}.` : `Nobody found at ${t.toFixed(2)} s. Try another time.`, images: [reply.overlay]};
      }
      case 'set_mode': {
        const m = String(input.mode) as Mode; if (!['swap', 'motion', 'headswap', 'sharpness'].includes(m)) throw Error('Unknown mode');
        setMode(m); setKeepAudio(true); await settle(); return {text: `Mode is now ${m}.`};
      }
      case 'set_prompt': setPrompt(String(input.text ?? '')); await settle(); return {text: 'Prompt updated.'};
      case 'mark_subject': {
        const t = num('time'); let hit = found.current.get(t.toFixed(2));
        if (!hit) {
          // Marking by the assistant's own vision: a point needs only the frame's size, not find_people.
          if (input.x === undefined || input.y === undefined) throw Error(`Call find_people at ${t} first, or give x and y`);
          const f = await captureFrame(c.video!.url, inRange(t)); hit = {width: f.width, height: f.height, people: []}; found.current.set(t.toFixed(2), hit);
        }
        // The frame with the marked point, so the assistant can check it landed on the right person.
        const shown = async (color: string, label: string) => [await annotated((await captureFrame(c.video!.url, inRange(t))).blob, 960, (g, w, h) => drawPoint(g, w, h, point.x, point.y, SUBJECT_COLORS.find(x => x.name === color)?.hex ?? '#fff', label))];
        // A numbered person from find_people, or a point (0-1) on someone it missed: SAM segments from that point.
        let point: {x: number; y: number}, who: string;
        if (input.person !== undefined) {
          const person = hit.people.find(p => p.number === num('person')); if (!person) throw Error(`No person #${input.person} at ${t}`);
          point = {x: person.x, y: person.y}; who = `person #${person.number}`;
        } else if (input.x !== undefined && input.y !== undefined) {
          point = {x: Math.min(1, Math.max(0, num('x'))), y: Math.min(1, Math.max(0, num('y')))}; who = `the point (${point.x.toFixed(2)}, ${point.y.toFixed(2)})`;
        } else throw Error('Give person (a number from find_people) or x and y (0-1) on the person');
        const anchor = {...point, time_seconds: t, frame_width: hit.width, frame_height: hit.height};
        const raw = input.picture_slots, slots = (Array.isArray(raw) ? raw : raw == null ? [] : [raw]).map(Number).filter(Number.isFinite);
        // One subject per performer: marking again someone bound to the same pictures adds a mark to that subject.
        const index = input.subject !== undefined ? num('subject') - 1
          : slots.length ? c.subjects.findIndex(s => s.picture_slots.length === slots.length && s.picture_slots.every(n => slots.includes(n))) : -1;
        if (index >= 0) {
          const target = c.subjects[index]; if (!target) throw Error(`No subject ${input.subject}`);
          setSubjects(current => current.map(s => s.id === target.id ? {...s, anchors: [...s.anchors.filter(a => Math.abs(a.time_seconds - t) > .05), anchor].sort((p, q) => p.time_seconds - q.time_seconds)} : s)); await settle();
          const times = [...target.anchors.filter(a => Math.abs(a.time_seconds - t) > .05).map(a => a.time_seconds), t].sort((p, q) => p - q);
          return {text: `Subject ${index + 1} (${target.color}, Picture ${target.picture_slots.join(', ')}) is ${who} at ${t.toFixed(2)} s. Its marks: ${times.map(x => x.toFixed(2) + ' s').join(', ')}.`, images: await shown(target.color, `Subject ${index + 1}`)};
        }
        if (!slots.length) throw Error('A new subject needs picture_slots. To mark the same person again (another time or after a cut), pass subject with its number instead.');
        if (slots.some(n => !c.pictures.some(p => p.slot === n))) throw Error('Use attached picture slots');
        const color = SUBJECT_COLORS.find(col => !c.subjects.some(s => s.color === col.name));
        if (!color) throw Error('Every color is in use');
        const subject: SubjectBinding = {id: crypto.randomUUID(), label: String(input.label || `Subject ${c.subjects.length + 1}`), color: color.name, picture_slots: slots, anchors: [anchor]};
        setSubjects(current => [...current, subject]); await settle();
        return {text: `Subject ${c.subjects.length + 1} (${color.name}) = ${who} at ${t.toFixed(2)} s → Picture ${slots.join(', ')}.`, images: await shown(color.name, `Subject ${c.subjects.length + 1}`)};
      }
      case 'clear_subjects': setSubjects([]); await settle(); return {text: 'All subjects removed.'};
      case 'remove_subject': {const target = c.subjects[num('subject') - 1]; if (!target) throw Error(`No subject ${input.subject}`); setSubjects(current => current.filter(s => s.id !== target.id)); await settle(); return {text: `Subject ${input.subject} removed.`};}
      case 'remove_pictures': {
        const slots = (input.slots as number[] | undefined || []).map(Number);
        if (!slots.length) {removeAllPictures(); await settle(); return {text: 'All pictures removed.'};}
        slots.forEach(slot => removePicture(slot)); await settle(); return {text: `Removed Picture ${slots.join(', ')}.`};
      }
      case 'set_interval': {
        if (!c.video) throw Error('Attach a guide video first');
        const total = c.video.duration ?? Number.POSITIVE_INFINITY; const start = Math.max(0, num('start')), end = Math.min(total, num('end'));
        if (!(end > start + .2)) throw Error('The interval must be longer than 0.2 s and inside the video');
        setVideo(v => v ? {...v, range: {start, end}} : v); await settle(); return {text: `Interval ${start.toFixed(2)}–${end.toFixed(2)} s.`};
      }
      case 'set_shots': {
        if (input.seconds !== undefined) setShotSeconds(Math.min(20, Math.max(2, num('seconds'))));
        if (input.cut_mode !== undefined) setCutMode(String(input.cut_mode) as CutMode);
        if (Array.isArray(input.split_points)) setSplitPoints((input.split_points as unknown[]).map(Number).filter(x => Number.isFinite(x) && x > 0).sort((a, b) => a - b));
        if (input.context_frames !== undefined) setContextFrames(Math.min(48, Math.max(0, Math.round(num('context_frames')))));
        await settle(); return {text: 'Shot settings updated.'};
      }
      case 'set_output': {
        if (input.keep_audio !== undefined) setKeepAudio(Boolean(input.keep_audio));
        if (input.audio_conditioning !== undefined) setAudioConditioning(Boolean(input.audio_conditioning));
        if (input.timeline_fps !== undefined) setTimelineFps(Math.min(60, Math.max(8, num('timeline_fps'))));
        await settle(); return {text: 'Output settings updated.'};
      }
      case 'set_project': setProject(String(input.name ?? '').slice(0, 80)); await settle(); return {text: 'Project renamed.'};
      case 'get_options': {if (!panelControls.current) throw Error('The generation panel is not ready'); return {text: JSON.stringify(panelControls.current.getOptions())};}
      case 'set_options': {
        if (!panelControls.current) throw Error('The generation panel is not ready');
        panelControls.current.applyOptions((input.options || {}) as Record<string, unknown>); await settle();
        return {text: 'Options now: ' + JSON.stringify((panelControls.current.getOptions() as {options: unknown}).options)};
      }
      case 'select_job': panelControls.current?.selectJob(jobId(input.job_id)); await settle(); return {text: 'Job shown in the panel.'};
      case 'use_generation_as_guide': {
        const response = await fetch('/api/backend/jobs', {cache: 'no-store'}); const rows: (GeneratedVideo & {status?: string})[] = await readJson(response);
        const ref = String(input.job_id ?? '').trim().toLowerCase().replace(/^#/, '');
        const matches = rows.filter(j => j.id === ref || (ref.length === 8 && j.id.startsWith(ref)));
        if (matches.length !== 1 || matches[0].status !== 'completed' || !matches[0].result_url) throw Error('Use the reference of one completed generation');
        const nextMode = String(input.mode) as Mode;
        if (!MODES.includes(nextMode)) throw Error('Unknown mode');
        if (!await useGenerated(matches[0], nextMode)) throw Error('Could not load that generation result');
        await settle(); return {text: `Generation #${matches[0].id.slice(0, 8)} is now the guide video in ${nextMode} mode. The next generation has not been started.`};
      }
      case 'send_marks_to_job': {
        const resolved = jobId(input.job_id);
        const r = await fetch(`/api/backend/jobs/${resolved}/subjects`, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({bindings: c.subjects, representation: c.guideRepresentation, ...(c.guideRepresentation === '2d' ? {mark_opacity: c.markOpacity} : {})})});
        const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`);
        return {text: `Marks sent to job ${input.job_id}; ${reply.status === 'queued_mask' ? 'its preview is being rebuilt (wait_for_job plan).' : 'saved.'}`};
      }
      case 'set_guide': {
        const rep = String(input.representation) as GuideRepresentation;
        if (!['original', '2d', '3d', 'mask'].includes(rep)) throw Error('Unknown representation');
        setGuideRepresentation(rep); if (input.mark_opacity !== undefined) setMarkOpacity(Math.min(1, Math.max(.1, num('mark_opacity'))));
        await settle(); return {text: `Guide is ${rep}${rep === '2d' ? `, mark opacity ${studioLive.current.markOpacity}` : ''}.`};
      }
      case 'set_quality': setQuality(String(input.quality)); await settle(); return {text: `Quality is ${studioLive.current.quality}.`};
      case 'set_auto_approve': panelControls.current?.setAutoApprove(Boolean(input.enabled)); await settle(); return {text: `Auto-approve ${input.enabled ? 'on' : 'off'}.`};
      case 'generate': {
        if (!panelControls.current) throw Error('The generation panel is not ready');
        await settle();
        // Say exactly what blocks Generate, so the assistant can fix it instead of asking the user.
        const c = studioLive.current, missing: string[] = [], fixed = c.mode === 'headswap' || c.mode === 'sharpness';
        if (!c.video?.range) missing.push('attach a guide video and confirm its interval');
        if (!fixed && !c.prompt.trim()) missing.push('the prompt is empty: call set_prompt');
        if (!fixed && !c.pictures.length && c.mode !== 'motion') missing.push('attach at least one picture');
        c.subjects.forEach((s, i) => {
          if (!s.picture_slots.length) missing.push(`subject ${i + 1} has no picture: remove it, or add that person as another mark of an existing subject (mark_subject with subject)`);
          else if (s.picture_slots.some(n => !c.pictures.some(p => p.slot === n))) missing.push(`subject ${i + 1} points to a picture that is not attached`);
          if (s.anchors.some(a => !c.video?.range || a.time_seconds < c.video.range.start || a.time_seconds >= c.video.range.end)) missing.push(`subject ${i + 1} has a mark outside the selected interval`);
        });
        const badTokens = fixed ? [] : invalidReferences(c.prompt, c.pictures.map(p => p.slot));
        if (badTokens.length) missing.push('the prompt names pictures that are not attached: ' + badTokens.join(', '));
        if (missing.length) throw Error('Not ready to generate: ' + missing.join('; '));
        const id = await panelControls.current.submit();
        return {text: `Generation started: reference #${id.slice(0, 8)} (full job id ${id}). Use wait_for_job.`};
      }
      default: throw Error(`Unknown studio tool ${call.name}`);
    }
  }
  // Improve at Generate: in Improve mode, and in Auto Prompt mode until the AI has written the final prompt.
  useEffect(() => {panelControls.current?.setEnhancePrompt(promptMode === 'improve' || (promptMode === 'auto' && autoSource === null));}, [promptMode, autoSource]);
  useEffect(() => {setReadLang(lang === 'en' ? 'pt' : lang);}, [lang]);
  const assistantController: StudioController = {state: studioState, run: runStudioCall, remember: files => files.forEach(file => explained.current.set(file.name, file)), ingest: async files => {
    const images=files.filter(file => file.type.startsWith('image/')), videos=files.filter(file => file.type.startsWith('video/'));
    if (videos.length) addVideo([videos[0]], true);
    const added = images.length ? addPictures(images) : 0;
    await settle();
    const kept = images.length ? (added < images.length ? `Only ${added} of ${images.length} image(s) loaded: no free picture slots. ` : `${added} reference image(s) loaded in attachment order${maxPictures ? '' : ' (kept as Pictures; the current Sharpness mode does not use them, switch mode to use them)'}. `) : '';
    return {text: `${videos.length ? `${videos[0].name} loaded as guide. ` : ''}${kept}`};
  }};
  const contextWindow = selectedDuration > 15;
  const shotFrames = Math.max(22, Math.floor((Math.round(shotSeconds * 24) - 5) / 17) * 17 + 5);
  const estimatedShots = selectedDuration ? Math.ceil(Math.round(selectedDuration * timelineFps) / shotFrames) : 0;
  const subjectErrors = subjects.some(s => !s.anchors.length || !s.picture_slots.length || s.picture_slots.some(n => !pictures.some(p => p.slot === n)) || s.anchors.some(a => !video?.range || a.time_seconds < video.range.start || a.time_seconds >= video.range.end));
  const executionPrompt = prompt + (subjects.length && !subjectErrors ? '\n\n' + bindingPrompt(subjects, guideRepresentation) : '');
  const canExport = !!video?.range && !editingVideo && ready && !busy && !suggesting && (fixedRecipe
    ? activePictures.length === maxPictures
    // Motion's first-frame propagate model also runs from the prompt alone; the bridge rejects that for other models.
    : (pictures.length > 0 || mode === 'motion') && !!prompt.trim() && !invalid.length && !subjectErrors);
  const selected = history.find(h => h.id === selectedId) || null;
  const filteredHistory = history.filter(h => historyFilter === 'all' || h.request.mode === historyFilter);
  const chosenTemplate = TEMPLATES.find(x => x.id === activeTemplate);
  const query = prompt.slice(0, textarea.current?.selectionStart ?? prompt.length).match(/@(Picture\d*|Video\d*|P\w*|V\w*|)$/i);
  const mentions = [...pictures.map(p => `@Picture${p.slot}`), ...(video ? ['@Video1'] : [])];
  const suggestions = mentions.filter(tag => !query || tag.toLowerCase().startsWith(query[0].toLowerCase()));

  function insertTag(tag: string) {
    const area = textarea.current, start = area?.selectionStart ?? prompt.length, end = area?.selectionEnd ?? start;
    const match = prompt.slice(0, start).match(/@[A-Za-z0-9]*$/);
    const from = match ? start - match[0].length : start;
    setPrompt(prompt.slice(0, from) + tag + ' ' + prompt.slice(end));
    requestAnimationFrame(() => { area?.focus(); area?.setSelectionRange(from + tag.length + 1, from + tag.length + 1); });
  }
  function addPictures(files: FileList | File[] | null) {
    if (!files) return 0;
    // Sharpness uses no pictures, but keeps them for the other modes (e.g. pictures attached in the assistant chat
    // while Sharpness was open): they become active again when the mode changes.
    const limit = maxPictures || MAX_PICTURES;
    const slots = [...new Set([...expectedSlots, ...Array.from({length: MAX_PICTURES}, (_, i) => i + 1)])].filter(i => i <= limit);
    const available = slots.filter(i => !pictures.some(p => p.slot === i));
    const valid = Array.from(files).filter(f => ['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(f.type) && f.size <= 25 * 1024 * 1024);
    const added = Math.min(valid.length, available.length);
    setNotice(valid.length !== files.length ? tr('Use JPG, PNG, WebP or GIF (first frame), up to 25 MB each.', 'Use JPG, PNG, WebP ou GIF (primeiro quadro), até 25 MB por imagem.', 'Usa JPG, PNG, WebP o GIF (primer fotograma), hasta 25 MB por imagen.') : valid.length > available.length ? (mode === 'headswap' ? tr('Head Swap uses one face picture.', 'A troca de cabeça usa uma foto de rosto.', 'El cambio de cabeza usa una foto de rostro.') : tr(`Up to ${MAX_PICTURES} reference pictures.`, `Até ${MAX_PICTURES} imagens de referência.`, `Hasta ${MAX_PICTURES} imágenes de referencia.`)) : !maxPictures && added ? tr('Sharpness does not use pictures; they are kept for the other modes.', 'O Sharpness não usa imagens; elas ficam guardadas para os outros modos.', 'Sharpness no usa imágenes; se guardan para los otros modos.') : '');
    setPictures(current => [...current, ...valid.slice(0, available.length).map((file, i) => ({slot: available[i], file, url: URL.createObjectURL(file)}))].sort((a, b) => a.slot - b.slot));
    return added;
  }
  function addVideo(files: FileList | File[] | null, replace = false) {
    if (!files?.length) return;
    if (replace && video) URL.revokeObjectURL(video.url);
    else if (files.length > 1 || video) { setNotice(tr('Use one guide video. Remove the current guide to replace it.', 'Use um vídeo guia. Remova o atual para substituí-lo.', 'Usa un vídeo guía. Elimina el actual para reemplazarlo.')); return; }
    const file = files[0];
    if (file.type === 'image/gif') {void addGif(file); return;}
    if (!file.type.startsWith('video/') || file.size > 500 * 1024 * 1024) { setNotice(tr('Choose a video up to 500 MB.', 'Escolha um vídeo de até 500 MB.', 'Elige un vídeo de hasta 500 MB.')); return; }
    const signature = JSON.stringify([file.name, file.size, file.lastModified]);
    if (signature !== guideSignature) setSubjects(current => current.map(s => ({...s, anchors: []})));
    setGuideSignature(signature); setPickingId(null);
    setVideo({file, url: URL.createObjectURL(file)}); setEditingVideo(true); setNotice(''); startFresh();
  }
  /** A GIF guide is converted to MP4 by the backend (browsers cannot play GIF in <video>), then added as a video. */
  async function addGif(gif: File) {
    if (gif.size > 100 * 1024 * 1024) {setNotice(tr('Choose a GIF up to 100 MB.', 'Escolha um GIF de até 100 MB.', 'Elige un GIF de hasta 100 MB.')); return;}
    setNotice(tr('Converting the GIF to video…', 'Convertendo o GIF em vídeo…', 'Convirtiendo el GIF en vídeo…'));
    try {
      const body = new FormData(); body.set('gif', gif);
      const response = await fetch('/api/backend/convert-gif', {method: 'POST', body});
      if (!response.ok) throw Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
      addVideo([new File([await response.blob()], gif.name.replace(/\.gif$/i, '') + '.mp4', {type: 'video/mp4', lastModified: gif.lastModified})]);
    } catch (e) {setNotice(tr('This GIF could not be converted: ', 'Não foi possível converter este GIF: ', 'No se pudo convertir este GIF: ') + (e instanceof Error ? e.message : String(e)));}
  }
  async function openGenerated() {
    setGeneratedOpen(v => !v);
    try {
      const response = await fetch('/api/backend/jobs', {cache: 'no-store'});
      const rows: GeneratedVideo[] = await readJson(response);
      setGenerated(Array.isArray(rows) ? rows.filter(j => (j as {status?: string}).status === 'completed' && j.result_url) : []);
    } catch { setGenerated([]); }
  }
  /** Load a finished generation as the new source video, optionally switching mode (e.g. sharpen it). */
  async function useGenerated(item: GeneratedVideo, nextMode?: Mode) {
    setLoadingGenerated(item.id);
    try {
      const response = await fetch(item.result_url);
      if (!response.ok) throw Error();
      const name = `${(item.project || 'henge').replace(/[^\w.-]+/g, '-')}-${item.id.slice(0, 6)}.mp4`;
      addVideo([new File([await response.blob()], name, {type: 'video/mp4', lastModified: Math.round(item.created * 1000)})], true);
      if (nextMode) setMode(nextMode);
      setGeneratedOpen(false); setView('studio');
      return true;
    } catch { setNotice(tr('Could not load that video from the backend.', 'Não foi possível carregar esse vídeo do backend.', 'No se pudo cargar ese vídeo del backend.')); return false; }
    finally { setLoadingGenerated(null); }
  }
  function removeVideo() { if (video) URL.revokeObjectURL(video.url); setVideo(null); setPickingId(null); }
  function removeAllPictures() {
    pictures.forEach(p => URL.revokeObjectURL(p.url));
    setPictures([]); setExpectedSlots([]); setBringSlots([]);
    // Subjects keep their marks but lose the pictures they pointed to.
    setSubjects(current => current.map(s => ({...s, picture_slots: []})));
    if (firstFrameSlot) {setFirstFrameSlot(null); try {localStorage.removeItem(FIRST_FRAME_KEY);} catch {/* private mode */}}
  }
  function removePicture(slot: number) {
    const item = pictures.find(p => p.slot === slot);
    if (item) URL.revokeObjectURL(item.url);
    setPictures(pictures.filter(p => p.slot !== slot));
    if (slot === firstFrameSlot) {setFirstFrameSlot(null); try {localStorage.removeItem(FIRST_FRAME_KEY);} catch {/* private mode */}}
    setSubjects(current => current.map(s => ({...s, picture_slots: s.picture_slots.filter(n => n !== slot)})));
  }
  async function readPrompt() {
    setTranslating(true);
    try {
      const r = await fetch('/api/backend/prompt/translate', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({text: prompt, lang: readLang})});
      const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`);
      setTranslation({text: reply.text, lang: readLang, source: prompt});
    } catch (e) {setNotice(e instanceof Error ? e.message : String(e));} finally {setTranslating(false);}
  }
  async function autoPrompt() {
    const brief = prompt;
    if (!video?.range || editingVideo || !pictures.length || !brief.trim()) { setNotice(tr('Add a guide, references and a short brief.', 'Adicione um guia, referências e uma breve descrição.', 'Añade una guía, referencias y una breve descripción.')); return; }
    setWorking(true); setNotice('');
    try {
      const request = makeRequest(); if (!request) throw Error('Select a guide interval.');
      request.prompt = nativePrompt(brief + (subjects.length && !subjectErrors ? '\n' + bindingPrompt(subjects, guideRepresentation) : ''));
      request.editor_prompt = brief; setAutoSource(brief); setTranslation(null);
      const body = new FormData(); body.set('direction', JSON.stringify(request)); body.set('options', JSON.stringify({profile: mode === 'motion' ? 'motion' : 'character', adapt: 'auto', seed: 42, steps: 8, clip_fps: 2})); body.set('video', video.file);
      pictures.forEach(p => body.set(`picture_${p.slot}`, p.file));
      const response = await fetch('/api/backend/jobs', {method: 'POST', body}); const result = await readJson(response);
      if (!response.ok) throw Error(result.detail || result.error || 'Planning failed.');
      setGenerationJob(result); setPendingAutoPromptJob(result.id);
      setNotice(tr('Planning queued. The VLM prompt will appear when ready; review the plan before generating.', 'Planejamento na fila. O prompt do VLM aparecerá quando pronto; revise o plano antes de gerar.', 'Planificación en cola. El prompt aparecerá cuando esté listo; revisa el plan antes de generar.'));
    } catch (e) { setNotice(e instanceof Error ? e.message : 'Unable to generate a prompt.'); }
    finally { setWorking(false); }
  }
  function makeRequest(): DirectionRequest | null {
    if (!video?.range) return null;
    return {
      schema_version: 2, project: project.trim() || t.projectPh, mode, quality,
      processing: {mode: contextWindow ? 'context_window' : 'single', max_shots: 0, requested_seconds_per_shot: shotSeconds, frames_per_shot: shotFrames, timeline_fps: timelineFps, frame_grid: '17n+5', trim_to_source_length: true, join: 'ordered', execution_status: 'comfy_backend', context_frames: contextFrames, cut_mode: cutMode, ...(splitPoints.length ? {split_points: splitPoints} : {})},
      audio_conditioning: {enabled: audioConditioning, source: audioConditioning ? 'guide_video' : null},
      output_audio: {keep_source: keepAudio && !generateAudio, generate: generateAudio}, prompt: fixedRecipe ? '' : nativePrompt(executionPrompt), editor_prompt: fixedRecipe ? '' : prompt,
      // Sharpness uses only the video: subjects marked in another mode are not sent.
      subject_guidance: mode === 'sharpness' ? {representation: 'original', bindings: [], status: 'selection_only', marker_colors_are_output_appearance: false} : {representation: guideRepresentation, bindings: subjects, status: 'selection_only', marker_colors_are_output_appearance: false, ...(guideRepresentation === '2d' ? {mark_opacity: markOpacity, ...(markLabels ? {mark_labels: true} : {})} : {})},
      video: {name: video.file.name, source_signature: guideSignature, conditioning: 'guide_latents', source_duration: video.duration, start_seconds: video.range.start, end_seconds: video.range.end, duration: selectedDuration},
      pictures: activePictures.map(p => ({slot: p.slot, token: `<Picture ${p.slot}>`, name: p.file.name})),
      ...(mode === 'motion' && firstFrameSlot && activePictures.some(p => p.slot === firstFrameSlot) ? {first_frame_slot: firstFrameSlot} : {}), generation_status: 'not_submitted',
    };
  }
  async function importSettings(file?: File) {
    if (!file) return;
    try {
      if (file.size > 2 * 1024 * 1024) throw Error('File too large');
      const parsed = JSON.parse(await file.text());
      const direction = parsed.direction || parsed;
      const saved = {id: 'imported', created: new Date().toISOString(), request: direction, thumbnail: '', rating: 0, tags: []};
      if (!readHistory(JSON.stringify([saved])).length) throw Error('Invalid configuration');
      reuse(saved); setImportedSettings(parsed.generation && typeof parsed.generation === 'object' ? parsed.generation : {}); setImportRevision(v => v+1);
      setNotice(tr('Settings imported. Attach your video and reference pictures to generate.', 'Configuração importada. Anexe o vídeo e as imagens de referência para gerar.', 'Configuración importada. Añade el vídeo y las imágenes de referencia para generar.'));
    } catch {setNotice(tr('This file is not a valid Henge configuration.', 'Este arquivo não é uma configuração válida do Henge.', 'Este archivo no es una configuración válida de Henge.'));}
  }
  /** The direction's settings (mode, prompt, quality, shots, audio, subject guidance); media are left as they are. */
  useEffect(() => {if (mode !== 'sharpness') setQuality(q => ['1440p', '2160p'].includes(q) ? '1080p' : q);}, [mode]);
  useEffect(() => {setPickingId(null);}, [mode]);
  // Head Swap takes Original or Mask; Sharpness always uses the original video.
  useEffect(() => {if (mode === 'sharpness' || (mode === 'headswap' && ['2d', '3d'].includes(guideRepresentation))) setGuideRepresentation('original');}, [mode, guideRepresentation]);
  // The guide's own size: Sharpness should go above it, so it picks the next size up and warns otherwise.
  const [guideSize, setGuideSize] = useState<{width: number; height: number} | null>(null);
  useEffect(() => {
    setGuideSize(null); if (!video?.url) return;
    const probe = document.createElement('video'); probe.preload = 'metadata';
    probe.onloadedmetadata = () => {if (probe.videoWidth && probe.videoHeight) setGuideSize({width: probe.videoWidth, height: probe.videoHeight});};
    probe.src = video.url;
    return () => {probe.onloadedmetadata = null; probe.removeAttribute('src');};
  }, [video?.url]);
  useEffect(() => {
    if (mode !== 'sharpness' || !guideSize) return;
    const short = Math.min(guideSize.width, guideSize.height);
    setQuality(q => QUALITY_SHORT[q] > short ? q : Object.keys(QUALITY_SHORT).find(k => QUALITY_SHORT[k] > short) ?? q);
  }, [mode, guideSize]);
  const qualityRow = <div className="setting-row"><span>{t.quality}</span><div className="quality-options">{['480p', '720p', '1080p', ...(mode === 'sharpness' ? ['1440p', '2160p'] : [])].map(q => <button key={q} className={'mono nc ' + (quality === q ? 'chosen' : '')} aria-pressed={quality === q} onClick={() => setQuality(q)}>{q === '1440p' ? '2K' : q === '2160p' ? '4K' : q}</button>)}</div></div>;
  // The same guide is back (reload, re-upload or a restored job): bring back its edited first frame.
  useEffect(() => {
    if (!video || !guideSignature) return;
    let saved: {id: string; width: number; height: number; slot: number; guide: string} | null = null;
    try {saved = JSON.parse(localStorage.getItem(FIRST_FRAME_KEY) || 'null');} catch {/* private mode */}
    if (!saved || saved.guide !== guideSignature || pictures.some(p => p.slot === saved!.slot)) return;
    const {id, width, height, slot} = saved;
    coverFit(`/api/backend/frame-edits/${id}`, width, height).then(file => {
      setPictures(current => current.some(p => p.slot === slot) ? current : [...current, {slot, file, url: URL.createObjectURL(file)}].sort((a, b) => a.slot - b.slot));
      setFirstFrameSlot(slot); setRequestedProfile('motion_ffp');
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [video?.url, guideSignature]);
  function applyDirection(r: DirectionRequest) {
    if (MODES.includes(r.mode)) setMode(r.mode);
    if (['480p', '720p', '1080p', '1440p', '2160p'].includes(r.quality)) setQuality(r.quality);
    setSubjects(readSubjectBindings(r.subject_guidance?.bindings)); setGuideRepresentation(r.subject_guidance && ['2d', '3d', 'mask'].includes(r.subject_guidance.representation) ? r.subject_guidance.representation : 'original'); if (typeof r.subject_guidance?.mark_opacity === 'number') setMarkOpacity(r.subject_guidance.mark_opacity); setGuideSignature(r.video?.source_signature || '');
    if (typeof r.project === 'string') setProject(r.project);
    setFirstFrameSlot(typeof r.first_frame_slot === 'number' ? r.first_frame_slot : null);
    setPrompt(r.editor_prompt ?? r.prompt ?? ''); setAudioConditioning(r.audio_conditioning?.enabled === true);
    setKeepAudio(r.output_audio?.keep_source !== false);
    if (r.processing) {setShotSeconds(r.processing.requested_seconds_per_shot || 4.5); setTimelineFps(r.processing.timeline_fps || 24); setContextFrames(r.processing.context_frames || 22); if (r.processing.cut_mode) setCutMode(r.processing.cut_mode);}
  }
  /** A server job brings back its own guide (with the chosen interval) and pictures, e.g. after a page reload. */
  const restoring = useRef('');
  async function selectServerJob(r: DirectionRequest, id: string) {
    applyDirection(r); restoring.current = id;
    try {
      const fetchFile = async (name: string, filename: string, type: string, lastModified = Date.now()) => {
        const response = await fetch(`/api/backend/jobs/${id}/source/${name}`);
        if (!response.ok) throw Error();
        return new File([await response.blob()], filename, {type, lastModified});
      };
      let lastModified: number | undefined;
      try {const signature = JSON.parse(r.video?.source_signature || 'null'); if (Array.isArray(signature) && typeof signature[2] === 'number') lastModified = signature[2];} catch {/* no signature */}
      const [file, files] = await Promise.all([fetchFile('video', r.video?.name || 'guide.mp4', 'video/mp4', lastModified), Promise.all(r.pictures.map(p => fetchFile(`picture_${p.slot}`, p.name || `picture_${p.slot}.png`, 'image/png')))]);
      if (restoring.current !== id) return;
      setVideo(current => {if (current) URL.revokeObjectURL(current.url); return {file, url: URL.createObjectURL(file), range: {start: r.video.start_seconds, end: r.video.end_seconds}, duration: r.video.source_duration};});
      setPictures(current => {current.forEach(p => URL.revokeObjectURL(p.url)); return r.pictures.map((p, i) => ({slot: p.slot, file: files[i], url: URL.createObjectURL(files[i])}));});
      setExpectedSlots(r.pictures.map(p => p.slot)); setEditingVideo(false); setPickingId(null); setNotice('');
    } catch {/* media no longer on the server: the settings are still restored */}
  }
  /** New: an empty studio (media, people, prompt, template, selected generation). Mode, language and settings stay. */
  async function resetStudio() {
    const busyDraft = video || pictures.length || prompt.trim() || subjects.length;
    if (busyDraft && !await confirmDialog({tone: 'danger', title: tr('Start a new one?', 'Começar um novo?', '¿Empezar uno nuevo?'),
      message: tr('The video, pictures, marked people and prompt will be cleared. Mode, language and settings stay. Your generations stay in History.', 'O vídeo, as imagens, as pessoas marcadas e o prompt serão apagados. Modo, idioma e ajustes continuam. Suas gerações continuam no Histórico.', 'Se borrarán el video, las imágenes, las personas marcadas y el prompt. El modo, el idioma y los ajustes se mantienen. Tus generaciones siguen en el Historial.'),
      confirm: tr('Clear and start new', 'Limpar e começar', 'Borrar y empezar'), cancel: tr('Keep editing', 'Continuar editando', 'Seguir editando')})) return;
    removeVideo(); setGuideSignature(''); removeAllPictures(); setSubjects([]); setPrompt(''); setAutoSource(null); setPendingAutoPromptJob(null);
    setActiveTemplate(null); setProject(''); setNotice(''); setEditingVideo(false); startFresh();
  }
  function reuse(item: SavedDirection) {
    const r = item.request;
    removeVideo(); pictures.forEach(p => URL.revokeObjectURL(p.url)); setPictures([]);
    setExpectedSlots(r.pictures.map(p => p.slot)); applyDirection(r);
    setView('studio'); setAuto(false); setActiveTemplate(null);
    setNotice(tr('Settings restored. Reattach the guide and reference pictures to generate.', 'Ajustes restaurados. Anexe novamente o guia e as referências para gerar.', 'Ajustes restaurados. Vuelve a adjuntar la guía y las referencias para generar.'));
  }
  /** A community example: its guide (whole clip selected), references, mode and prompt; empty slots are the user's. */
  const [loadingCommunity, setLoadingCommunity] = useState<string | null>(null);
  async function useCommunity(preset: CommunityPreset, mode: Mode = preset.mode) {
    setLoadingCommunity(preset.id);
    try {
      const fetchFile = async (url: string, name: string, type: string) => {
        const response = await fetch(url);
        if (!response.ok) throw Error();
        return new File([await response.blob()], name, {type, lastModified: 0});
      };
      const base = `/community/${preset.id}`;
      const [file, files] = await Promise.all([fetchFile(`${base}/guide.mp4`, `${preset.id}.mp4`, 'video/mp4'), Promise.all(preset.refs.map(r => fetchFile(`${base}/ref_${r.slot}.jpg`, `${preset.id}_${r.slot}.jpg`, 'image/jpeg')))]);
      setMode(mode);
      setVideo(current => {if (current) URL.revokeObjectURL(current.url); return {file, url: URL.createObjectURL(file), range: {start: 0, end: preset.duration}, duration: preset.duration};}); startFresh();
      setPictures(current => {current.forEach(p => URL.revokeObjectURL(p.url)); return preset.refs.map((r, i) => ({slot: r.slot, file: files[i], url: URL.createObjectURL(files[i])}));});
      setExpectedSlots([...preset.refs, ...preset.bring].map(r => r.slot).sort((a, b) => a - b)); setBringSlots(preset.bring.map(b => ({slot: b.slot, label: b.label})));
      setGuideSignature(JSON.stringify([file.name, file.size, 0])); setSubjects([]); setGuideRepresentation('original');
      setPrompt(preset.prompt[lang]); setAuto(false); setActiveTemplate(null); setEditingVideo(false); setView('studio');
      setNotice(preset.bring.length
        ? tr(`Example loaded. Add your picture for ${preset.bring.map(b => `Picture ${b.slot} (${b.label.en})`).join(' and ')}, then generate.`, `Exemplo carregado. Adicione sua foto em ${preset.bring.map(b => `Imagem ${b.slot} (${b.label.pt})`).join(' e ')} e gere.`, `Ejemplo cargado. Añade tu foto en ${preset.bring.map(b => `Imagen ${b.slot} (${b.label.es})`).join(' y ')} y genera.`)
        : tr('Example loaded with its guide, references and prompt. Generate it or change anything first.', 'Exemplo carregado com guia, referências e prompt. Gere ou mude o que quiser antes.', 'Ejemplo cargado con guía, referencias y prompt. Genéralo o cambia lo que quieras antes.'));
      window.scrollTo({top: 0, behavior: 'smooth'});
    } catch { setNotice(tr('Could not load this example.', 'Não foi possível carregar este exemplo.', 'No se pudo cargar este ejemplo.')); }
    finally { setLoadingCommunity(null); }
  }
  function patchHistory(id: string, patch: Partial<Pick<SavedDirection, 'rating' | 'tags'>>) { setHistory(current => current.map(h => h.id === id ? {...h, ...patch} : h)); }
  function exportFeedback() {
    const rows = history.filter(h => h.rating).map(h => ({schema_version: 1, kind: 'direction_feedback', id: h.id, created: h.created, request: h.request, rating: h.rating, tags: h.tags, output_video: null}));
    const url = URL.createObjectURL(new Blob([rows.map(r => JSON.stringify(r)).join('\n') + '\n'], {type: 'application/x-ndjson'}));
    const a = document.createElement('a'); a.href = url; a.download = 'henge-direction-feedback.jsonl'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const dateLabel = (value: string) => new Intl.DateTimeFormat({en: 'en', pt: 'pt-BR', es: 'es'}[lang], {day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'}).format(new Date(value));
  const feedbackLabels = [tr('Clear identity', 'Identidade definida', 'Identidad definida'), tr('Clear motion', 'Movimento definido', 'Movimiento definido'), tr('Clear preservation', 'Preservação definida', 'Conservación definida'), tr('Prompt ready', 'Prompt pronto', 'Prompt listo')];
  const historyTitle = tr('Your directions', 'Suas direções', 'Tus direcciones');

  return <div className={`app-shell mode-${mode}`} style={style}>
    <SetupScreen lang={lang}/>
    <DialogHost/>
    {settingsOpen && <SettingsCenter lang={lang} wizard={settingsOpen.wizard} initialTab={settingsOpen.tab} onClose={() => setSettingsOpen(null)}/>}
    {!ready && <div className="boot-splash" role="status" aria-label="Loading Henge"><span className="brandmark"><Icon name="spark" size={28}/></span><strong>Henge</strong><span className="boot-bar"/></div>}
    {editSlot !== null && pictures.some(p => p.slot === editSlot) && <FirstFrameModal image={pictures.find(p => p.slot === editSlot)!.file} pictures={pictures.filter(p => p.slot !== editSlot)} lang={lang} onClose={() => setEditSlot(null)} onUse={file => {
      const slot = editSlot; setEditSlot(null);
      setPictures(current => current.map(p => p.slot === slot ? (URL.revokeObjectURL(p.url), {slot, file: new File([file], `picture_${slot}_edited.png`, {type: 'image/png'}), url: URL.createObjectURL(file)}) : p));
    }}/>}
    {frameModal && video?.range && <FirstFrameModal videoUrl={video.url} start={video.range.start} end={video.range.end} pictures={pictures.filter(p => p.slot !== firstFrameSlot)} lang={lang} onClose={() => setFrameModal(false)} onUse={(file, edit, at) => {
      const slot = firstFrameSlot ?? Array.from({length: maxPictures}, (_, i) => i + 1).find(i => !pictures.some(p => p.slot === i));
      if (!slot) {setNotice(tr('Remove a picture to make room for the first frame.', 'Remova uma Picture para abrir espaço para o primeiro quadro.', 'Quita una imagen para dejar espacio al primer fotograma.')); return;}
      setPictures(current => [...current.filter(p => {if (p.slot === slot) URL.revokeObjectURL(p.url); return p.slot !== slot;}), {slot, file, url: URL.createObjectURL(file)}].sort((a, b) => a.slot - b.slot));
      setFirstFrameSlot(slot); setRequestedProfile('motion_ffp'); setFrameModal(false);
      // FFP propagates from the clip's first frame: a later edited frame becomes the start of the interval.
      const moved = at !== undefined && video.range && at > video.range.start + .02 ? at : null;
      if (moved !== null) setVideo(v => v?.range ? {...v, range: {start: moved, end: v.range.end}} : v);
      // A frame edit lives on the bridge: remember it with this guide so a reload can bring it back.
      try {if (edit) localStorage.setItem(FIRST_FRAME_KEY, JSON.stringify({...edit, slot, guide: guideSignature})); else localStorage.removeItem(FIRST_FRAME_KEY);} catch {/* private mode */}
      if (moved !== null) {setNotice(tr(`Picture ${slot} is the edited frame; the interval now starts there (${moved.toFixed(2)} s), since the first-frame model propagates from the start.`, `A Imagem ${slot} é o quadro editado; o intervalo agora começa nele (${moved.toFixed(2)} s), porque o modelo propaga a partir do início.`, `La Imagen ${slot} es el fotograma editado; el intervalo ahora empieza en él (${moved.toFixed(2)} s), porque el modelo propaga desde el inicio.`)); return;}
      setNotice(tr(`Picture ${slot} is the edited first frame. The First-frame propagate model is selected; describe the edit in the prompt.`, `A Imagem ${slot} é o primeiro quadro editado. O modelo First-frame propagate foi selecionado; descreva a edição no prompt.`, `La Imagen ${slot} es el primer fotograma editado. Se seleccionó el modelo First-frame propagate; describe la edición en el prompt.`));
    }}/>}
    {editingVideo && video && <VideoTrimModal file={video.file} url={video.url} initial={video.range} onConfirm={(range, duration) => {setVideo(v => v ? {...v, range, duration} : v); setEditingVideo(false);}} onCancel={() => {if (!video.range) removeVideo(); setEditingVideo(false);}}/>}
    <header className="topbar">
      <button className="wordmark" onClick={() => setView('studio')} aria-label="Henge Studio"><span className="brandmark"><Icon name="spark" size={23}/></span><strong>Henge</strong><span className="alpha mono">Studio · α</span></button>
      <div className="project-field"><label className="mono" htmlFor="project-name">{t.project}</label><input id="project-name" value={project} onChange={e => setProject(e.target.value)} placeholder={t.projectPh}/></div>
      <nav className="main-nav" aria-label={tr('Main navigation', 'Navegação principal', 'Navegación principal')}>
        {(['studio', 'history', 'community'] as View[]).map(v => <button key={v} className={view === v ? 'active' : ''} onClick={() => setView(v)} aria-current={view === v ? 'page' : undefined}>{t[v]}{v === 'history' && history.length > 0 && <span className="count mono">{history.length}</span>}</button>)}
      </nav>
      <span className="draft-status"><i/>{t.draft}</span>
      <div className="topbar-end"><a className="source-link ghost guide-link" href="/guides/index.html" target="_blank" rel="noreferrer">{tr('Tips (PT)', 'Dicas', 'Consejos (PT)')}</a><button type="button" className="source-link ghost settings-button" aria-label={tr('Settings', 'Configurações', 'Configuración')} title={tr('Settings: connection, assistant, login', 'Configurações: conexão, assistente, login', 'Configuración: conexión, asistente, acceso')} onClick={() => setSettingsOpen({wizard: false, tab: 'connection'})}><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg></button><ThemeSwitcher lang={lang}/><AccessSettings lang={lang}/><div className="language-switch" role="group" aria-label="Language">{(['en', 'pt', 'es'] as Language[]).map(l => <button key={l} className={'mono ' + (lang === l ? 'active' : '')} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}</div><a className="source-link ghost" href="https://github.com/alisson-anjos/Henge" target="_blank" rel="noreferrer"><Icon name="github" size={16}/>{t.openSource}</a></div>
    </header>

    {/* Kept mounted on other tabs so the generation panel keeps its settings and selected job. */}
    <div className="studio-view" hidden={view !== 'studio'}>
      {ready && <AssistantPanel controller={assistantController} lang={lang} jobId={generationJob?.id}/>}
      <main className="workspace">
        <aside className="controls">
          <div className="create-heading rise"><div className="create-top"><span className="eyebrow accent">{t.create}</span><button type="button" className="quiet-button new-studio" onClick={resetStudio} disabled={busy} title={tr('Start over with an empty studio', 'Recomeçar com o estúdio vazio', 'Empezar de nuevo con el estudio vacío')}>↺ {tr('New', 'Novo', 'Nuevo')}</button></div><h1>{t[`h1a_${mode}`]}<br/><span>{t[`h1b_${mode}`]}</span></h1></div>
          <section className="mode-picker" aria-labelledby="mode-picker-title">
            <div className="mode-picker-heading"><span id="mode-picker-title" className="eyebrow">{t.mode}</span><span className="mono">{String(MODES.indexOf(mode) + 1).padStart(2, '0')} / {String(MODES.length).padStart(2, '0')}</span></div>
            <div className="mode-switch" role="group" aria-label={t.mode}>{MODES.map(m => <button key={m} disabled={!ready || busy} className={mode === m ? 'selected' : ''} onClick={() => {setMode(m); setKeepAudio(true);}} aria-pressed={mode === m} style={accentVars(m, 'mode') as CSSProperties}><span className="mode-icon"><Icon name={m} size={18}/></span><span className="mode-copy"><strong>{modeName(m)}</strong><small>{modeHint(m)}</small></span><span className="mode-selected"><Icon name="check" size={12}/></span></button>)}</div>
            <p className="mode-description"><span className="mode-description-dot"/>{modeDescription}</p>
          </section>
          {mode === 'sharpness' && <section className="input-card surface output-settings target-resolution"><div className="label-row"><h2>{tr('Target resolution', 'Resolução final', 'Resolución final')}</h2></div>{qualityRow}
            {guideSize && (() => {const [w, h] = outputSize(guideSize.width, guideSize.height, QUALITY_SHORT[quality], QUALITY_SHORT[quality] > 720); return <div className="resolution-summary mono nc"><div><span className="eyebrow muted">{tr('Source', 'Origem', 'Origen')}</span><strong>{guideSize.width}×{guideSize.height}</strong></div><span className="muted">→</span><div><span className="eyebrow muted">{tr('Target', 'Alvo', 'Destino')}</span><strong className="accent">{w}×{h}</strong></div>{QUALITY_SHORT[quality] > 720 && <small className="muted">{tr(`render ${w / 2}×${h / 2} → ×2`, `render ${w / 2}×${h / 2} → ×2`, `render ${w / 2}×${h / 2} → ×2`)}</small>}</div>;})()}
            {guideSize && QUALITY_SHORT[quality] <= Math.min(guideSize.width, guideSize.height) && <p className="validation" role="alert">{tr(`Your video is already ${Math.min(guideSize.width, guideSize.height)}p. Choose a larger size, or the result will not gain resolution.`, `Seu vídeo já está em ${Math.min(guideSize.width, guideSize.height)}p. Escolha um tamanho maior, senão o resultado não ganha resolução.`, `Tu vídeo ya está en ${Math.min(guideSize.width, guideSize.height)}p. Elige un tamaño mayor o el resultado no ganará resolución.`)}</p>}
            {['1080p', '1440p', '2160p'].includes(quality) && <small className="muted">{tr('Sharpened at half size, then doubled to this size by the H3 or NVIDIA upscaler (Advanced → Sharpness).', 'Nitidez em meia resolução, depois dobrada até este tamanho pelo upscaler H3 ou NVIDIA (Avançado → Nitidez).', 'Nitidez a media resolución, luego duplicada a este tamaño por el escalador H3 o NVIDIA (Avanzado → Nitidez).')}</small>}</section>}
          {chosenTemplate && <div className="active-template surface"><Icon name="spark"/><div><span className="eyebrow accent">{t.tplActive}</span><strong>{chosenTemplate.title[lang]}</strong></div><button className="icon-btn" aria-label={t.exitTpl} onClick={() => setActiveTemplate(null)}><Icon name="close" size={15}/></button></div>}
          <section className="input-card surface">
            <div className="label-row"><h2><span className="step-number">01</span>{t.guide}</h2><span className="mono muted">{video ? '01' : '00'} / 01</span></div>
            <input data-testid="guide-input" hidden ref={videoInput} type="file" accept="video/*,image/gif" onChange={e => {addVideo(e.target.files); e.target.value = '';}}/>
            <div className={'video-drop ' + (video ? 'has-file' : '')} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); addVideo(e.dataTransfer.files);}}>
              {video ? <><span className="file-icon"><Icon name="film"/></span><div><strong>{video.file.name}</strong><small>{(video.file.size / 1048576).toFixed(1)} MB · {selectedDuration.toFixed(1)}s {t.selected}</small></div><button className="icon-btn" aria-label={tr('Edit video interval', 'Editar intervalo do vídeo', 'Editar intervalo del vídeo')} onClick={() => setEditingVideo(true)}><Icon name="scissors" size={16}/></button><button className="icon-btn" aria-label={tr('Remove video', 'Remover vídeo', 'Eliminar vídeo')} onClick={removeVideo}><Icon name="close" size={16}/></button></> : <button className="drop-button" onClick={() => videoInput.current?.click()}><span className="upload-icon"><Icon name="upload"/></span><strong>{t.drop}</strong><small>{t.dropSub}</small></button>}
            </div>
            <button className="text-link generated-toggle" aria-expanded={generatedOpen} onClick={openGenerated}><Icon name="film" size={14}/>{tr('Use a video generated in the studio', 'Usar um vídeo gerado no estúdio', 'Usar un vídeo generado en el estudio')}</button>
            {generatedOpen && <div className="generated-picker">{generated === null ? <small className="muted">{tr('Loading…', 'Carregando…', 'Cargando…')}</small> : generated.length ? generated.slice(0, 12).map(item => <button key={item.id} disabled={!!loadingGenerated} onClick={() => useGenerated(item)}><video muted playsInline preload="metadata" src={item.result_url + '#t=0.5'}/><span><strong>{item.project || 'Henge'}</strong><small className="mono">{item.mode ? modeName(item.mode) : ''}{item.duration ? ` · ${item.duration.toFixed(1)}s` : ''}</small></span>{loadingGenerated === item.id && <small className="muted">…</small>}</button>) : <small className="muted">{tr('No finished generations yet.', 'Nenhuma geração concluída ainda.', 'Aún no hay generaciones terminadas.')}</small>}</div>}
            {video?.range && <button className="interval-summary" onClick={() => setEditingVideo(true)}><Icon name="scissors" size={14}/><span className="mono nc">{formatTime(video.range.start)} → {formatTime(video.range.end)}</span><span className="accent mono nc">{selectedDuration.toFixed(1)}s</span></button>}
            {video?.range && (molmoReady || splitPoints.length > 0) && <div className="split-points"><span>{tr('Split points', 'Pontos de corte', 'Puntos de corte')}: {splitPoints.length ? <b className="mono">{splitPoints.map(p => p.toFixed(1) + ' s').join(' · ')}</b> : <span className="muted">{tr('automatic', 'automáticos', 'automáticos')}</span>}</span>
              <span className="split-actions"><button type="button" className="text-link" disabled={suggesting || working || generationActive} onClick={async () => {const id=crypto.randomUUID(), controller=new AbortController(); suggestRequest.current={id,controller}; setSuggesting(true); try {const r = await suggestSplits(shotSeconds,id,controller.signal); setSplitPoints(r.points); setNotice(r.points.length ? tr(`Molmo2 split the shots at ${r.points.join(', ')} s (max ${shotSeconds} s per shot).`, `O Molmo2 dividiu os trechos em ${r.points.join(', ')} s (máx. ${shotSeconds} s por trecho).`, `Molmo2 dividió los tramos en ${r.points.join(', ')} s (máx. ${shotSeconds} s por tramo).`) : tr('Molmo2 found no better split points: the shots follow the camera cuts and the length.', 'O Molmo2 não achou pontos melhores: os trechos seguem os cortes e o comprimento.', 'Molmo2 no encontró mejores puntos: los tramos siguen los cortes y la duración.'));} catch (e) {if (!(e instanceof DOMException && e.name === 'AbortError')) setNotice(e instanceof Error ? e.message : String(e));} finally {if(suggestRequest.current?.id===id)suggestRequest.current=null; setSuggesting(false);}}}>{suggesting ? tr('Molmo2 is watching…', 'O Molmo2 está assistindo…', 'Molmo2 está viendo…') : tr('Suggest with Molmo2', 'Sugerir com o Molmo2', 'Sugerir con Molmo2')}</button>
              {suggesting && <button type="button" className="text-link" onClick={cancelSuggestion}>{tr('Cancel', 'Cancelar', 'Cancelar')}</button>}
              {splitPoints.length > 0 && <button type="button" className="text-link" onClick={() => setSplitPoints([])}>{tr('Clear', 'Limpar', 'Borrar')}</button>}</span></div>}
            {video && !contextWindow && <label className="cut-mode-field short-cut-mode">{tr('Camera cuts', 'Cortes de câmera', 'Cortes de cámara')}<Select value={cutMode} onChange={e => setCutMode(e.target.value as CutMode)}>{(['fit', 'every', 'off'] as CutMode[]).map(m => <option key={m} value={m}>{cutModeLabel(m, lang)}</option>)}</Select><small className="muted">{tr('Up to 15 s is one shot, unless you choose a shot at every cut (automatic when people are marked).', 'Até 15 s é um trecho só, a menos que você escolha um trecho por corte (automático com pessoas marcadas).', 'Hasta 15 s es un solo tramo, salvo que elijas un tramo por corte (automático con personas marcadas).')}</small></label>}
            {contextWindow && <details className="context-window-panel" open><summary><Icon name="scissors" size={16}/><strong>{t.autoCut}</strong><span className="mini-badge">{t.unlimited}</span></summary><p>{tr('This interval uses short segments joined in order.', 'Este intervalo usa segmentos curtos unidos em sequência.', 'Este intervalo usa segmentos cortos unidos en orden.')}</p><div className="shot-settings"><label>{t.fixedLabel}<input aria-label={t.fixedLabel} type="number" min="1" max="15" step="0.1" value={shotSeconds} onChange={e => setShotSeconds(Math.min(15, Math.max(1, Number(e.target.value) || 4.5)))}/></label><label>Timeline FPS<input aria-label="Timeline FPS" type="number" min="1" max="120" value={timelineFps} onChange={e => setTimelineFps(Math.min(120, Math.max(1, Number(e.target.value) || 24)))}/></label></div><div className="label-row"><span>{t.ctxLen}</span><div className="context-options">{[5, 22, 39].map(f => <button key={f} aria-pressed={contextFrames === f} className={contextFrames === f ? 'chosen' : ''} onClick={() => setContextFrames(f)}>{f}f</button>)}</div></div><label className="cut-mode-field">{tr('Camera cuts', 'Cortes de câmera', 'Cortes de cámara')}<Select value={cutMode} onChange={e => setCutMode(e.target.value as CutMode)}>{(['fit', 'every', 'off'] as CutMode[]).map(m => <option key={m} value={m}>{cutModeLabel(m, lang)}</option>)}</Select></label><small className="muted">{shotFrames}f · 17n+5 · {cutMode === 'every' ? tr('a shot per camera cut', 'um trecho por corte de câmera', 'un tramo por corte de cámara') : `~${estimatedShots} ${t.cutsWord}`}</small></details>}
          </section>
          {maxPictures > 0 && <section className={'input-card surface reference-dropzone ' + (draggingPictures ? 'dragging' : '')} onDragEnter={e => {e.preventDefault(); if (e.dataTransfer.types.includes('Files')) {pictureDragDepth.current++; setDraggingPictures(true);}}} onDragOver={e => {e.preventDefault(); e.dataTransfer.dropEffect = 'copy';}} onDragLeave={e => {e.preventDefault(); pictureDragDepth.current = Math.max(0, pictureDragDepth.current - 1); if (!pictureDragDepth.current) setDraggingPictures(false);}} onDrop={e => {e.preventDefault(); e.stopPropagation(); pictureDragDepth.current = 0; setDraggingPictures(false); addPictures(e.dataTransfer.files);}}>
            <div className="label-row"><h2><span className="step-number">02</span>{mode === 'headswap' ? tr('Face reference', 'Rosto de referência', 'Rostro de referencia') : t.refs}</h2><span className="ref-header-end">{pictures.length > 0 && <button type="button" className="text-link remove-all-refs" onClick={removeAllPictures}>{tr('Remove all', 'Remover todas', 'Quitar todas')}</button>}<span className="mono muted">{String(activePictures.length).padStart(2, '0')} / {String(maxPictures).padStart(2, '0')}</span></span></div>
            <input data-testid="picture-input" hidden ref={imageInput} type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple onChange={e => {addPictures(e.target.files); e.target.value = '';}}/>
            <div className="reference-grid">{activePictures.map(p => <div className="reference" key={p.slot}><img draggable={false} src={p.url} alt={`Picture ${p.slot}: ${p.file.name}`}/><button className="remove-ref" aria-label={`Remove Picture ${p.slot}`} onClick={() => removePicture(p.slot)}><Icon name="close" size={11}/></button><button className="edit-ref" title={tr('Edit with FLUX Klein', 'Editar com FLUX Klein', 'Editar con FLUX Klein')} aria-label={tr(`Edit Picture ${p.slot}`, `Editar Picture ${p.slot}`, `Editar Picture ${p.slot}`)} onClick={() => setEditSlot(p.slot)}><Icon name="image" size={11}/></button><button className="ref-label mono nc" onClick={() => insertTag(`@Picture${p.slot}`)}>@Picture{p.slot}</button>{p.slot === firstFrameSlot && <span className="first-frame-badge mono">{tr('1st frame', '1º quadro', '1er fotograma')}</span>}</div>)}{bringSlots.filter(b => b.slot <= maxPictures && !pictures.some(p => p.slot === b.slot)).map(b => <button key={`bring-${b.slot}`} className="add-reference bring-reference" onClick={() => imageInput.current?.click()}><Icon name="plus" size={18}/><span className="mono">@Picture{b.slot}</span><small>{b.label[lang]} · {tr('add your photo', 'adicione sua foto', 'añade tu foto')}</small></button>)}{activePictures.length < maxPictures && !bringSlots.some(b => !pictures.some(p => p.slot === b.slot)) && <button className="add-reference" onClick={() => imageInput.current?.click()}><Icon name="plus" size={18}/><span>{t.add}</span></button>}</div>
            {mode === 'motion' && video?.range && <details className="ffp-card" open={!!firstFrameSlot}><summary><span className="ffp-head"><span className="eyebrow accent">FFP · {tr('FRAME PROPAGATE', 'PROPAGAR UM QUADRO', 'PROPAGAR UN FOTOGRAMA')}</span><span className="mini-badge">{tr('optional', 'opcional', 'opcional')}</span></span>
              <strong>{tr('Edit one frame, the whole video follows', 'Edite um quadro, o vídeo inteiro acompanha', 'Edita un fotograma, todo el vídeo lo sigue')}</strong></summary>
              <ul className="ffp-points">
                <li>{tr('Pick any frame of the guide, then replace, remove or add something, or paint the area, with FLUX Klein. You can also upload your own edited frame.', 'Escolha qualquer quadro do guia e substitua, remova ou adicione algo, ou pinte a área, com o FLUX Klein. Também dá para enviar o seu próprio quadro editado.', 'Elige cualquier fotograma de la guía y reemplaza, quita o añade algo, o pinta el área, con FLUX Klein. También puedes subir tu propio fotograma editado.')}</li>
                <li>{tr('The video starts at that frame and the edit is carried through every frame after it.', 'O vídeo começa nesse quadro e a edição é levada para todos os quadros seguintes.', 'El vídeo empieza en ese fotograma y la edición se lleva a todos los siguientes.')}</li>
              </ul>
              <small>{tr('Model: FFP LoRA (SolarRenderer merge, dyn99 or the lighter dyn95).', 'Modelo: LoRA FFP (merge com SolarRenderer, dyn99 ou o mais leve dyn95).', 'Modelo: LoRA FFP (mezcla con SolarRenderer, dyn99 o el más ligero dyn95).')}</small>
              {firstFrameSlot && pictures.find(p => p.slot === firstFrameSlot) && <div className="ffp-current"><img src={pictures.find(p => p.slot === firstFrameSlot)!.url} alt=""/><span>{tr(`Picture ${firstFrameSlot} · edited frame`, `Imagem ${firstFrameSlot} · quadro editado`, `Imagen ${firstFrameSlot} · fotograma editado`)}</span></div>}
              <div className="ffp-actions"><button className="primary first-frame-button" onClick={() => setFrameModal(true)}><Icon name="image" size={14}/>{firstFrameSlot ? tr('Change the edited frame', 'Trocar o quadro editado', 'Cambiar el fotograma editado') : tr('Choose and edit a frame', 'Escolher e editar um quadro', 'Elegir y editar un fotograma')}</button>
              {firstFrameSlot && <button type="button" className="text-link" onClick={() => {setFirstFrameSlot(null); try {localStorage.removeItem(FIRST_FRAME_KEY);} catch {/* private mode */}}}>{tr('Don’t propagate', 'Não propagar', 'No propagar')}</button>}</div></details>}
            <p className="micro-copy">{draggingPictures ? tr('Drop to add references', 'Solte para adicionar referências', 'Suelta para añadir referencias') : mode === 'headswap' ? tr('One clear photo of the new face. The head is placed on the person in the video.', 'Uma foto nítida do novo rosto. A cabeça é aplicada na pessoa do vídeo.', 'Una foto nítida del nuevo rostro. La cabeza se aplica a la persona del vídeo.') : tr('JPG, PNG, WebP, GIF · 25 MB each. Slots keep their numbers.', 'JPG, PNG, WebP, GIF · 25 MB cada. Os slots mantêm seus números.', 'JPG, PNG, WebP, GIF · 25 MB cada. Los slots conservan sus números.')}</p>
          </section>}
          {(mode === 'swap' || mode === 'motion') && video?.range && <section className="input-card surface background-card">
            <div className="label-row"><h2><span className="step-number">+</span>{tr('New background', 'Novo cenário', 'Nuevo fondo')}</h2><span className="mini-badge">{tr('optional', 'opcional', 'opcional')}</span></div>
            <input data-testid="background-input" hidden ref={backgroundInput} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => {const f = e.target.files?.[0]; if (f) setBackground({file: f, url: URL.createObjectURL(f)}); e.target.value = '';}}/>
            {background ? <div className="reference background-thumb"><img draggable={false} src={background.url} alt={tr('New background', 'Novo cenário', 'Nuevo fondo')}/><button className="remove-ref" aria-label={tr('Remove the new background', 'Remover o novo cenário', 'Quitar el nuevo fondo')} onClick={() => setBackground(null)}>×</button></div>
              : <button className="quiet-button" onClick={() => backgroundInput.current?.click()}><Icon name="image" size={14}/>{tr('Add a background picture', 'Adicionar uma imagem de cenário', 'Añadir una imagen de fondo')}</button>}
            <p className="micro-copy">{tr('Moving plate: the people stay as they are and this picture replaces what is behind them, moving with the original camera (tracked on the background), before generation.', 'Moving plate: as pessoas ficam como estão e esta imagem substitui o que está atrás delas, movendo junto com a câmera original (rastreada no fundo), antes da geração.', 'Moving plate: las personas quedan igual y esta imagen sustituye lo que hay detrás, moviéndose con la cámara original, antes de generar.')}</p>
          </section>}
          <section className="input-card surface generation-settings-card" id="generation-settings"/>
          <section className="input-card surface output-settings"><div className="label-row"><h2><span className="step-number">03</span>{t.output}</h2></div>{mode !== 'sharpness' && qualityRow}
            <div className="setting-row"><label htmlFor="keep-audio">{t.audio}</label><button id="keep-audio" className="toggle" role="switch" aria-label={t.audio} aria-checked={keepAudio && !generateAudio} onClick={() => {setKeepAudio(v => !v); setGenerateAudio(false);}}><span/></button></div>
            <small className="setting-help">{tr('Copies the guide video’s sound into the result, unchanged. Off: the result is silent.', 'Copia o som do vídeo guia para o resultado, sem mudar nada. Desligado: o resultado sai sem som.', 'Copia el sonido del vídeo guía al resultado, sin cambios. Desactivado: el resultado sale sin sonido.')}</small>
            <div className="setting-row"><label htmlFor="generate-audio">{tr('Generated audio (H3)', 'Áudio gerado (H3)', 'Audio generado (H3)')}</label><button id="generate-audio" className="toggle" role="switch" aria-label={tr('Generated audio (H3)', 'Áudio gerado (H3)', 'Audio generado (H3)')} aria-checked={generateAudio} onClick={() => setGenerateAudio(v => !v)}><span/></button></div>
            <small className="setting-help">{tr('Keeps the sound H3 generates with each shot (footsteps, impacts, ambience, and lines you write in the prompt as <d>[language] text</d>), joined at the cuts. Replaces the guide’s sound. Needs the audio model (profile audio).', 'Mantém o som que o H3 gera em cada shot (passos, impactos, ambiente e falas que você escrever no prompt como <d>[idioma] texto</d>), juntado nos cortes. Substitui o som do guia. Precisa do modelo de áudio (perfil audio).', 'Conserva el sonido que H3 genera en cada toma (pasos, golpes, ambiente y frases que escribas como <d>[idioma] texto</d>), unido en los cortes. Sustituye el sonido de la guía. Necesita el modelo de audio (perfil audio).')}</small>
            <div className="setting-row"><label htmlFor="audio-conditioning">{tr('Audio conditioning', 'Condicionamento de áudio', 'Condicionamiento de audio')}</label><button id="audio-conditioning" className="toggle" role="switch" aria-label={tr('Audio conditioning', 'Condicionamento de áudio', 'Condicionamiento de audio')} aria-checked={audioConditioning} onClick={() => setAudioConditioning(v => !v)}><span/></button></div>
            <small className="setting-help">{tr('Also feeds that sound to the video model, so mouths, rhythm and beats follow it (speech, singing, dance). Needs a guide with audio; leave it off for silent clips.', 'Também envia esse som ao modelo de vídeo, para que boca, ritmo e batidas o acompanhem (fala, canto, dança). Precisa de um guia com áudio; deixe desligado em clipes sem som.', 'También envía ese sonido al modelo de vídeo, para que boca, ritmo y golpes lo sigan (habla, canto, baile). Necesita una guía con audio; déjalo desactivado en clips sin sonido.')}</small>
            <div className="model-badge"><span className="model-symbol"><Icon name="spark" size={19}/></span><div><strong>MiniMax H3</strong><small>{mode === 'sharpness' ? 'Little More Sharpness' : t.model}</small></div><span className="mono nc muted">{quality}</span></div>
          </section>
        </aside>

        <section className="canvas-column">
          <div className="canvas-toolbar"><span><i className="status-dot"/>{t.workspace}<small className="mono muted">/ {modeName(mode)}</small></span><span className="mono muted">{working ? tr('Building prompt', 'Criando prompt', 'Creando prompt') : video ? tr('Source preview', 'Prévia do guia', 'Vista previa de la guía') : t.stIdle}</span></div>
          <div className={'stage ' + (video ? 'has-video' : '')}>
            <div className="blob blob-a"/><div className="blob blob-b"/>
            {!video ? <div className="empty-stage"><div className="ring ring-one"/><div className="ring ring-two"/><div className="orbit-dot"/><div className="stage-message"><span className="eyebrow accent">{t.idleKicker}</span><h2>{t[`idleTitle1_${mode}`]}<br/><span>{t[`idleTitle2_${mode}`]}</span></h2><p>{t[`idleSub_${mode}`]}</p><button className="quiet-button" onClick={() => videoInput.current?.click()}><Icon name="plus" size={17}/>{t.addVideo}</button></div></div> : <div className="preview-panes"><div className="source-pane"><span className="badge mono">{t.source}</span><SubjectVideo url={video.url} range={video.range} subjects={mode === 'sharpness' ? [] : subjects} pickingId={mode === 'sharpness' ? null : pickingId} onAnchor={(id, anchor) => {setSubjects(current => current.map(s => s.id === id ? {...s, anchors: [...s.anchors.filter(a => Math.abs(a.time_seconds - anchor.time_seconds) > .05), anchor]} : s)); setPickingId(null);}} onDuration={(duration, width, height) => {setVideo(v => v?.url === video.url ? {...v, duration} : v); if (width && height) setGuideSize({width, height});}}/>{video.range && <span className="badge range-label mono nc">{formatTime(video.range.start)} / {formatTime(video.range.end)}</span>}</div><div className="output-pane"><span className="badge mono accent">{t.outputLabel}</span>{generationJob && !['completed','failed','cancelled','awaiting_approval'].includes(generationJob.status) ? <div className="live-stage">{generationJob.sampling_preview_url ? <><img src={generationJob.sampling_preview_url} alt={tr('Live generation preview', 'Prévia da geração ao vivo', 'Vista previa en vivo')}/><span className="live-caption">{tr('Live preview · approximate', 'Prévia ao vivo · aproximada', 'Vista previa en vivo · aproximada')}</span></> : <Icon name="spark" size={42}/>}<JobProgress job={generationJob} lang={lang}/></div> : generationJob?.result_url ? <div className="result-stage"><video key={generationJob.id} controls playsInline src={generationJob.result_url}/><div className="result-toolbar">
                <div className="result-row">
                  <a className="primary result-download" href={generationJob.result_url} download="henge-result.mp4"><Icon name="download" size={15}/>{tr('Download video', 'Baixar vídeo', 'Descargar vídeo')}</a>
                  <details className="result-more">
                    <summary className="quiet-button">{tr('More', 'Mais', 'Más')}<span aria-hidden="true" className="result-caret">▾</span></summary>
                    <div className="result-menu" role="menu" onClick={e => {(e.currentTarget.parentElement as HTMLDetailsElement).open = false;}}>
                      {generationJob.comparison_url && <a role="menuitem" href={generationJob.comparison_url} download="henge-comparison.mp4"><Icon name="film" size={14}/><span>{tr('Comparison', 'Comparação', 'Comparación')}<small>{tr('Guide and result side by side', 'Guia e resultado lado a lado', 'Guía y resultado lado a lado')}</small></span></a>}
                      {generationJob.comparison_url && <a role="menuitem" href={`/api/backend/jobs/${generationJob.id}/comparison-with-refs`} download="henge-guide-result-references.mp4"><Icon name="pictures" size={14}/><span>{tr('Comparison + references', 'Comparação + referências', 'Comparación + referencias')}<small>{tr('Adds the reference pictures', 'Inclui as imagens de referência', 'Incluye las imágenes de referencia')}</small></span></a>}
                      <a role="menuitem" href={`/api/backend/jobs/${generationJob.id}/bundle.zip`} download={`henge-${generationJob.id.slice(0, 8)}.zip`}><Icon name="download" size={14}/><span>{tr('Everything (.zip)', 'Tudo (.zip)', 'Todo (.zip)')}<small>{tr('Every asset of this generation in one file', 'Todos os arquivos desta geração em um só', 'Todos los archivos de esta generación en uno')}</small></span></a>
                      <a role="menuitem" href={`/api/backend/jobs/${generationJob.id}/workflow?stage=h3_segment_000`} download><Icon name="code" size={14}/><span>{tr('ComfyUI workflow', 'Workflow do ComfyUI', 'Workflow de ComfyUI')}<small>{tr('Drag the file into ComfyUI to open it', 'Arraste o arquivo para o ComfyUI', 'Arrastra el archivo a ComfyUI')}</small></span></a>
                    </div>
                  </details>
                </div>
                <div className="result-row result-next">
                  <span className="eyebrow muted">{tr('Continue with', 'Continuar com', 'Continuar con')}</span>
                  {(['sharpness', 'headswap'] as Mode[]).map(m => <button key={m} className="quiet-button" disabled={!!loadingGenerated} onClick={() => useGenerated({id: generationJob.id, project: generationJob.project, result_url: generationJob.result_url!, created: generationJob.created}, m)}><Icon name={m} size={14}/>{m === 'sharpness' ? tr('Sharpen', 'Deixar nítido', 'Dar nitidez') : tr('Head swap', 'Trocar a cabeça', 'Cambiar la cabeza')}</button>)}
                </div>
              </div></div> : <><Icon name="spark" size={42}/><p>{(generationJob?.error && readableError(generationJob.error).summary) || generationJob?.message || tr('Upload your media and plan the edit below.', 'Envie suas mídias e planeje a edição abaixo.', 'Sube tus medios y planifica la edición abajo.')}</p><span className="status-pill">{generationJob ? jobStatusLabel(generationJob.status,lang) : tr('Ready to plan', 'Pronto para planejar', 'Listo para planificar')}</span></>}</div></div>}
            {working && <div className="jutsu-loading" role="status"><div className="jutsu-seal"><i/><i/><Icon name="spark" size={42}/></div><strong>{tr('Directing your scene', 'Preparando sua direção', 'Preparando tu dirección')}</strong><small>{tr('Reading references and sampled guide frames', 'Lendo referências e quadros do vídeo guia', 'Leyendo referencias y fotogramas de la guía')}</small></div>}
            <span className="stage-corner mono">Henge / {modeName(mode)}</span>
          </div>
          {video?.range && (!fixedRecipe || mode === 'headswap') && <SubjectBindings subjects={subjects} onChange={setSubjects} representation={guideRepresentation} onRepresentation={setGuideRepresentation} pictures={pictures} lang={lang} pickingId={pickingId} onPick={setPickingId} onPrompt={() => setNative(true)} mode={mode} markOpacity={markOpacity} onMarkOpacity={setMarkOpacity} markLabels={markLabels} onMarkLabels={setMarkLabels}/>}
          {mode !== 'sharpness' && subjects.length > 0 && subjectErrors && <p className="validation" role="status">{tr('Mark each subject inside the selected interval and attach its references.', 'Marque cada personagem dentro do intervalo selecionado e vincule suas referências.', 'Marca cada personaje dentro del intervalo seleccionado y vincula sus referencias.')}</p>}
          <section className="creation-card surface" aria-label={tr('Create video', 'Criar vídeo', 'Crear vídeo')}><section className="prompt-card"><div className="prompt-header"><h2><Icon name="spark" size={16}/>{t.direct}</h2>{!fixedRecipe && <div className="editor-tabs prompt-modes" role="group" aria-label={tr('Prompt mode', 'Modo do prompt', 'Modo del prompt')}>{([['improve', tr('Improve', 'Melhorar', 'Mejorar')], ['auto', 'Auto Prompt'], ['exact', tr('Exact text', 'Texto exato', 'Texto exacto')]] as const).map(([value, label]) => <button key={value} aria-pressed={promptMode === value} className={promptMode === value ? 'active' : ''} onClick={() => setPromptMode(value)}>{label}</button>)}</div>}</div>
            {!fixedRecipe && <p className="prompt-mode-help">{promptMode === 'improve'
              ? tr('Write the idea in any language. At Generate the AI rewrites it in English in the H3 format, and the plan shows the final prompt for review before rendering.', 'Escreva a ideia em qualquer idioma. Ao gerar, a IA reescreve em inglês no formato do H3, e o plano mostra o prompt final para revisão antes do render.', 'Escribe la idea en cualquier idioma. Al generar, la IA la reescribe en inglés en el formato de H3, y el plan muestra el prompt final para revisarlo antes del render.')
              : promptMode === 'auto'
              ? tr('Write the idea in any language and press "Write the prompt now": the final English prompt replaces it here, to read (in your language too), edit or undo. Generate then sends it as is.', 'Escreva a ideia em qualquer idioma e clique em "Escrever o prompt agora": o prompt final em inglês aparece aqui no lugar, para ler (também no seu idioma), editar ou desfazer. Ao gerar, ele vai como está.', 'Escribe la idea en cualquier idioma y pulsa "Escribir el prompt ahora": el prompt final en inglés aparece aquí, para leerlo (también en tu idioma), editarlo o deshacerlo. Al generar se envía tal cual.')
              : tr('Your text goes to the model exactly as written (write it in English). The plan still runs to read the pictures and the video.', 'Seu texto vai ao modelo exatamente como está (escreva em inglês). O plano ainda roda para ler as imagens e o vídeo.', 'Tu texto llega al modelo tal cual (escríbelo en inglés). El plan sigue ejecutándose para leer las imágenes y el vídeo.')}</p>}
            {fixedRecipe && <div className="fixed-recipe"><p>{mode === 'headswap'
              ? tr('The prompt is written for you: the published head_swap: template, with the facial details of Picture 1 described by the VLM. You review those details before generating.', 'O prompt é escrito para você: o template head_swap: publicado, com os detalhes do rosto da Imagem 1 descritos pelo VLM. Você revisa esses detalhes antes de gerar.', 'El prompt se escribe por ti: la plantilla head_swap: publicada, con los rasgos de la Imagen 1 descritos por el VLM. Revisas esos detalles antes de generar.')
              : tr('No prompt needed. MiniMax H3 with the Little More Sharpness LoRA runs on its trained caption, with the source video as guide. For 2K/4K it sharpens at half size and doubles it (H3 or NVIDIA upscaler).', 'Não precisa de prompt. O MiniMax H3 com o LoRA Little More Sharpness roda com a legenda do treino e o vídeo de origem como guia. Em 2K/4K ele deixa nítido em meia resolução e dobra (upscaler H3 ou NVIDIA).', 'No hace falta prompt. MiniMax H3 con el LoRA Little More Sharpness usa su descripción de entrenamiento y el vídeo de origen como guía. En 2K/4K da nitidez a media resolución y duplica (escalador H3 o NVIDIA).')}</p>
              {mode === 'sharpness' && <pre className="native-preview">Enhance this video with sharp, crisp details while preserving a natural photorealistic appearance.</pre>}</div>}
            
            {!fixedRecipe && <div className="prompt-editor"><textarea ref={textarea} aria-label="Execution prompt" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={mode === 'swap' ? t.phSwap : t.phMotion}/>{query && suggestions.length > 0 && <div className="mention-menu">{suggestions.map(tag => <button key={tag} onClick={() => insertTag(tag)}>{tag}</button>)}</div>}</div>}
            {!fixedRecipe && promptMode === 'auto' && <div className="auto-prompt-bar">
              {autoSource === null
                ? <button type="button" className="primary" disabled={working || !prompt.trim()} onClick={autoPrompt}><Icon name="spark" size={14}/>{working ? tr('Writing…', 'Escrevendo…', 'Escribiendo…') : tr('Write the prompt now', 'Escrever o prompt agora', 'Escribir el prompt ahora')}</button>
                : <><span className="muted">{tr('Final prompt in English, written by the AI.', 'Prompt final em inglês, escrito pela IA.', 'Prompt final en inglés, escrito por la IA.')}</span><button type="button" className="quiet-button" onClick={() => {setPrompt(autoSource); setAutoSource(null); setTranslation(null);}}>{tr('Undo', 'Desfazer', 'Deshacer')}</button><button type="button" className="quiet-button" disabled={working} onClick={() => {setPrompt(autoSource); setAutoSource(null); setTranslation(null); setTimeout(autoPrompt, 0);}}>{tr('Write again', 'Escrever de novo', 'Escribir de nuevo')}</button></>}
              {prompt.trim() && <span className="read-in"><label>{tr('Read in', 'Ler em', 'Leer en')} <Select value={readLang} onChange={e => setReadLang(e.target.value as Language)}><option value="pt">Português</option><option value="es">Español</option><option value="en">English</option></Select></label><button type="button" className="quiet-button" disabled={translating} onClick={readPrompt}>{translating ? tr('Translating…', 'Traduzindo…', 'Traduciendo…') : tr('Show', 'Mostrar', 'Mostrar')}</button></span>}
            </div>}
            {!fixedRecipe && translation && translation.source === prompt && <div className="prompt-translation"><span className="eyebrow muted">{tr('For reading only: the model gets the English text above.', 'Só para leitura: o modelo recebe o texto em inglês acima.', 'Solo para leer: el modelo recibe el texto en inglés de arriba.')}</span><pre>{translation.text}</pre></div>}
            {!fixedRecipe && invalid.length > 0 && <p className="validation missing-pictures" role="alert">{tr('Missing in the prompt:', 'Falta no prompt:', 'Falta en el prompt:')} {invalid.map(tag => {const slot = Number(tag.match(/\d+/)?.[0]); const bring = bringSlots.find(b => b.slot === slot); return `Picture ${slot}${bring ? ` (${bring.label[lang]})` : ''}`;}).join(', ')}. {tr('Add the picture, or remove the tag from the prompt.', 'Adicione a imagem ou tire a marcação do prompt.', 'Añade la imagen o quita la etiqueta del prompt.')} <button type="button" className="quiet-button" onClick={() => imageInput.current?.click()}>{tr('Add picture', 'Adicionar imagem', 'Añadir imagen')}</button></p>}
            {!fixedRecipe && native && <pre className="native-preview">{nativePrompt(executionPrompt) || tr('Your H3 prompt will appear here.', 'Seu prompt H3 aparecerá aqui.', 'Tu prompt H3 aparecerá aquí.')}</pre>}
            <div className="prompt-footer">{!fixedRecipe && <><span className="eyebrow muted">{t.insert}</span><div className="mention-chips">{mentions.map(tag => <button key={tag} className="chip mono nc" onClick={() => insertTag(tag)}>{tag}</button>)}{!mentions.length && <span className="muted">—</span>}</div></>}<div className="prompt-generation-actions" id="prompt-generation-actions"/></div>
          </section>
          <input hidden ref={importSettingsInput} type="file" accept="application/json,.json" onChange={e => {importSettings(e.target.files?.[0]); e.target.value = '';}}/>
          <GenerationPanel background={mode === 'swap' || mode === 'motion' ? background?.file || null : null} key={importRevision} onEnhanceChange={setEnhanceOn} registerControls={controls => {panelControls.current = controls;}} freshRevision={freshRevision} requestedProfile={requestedProfile} initialSettings={importedSettings} onSelectJob={selectServerJob} onImportSettings={() => importSettingsInput.current?.click()} onShareSettings={options => {const direction = makeRequest(); if (direction) downloadJSON({kind: 'henge_settings', schema_version: 1, direction, generation: options}, 'henge-shared-settings.json');}} mode={mode} request={makeRequest()} video={video?.file || null} pictures={activePictures} canSubmit={canExport} lang={lang} requestedJobId={pendingAutoPromptJob} onResult={job => {setGenerationJob(job); if (job.id === pendingAutoPromptJob && job.plan && job.status === 'awaiting_approval') {setPrompt(job.plan.prompt); setPendingAutoPromptJob(null);}}}/>
          </section>
        </section>

        <aside className="direction-panel"><section className="surface pipeline-card"><span className="eyebrow muted">{t.pipeline}</span><div className="pipeline-list">{[[!!video?.range, t.p1, t.p1s], [maxPictures === 0 || activePictures.length > 0, t.p2, maxPictures === 0 ? tr('Not needed', 'Não necessárias', 'No necesarias') : `${activePictures.length} ${t.p2s}`], [fixedRecipe || (!!prompt.trim() && !invalid.length), t.p3, fixedRecipe ? tr('Automatic', 'Automática', 'Automática') : t.p3s], [generationJob?.status === 'completed', tr('Generate video', 'Gerar vídeo', 'Generar vídeo'), generationJob?.status === 'completed' ? tr('Video ready', 'Vídeo pronto', 'Vídeo listo') : tr('Review, then generate', 'Revise e gere', 'Revisa y genera')]].map(([ok, title, sub], i) => <div className={'pipeline-item ' + (ok ? 'complete' : '')} key={String(title)}><span className="pipeline-circle">{ok && <Icon name="check" size={11}/>}</span><div><strong>{title}</strong><small>{sub}</small></div>{i === 3 && <span className="mono step-end">04</span>}</div>)}</div></section>
          <section className="surface recent-card"><div className="label-row"><span className="eyebrow muted">{t.recent}</span><span className="recent-links">{serverJobs.some(j => TERMINAL_STATUS.includes(j.status)) && <button className="text-link" onClick={() => void clearHistory()}>{tr('Clear', 'Limpar', 'Vaciar')}</button>}<button className="text-link" onClick={() => setView('history')}>{t.viewAll} →</button></span></div>{recentJobs.length ? recentJobs.map(j => <div className="recent-row" key={j.id}><button className={'recent-item' + (generationJob?.id === j.id ? ' active' : '')} onClick={() => panelControls.current?.selectJob(j.id)} title={tr(`Select generation #${j.id.slice(0, 8)}; the assistant will know which one you mean`, `Selecionar geração #${j.id.slice(0, 8)}; o assistente saberá qual é`, `Seleccionar generación #${j.id.slice(0, 8)}; el asistente sabrá cuál es`)}><span className={'recent-thumb ' + (j.mode === 'swap' ? 'th-b' : 'th-a')}>{j.result_url ? <video muted playsInline preload="metadata" src={j.result_url + '#t=0.5'}/> : <Icon name="film" size={16}/>}</span><span><strong>{j.project || modeName((j.mode || 'swap') as Mode)}</strong><small><i style={{background: j.status === 'completed' ? '#48d17a' : j.status === 'failed' ? '#ef5a50' : ['cancelled'].includes(j.status) ? '#777185' : 'var(--s-f0c35a, #f0c35a)'}}/><span className="mono">#{j.id.slice(0, 8)}</span> · {modeName((j.mode || 'swap') as Mode)} · {jobStatusLabel(j.status, lang)}</small></span></button>{TERMINAL_STATUS.includes(j.status) && <button type="button" className="recent-delete" aria-label={tr(`Delete generation #${j.id.slice(0, 8)}`, `Apagar a geração #${j.id.slice(0, 8)}`, `Borrar la generación #${j.id.slice(0, 8)}`)} title={tr('Delete', 'Apagar', 'Borrar')} onClick={() => void deleteJob(j)}>×</button>}</div>) : <div className="recent-empty"><Icon name="clock" size={22}/><p>{tr('Your generations will appear here.', 'Suas gerações aparecerão aqui.', 'Tus generaciones aparecerán aquí.')}</p></div>}</section>
          <p className="direction-tip"><span className="eyebrow accent">Tip</span> — {({swap: t.tipSwap, motion: t.tipMotion, headswap: tr('Use a front-facing, well-lit face. Clips where the head stays visible and not too small work best.', 'Use um rosto de frente e bem iluminado. Funciona melhor quando a cabeça aparece bem e não é pequena.', 'Usa un rostro de frente y bien iluminado. Funciona mejor si la cabeza se ve bien y no es pequeña.'), sharpness: tr('Run it as a second pass on a finished generation: pick it from "Use a video generated in the studio".', 'Use como segunda passada numa geração pronta: escolha em "Usar um vídeo gerado no estúdio".', 'Úsalo como segunda pasada sobre una generación: elígela en "Usar un vídeo generado en el estudio".')})[mode]}</p>
        </aside>
      </main>


    </div>

    {view === 'history' && <main className="history-page"><div className="section-top"><div><span className="eyebrow accent">{t.history} · {serverJobs.length}</span><h1>{tr('Your generations', 'Suas gerações', 'Tus generaciones')}</h1><p>{tr('Everything rendered on this Henge. Open one to see its result, plan and settings, or to run it again.', 'Tudo o que foi gerado neste Henge. Abra uma geração para ver o resultado, o plano e os ajustes, ou para rodar de novo.', 'Todo lo generado en este Henge. Abre una para ver el resultado, el plan y los ajustes, o para repetirla.')}</p></div><div className="history-tools"><input className="history-search" type="search" value={historySearch} onChange={e => setHistorySearch(e.target.value)} placeholder={tr('Search by name, mode or model', 'Buscar por nome, modo ou modelo', 'Buscar por nombre, modo o modelo')} aria-label={tr('Search generations', 'Buscar gerações', 'Buscar generaciones')}/>{historyModels.length > 1 && <Select className="history-model" value={historyModel} onChange={e => setHistoryModel(e.target.value)} aria-label={tr('Model', 'Modelo', 'Modelo')}><option value="all">{tr('All models', 'Todos os modelos', 'Todos los modelos')}</option>{historyModels.map(id => <option key={id} value={id}>{modelLabels[id] || id}</option>)}</Select>}{serverJobs.some(j => TERMINAL_STATUS.includes(j.status)) && <button type="button" className="quiet-button danger-text" onClick={clearHistory}><Icon name="close" size={12}/>{tr('Clear history', 'Limpar histórico', 'Vaciar historial')}</button>}<div className="filter-chips">{(['all', ...MODES] as const).map(key => <button key={key} className={historyFilter === key ? 'active' : ''} aria-pressed={historyFilter === key} onClick={() => setHistoryFilter(key)}>{key === 'all' ? t.all : modeName(key)}</button>)}</div></div></div>
      <div className="generation-grid">{historyJobs.slice(0, historyShown).map(j => {
        const open = () => {panelControls.current?.selectJob(j.id); setView('studio');};
        const name = `henge-${j.id.slice(0, 8)}`;
        const downloads = [
          j.result_url && {href: j.result_url, file: `${name}.mp4`, label: tr('Video', 'Vídeo', 'Vídeo')},
          j.comparison_url && {href: j.comparison_url, file: `${name}-comparison.mp4`, label: tr('Comparison', 'Comparação', 'Comparación')},
          j.comparison_url && {href: `/api/backend/jobs/${j.id}/comparison-with-refs`, file: `${name}-comparison-references.mp4`, label: tr('+ references', '+ referências', '+ referencias')},
          j.status === 'completed' && j.guide_preview_url && {href: j.guide_preview_url, file: `${name}-guide.mp4`, label: tr('Guide', 'Guia', 'Guía')},
          j.status === 'completed' && {href: `/api/backend/jobs/${j.id}/bundle.zip`, file: `${name}.zip`, label: tr('Everything (.zip)', 'Tudo (.zip)', 'Todo (.zip)'), all: true},
        ].filter(Boolean) as {href: string; file: string; label: string; all?: boolean}[];
        return <div key={j.id} className={'history-card generation-card surface' + (generationJob?.id === j.id ? ' selected' : '')} style={accentVars((j.mode || 'swap') as Mode, 'item') as CSSProperties}>
          <button type="button" className="generation-open" onClick={open} aria-label={`${tr('Open', 'Abrir', 'Abrir')} ${j.project || 'Henge'}`}><div className={'history-art ' + (j.mode === 'swap' ? 'th-b' : 'th-a')}>{j.result_url ? <video muted playsInline preload="metadata" src={j.result_url + '#t=0.5'}/> : <Icon name="film" size={30}/>}<span className={'badge mono mode-badge ' + (j.mode || '')}>{modeName((j.mode || 'swap') as Mode)}</span>{typeof j.duration === 'number' && <span className="badge duration-badge mono nc">{j.duration.toFixed(1)}s</span>}</div><div className="history-caption"><strong>{j.project || 'Henge'}</strong><span className="mono nc muted">#{j.id.slice(0, 8)} · {dateLabel(new Date(j.created * 1000).toISOString())}{j.quality ? ` · ${j.quality}` : ''}</span>{(() => {const secs = j.run_seconds ?? (j.run_started ? Date.now() / 1000 - j.run_started : undefined); return secs !== undefined ? <span className="mono nc muted job-time">⏱ {secs >= 60 ? `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s` : `${Math.round(secs)}s`}{j.run_started && j.run_seconds === undefined ? '…' : ''}</span> : null;})()}{jobModel(j).label && <span className="mono nc muted job-model">{jobModel(j).label}{j.options?.conditioning_mode === 'tara' ? ' · TARA' : ''}</span>}<span className={'job-status ' + j.status}>{jobStatusLabel(j.status, lang)}</span></div></button>
          {TERMINAL_STATUS.includes(j.status) && <button type="button" className="icon-btn history-delete" aria-label={tr('Delete this generation', 'Apagar esta geração', 'Borrar esta generación')} title={tr('Delete', 'Apagar', 'Borrar')} onClick={() => deleteJob(j)}><Icon name="close" size={14}/></button>}
          {downloads.length > 0 && <div className="generation-downloads">{downloads.map(d => <a key={d.file} className={'quiet-button' + (d.all ? ' download-all' : '')} title={d.all ? tr('Result, comparisons, every shot, guides, references, planner notes, ComfyUI workflows and the source media', 'Resultado, comparações, cada trecho, guias, referências, notas do planejador, workflows do ComfyUI e a mídia original', 'Resultado, comparaciones, cada tramo, guías, referencias, notas del planificador, workflows de ComfyUI y el material original') : undefined} href={d.href} download={d.file}><Icon name="download" size={12}/>{d.label}</a>)}</div>}
        </div>;
      })}{!serverJobs.length && <div className="history-empty"><span className="empty-emblem"><Icon name="clock" size={30}/></span><h2>{tr('Nothing generated yet.', 'Nada gerado ainda.', 'Nada generado todavía.')}</h2><button className="primary" onClick={() => setView('studio')}><Icon name="plus" size={16}/>{tr('Open studio', 'Abrir estúdio', 'Abrir estudio')}</button></div>}{serverJobs.length > 0 && !historyJobs.length && <p className="muted history-none">{tr('No generation matches this search.', 'Nenhuma geração encontrada com essa busca.', 'Ninguna generación coincide con la búsqueda.')}</p>}</div>
      <div ref={historyEnd} className="history-end">{historyShown < historyJobs.length ? tr('Loading more…', 'Carregando mais…', 'Cargando más…') : historyJobs.length > 24 ? tr('That is all.', 'Isso é tudo.', 'Eso es todo.') : ''}</div>
      <details className="saved-directions"><summary>{tr('Saved directions', 'Direções salvas', 'Direcciones guardadas')} · {history.length} <small className="muted">{tr('prompts and settings exported on this device', 'prompts e ajustes exportados neste dispositivo', 'prompts y ajustes exportados en este dispositivo')}</small></summary>
      <div className="history-layout"><div className="history-grid">{filteredHistory.map(h => <button key={h.id} className={'history-card surface ' + (selected?.id === h.id ? 'selected' : '')} style={accentVars(h.request.mode, 'item') as CSSProperties} onClick={() => setSelectedId(h.id)}><div className={'history-art ' + (h.request.mode === 'swap' ? 'th-b' : 'th-a')}>{h.thumbnail ? <img src={h.thumbnail} alt={h.request.video.name}/> : <Icon name="film" size={30}/>}<span className={'badge mono mode-badge ' + h.request.mode}>{modeName(h.request.mode)}</span><span className="badge duration-badge mono nc">{h.request.video.duration.toFixed(1)}s</span><span className="badge draft-badge mono">{tr('Direction', 'Direção', 'Dirección')}</span></div><div className="history-caption"><strong>{h.request.project}</strong><span className="mono nc muted">{dateLabel(h.created)} · {h.request.quality}</span><span className="stars" aria-label={`${h.rating}/5`}>{'★'.repeat(h.rating)}<span>{'☆'.repeat(5 - h.rating)}</span></span></div></button>)}{!filteredHistory.length && <div className="history-empty"><span className="empty-emblem"><Icon name="clock" size={30}/></span><h2>{history.length ? tr('No directions in this mode.', 'Nenhuma direção neste modo.', 'No hay direcciones en este modo.') : tr('Your next idea starts here.', 'Sua próxima ideia começa aqui.', 'Tu próxima idea empieza aquí.')}</h2><p>{tr('Export a direction from the Studio to save its prompt, settings and source preview.', 'Exporte uma direção no Estúdio para guardar o prompt, os ajustes e a prévia do guia.', 'Exporta una dirección del Estudio para guardar el prompt, los ajustes y la vista previa de la guía.')}</p><button className="primary" onClick={() => setView('studio')}><Icon name="plus" size={16}/>{tr('Open studio', 'Abrir estúdio', 'Abrir estudio')}</button></div>}</div>
        {selected && <aside className="history-detail surface"><div className={'detail-art ' + (selected.request.mode === 'swap' ? 'th-b' : 'th-a')}>{selected.thumbnail ? <img src={selected.thumbnail} alt={selected.request.video.name}/> : <Icon name="film" size={40}/>}<span className="badge mono">{tr('Source preview', 'Prévia do guia', 'Vista previa de la guía')}</span></div><div className="detail-body"><h2>{selected.request.project}</h2><p className="detail-prompt">{selected.request.editor_prompt}</p><div className="detail-facts">{[[t.mode, modeName(selected.request.mode)], [t.duration, `${selected.request.video.duration.toFixed(1)}s`], [t.quality, selected.request.quality], [t.created, dateLabel(selected.created)]].map(([label, value]) => <div key={label}><span className="eyebrow muted">{label}</span><strong>{value}</strong></div>)}</div><div className="feedback-panel"><div className="label-row"><strong>{tr('Rate this direction', 'Avalie esta direção', 'Valora esta dirección')}</strong><small className="muted">{selected.rating ? t.rl[selected.rating - 1] : t.noRating}</small></div><div className="rating-buttons" role="group" aria-label={tr('Direction rating', 'Avaliação da direção', 'Valoración de la dirección')}>{[1, 2, 3, 4, 5].map(n => <button key={n} aria-label={`${n} / 5`} aria-pressed={selected.rating === n} className={selected.rating >= n ? 'filled' : ''} onClick={() => patchHistory(selected.id, {rating: selected.rating === n ? 0 : n})}>{selected.rating >= n ? '★' : '☆'}</button>)}</div><div className="feedback-tags">{FEEDBACK.map((tag, i) => <button key={tag} aria-pressed={selected.tags.includes(tag)} className={selected.tags.includes(tag) ? 'chosen' : ''} onClick={() => patchHistory(selected.id, {tags: selected.tags.includes(tag) ? selected.tags.filter(x => x !== tag) : [...selected.tags, tag]})}>{feedbackLabels[i]}</button>)}</div></div><div className="detail-actions"><button className="primary" onClick={() => downloadJSON(selected.request, 'henge-request.json')}><Icon name="download" size={15}/>{t.export}</button><button className="quiet-button" onClick={() => setModal('share')}><Icon name="share" size={15}/>{tr('Share preset', 'Compartilhar template', 'Compartir plantilla')}</button><button className="quiet-button reuse-button" onClick={() => reuse(selected)}>{t.reuse}</button><button className="icon-btn delete-button" aria-label={t.del} onClick={() => setModal('delete')}><Icon name="trash" size={17}/></button></div></div></aside>}
      </div>
      </details>
    </main>}

    {view === 'community' && <main className="community-page"><span className="eyebrow accent">{t.community}</span><h1>{tr('Find your next idea.', 'Encontre sua próxima ideia.', 'Encuentra tu próxima idea.')}</h1><p className="community-intro">{tr('Open an example in Character Swap or Motion transfer, change the pictures, and make it yours.', 'Abra um exemplo no Character Swap ou no Motion transfer, troque as imagens e crie sua versão.', 'Abre un ejemplo en Character Swap o Motion transfer, cambia las imágenes y crea tu versión.')}</p>
      <section className="templates-section"><div className="section-top"><div><span className="eyebrow accent">{tr('Examples', 'Exemplos', 'Ejemplos')} · {COMMUNITY.length}</span><h2>{tr('Start from a real case.', 'Comece de um caso pronto.', 'Empieza con un caso listo.')}</h2><p>{tr('Guide video, references and prompt load together. Add your own picture where it says "You".', 'Vídeo guia, referências e prompt carregam juntos. Adicione sua foto onde aparece "Você".', 'Vídeo guía, referencias y prompt se cargan juntos. Añade tu foto donde dice "Tú".')}</p></div></div>
        <div className="template-grid">{COMMUNITY.map(preset => <div key={preset.id} className="template-card community-card">
          <div className="template-art"><video muted loop playsInline preload="metadata" poster={`/community/${preset.id}/poster.jpg`} aria-label={tr(`Preview: ${preset.title.en}`, `Prévia: ${preset.title.pt}`, `Vista previa: ${preset.title.es}`)} onMouseEnter={e => {e.currentTarget.play().catch(() => {});}} onMouseLeave={e => {e.currentTarget.pause(); e.currentTarget.currentTime = 0;}} onFocus={e => {e.currentTarget.play().catch(() => {});}} onBlur={e => {e.currentTarget.pause(); e.currentTarget.currentTime = 0;}}><source src={`/community/${preset.id}/guide.mp4`} type="video/mp4"/></video><span className="community-preview-label mono"><Icon name="film" size={11}/>{tr('Hover to preview', 'Passe para visualizar', 'Pasa para previsualizar')}</span>{loadingCommunity === preset.id && <span className="template-cta">{tr('Loading…', 'Carregando…', 'Cargando…')}</span>}</div>
          <div className="template-caption"><h3>{preset.title[lang]}</h3><p>{preset.prompt[lang]}</p></div>
          <div className="community-assets" aria-label={tr('Pictures used by this example', 'Imagens usadas por este exemplo', 'Imágenes usadas por este ejemplo')}>{[...preset.refs.map(r => ({...r, bring: false})), ...preset.bring.map(r => ({...r, bring: true}))].sort((a, b) => a.slot - b.slot).map(r => <span key={r.slot} className={r.bring ? 'bring' : 'included'}><Icon name={r.bring ? 'plus' : 'image'} size={11}/><span><strong>{r.label[lang]}</strong><small>{r.bring ? tr('add your photo', 'adicione sua foto', 'añade tu foto') : tr('included', 'incluída', 'incluida')}</small></span></span>)}</div>
          <div className="community-modes">{(['swap', 'motion'] as Mode[]).map(m => <button key={m} className="quiet-button" disabled={!!loadingCommunity} onClick={() => useCommunity(preset, m)}><Icon name={m} size={14}/><span>{modeName(m)}</span></button>)}</div>
        </div>)}</div>
      </section>
      </main>}


    <footer className="app-footer"><span className="mono">Henge <Icon name="spark" size={12}/> {tr('An open canvas for moving ideas.', 'Uma tela aberta para ideias em movimento.', 'Un lienzo abierto para ideas en movimiento.')}</span><span className="footer-credits">{tr('Made with', 'Feito com', 'Hecho con')} <a href="https://github.com/comfyanonymous/ComfyUI" target="_blank" rel="noreferrer">ComfyUI</a> · {tr('powered by open-weight models (MiniMax H3, Qwen, SAM and more)', 'movido a modelos de pesos abertos (MiniMax H3, Qwen, SAM e outros)', 'impulsado por modelos de pesos abiertos (MiniMax H3, Qwen, SAM y otros)')} · <a href="https://github.com/alisson-anjos/Henge" target="_blank" rel="noreferrer">{tr('open source (MIT)', 'código aberto (MIT)', 'código abierto (MIT)')}</a></span></footer>
    {notice && <div className="notification" role="status" aria-live="polite"><span>{notice}</span><button className="icon-btn" aria-label={tr('Dismiss notification', 'Fechar notificação', 'Cerrar notificación')} onClick={() => setNotice('')}><Icon name="close" size={16}/></button></div>}
    <dialog className="action-modal" ref={dialog} onCancel={e => {e.preventDefault(); setModal(null);}} aria-labelledby="action-title"><button className="modal-close icon-btn" aria-label={t.cancel} onClick={() => setModal(null)}><Icon name="close" size={18}/></button><span className="modal-emblem"><Icon name={modal === 'delete' ? 'trash' : 'share'} size={26}/></span><h2 id="action-title">{modal === 'delete' ? tr('Delete this direction?', 'Excluir esta direção?', '¿Eliminar esta dirección?') : tr('Share a direction', 'Compartilhe uma direção', 'Comparte una dirección')}</h2><p>{modal === 'delete' ? tr('This removes its local history entry. Your original media files are unchanged.', 'Isso remove a entrada do histórico local. Seus arquivos originais permanecem intactos.', 'Esto elimina la entrada del historial local. Tus archivos originales no cambian.') : tr('Export the prompt and settings as a JSON preset. Media, ratings and local file names are not included.', 'Exporte o prompt e os ajustes como um template JSON. Mídia, avaliações e nomes de arquivos locais não são incluídos.', 'Exporta el prompt y los ajustes como plantilla JSON. No incluye archivos, valoraciones ni nombres de archivos locales.')}</p><div className="modal-actions"><button className="quiet-button" onClick={() => setModal(null)}>{t.cancel}</button><button className="primary" onClick={() => {if (!selected) return; if (modal === 'delete') {setHistory(h => h.filter(x => x.id !== selected.id)); setSelectedId(null);} else {const r = selected.request; downloadJSON({schema_version: 1, kind: 'henge_prompt_preset', title: r.project, mode: r.mode, quality: r.quality, prompt: r.editor_prompt, processing: r.processing, audio_conditioning: r.audio_conditioning, output_audio: r.output_audio, reference_slots: r.pictures.map(p => p.slot)}, 'henge-preset.json');} setModal(null);}}>{modal === 'delete' ? t.del : tr('Download preset', 'Baixar template', 'Descargar plantilla')}</button></div></dialog>
  </div>;
}
