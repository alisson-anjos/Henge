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
import {captureFrame, thumbnail} from '../lib/frame-capture';
import {readableError} from '../lib/job-error';
import JobProgress from './job-progress';
import {readJson} from '../lib/http';
import {jobStatusLabel} from '../lib/job-status';
import SubjectBindings, {SubjectVideo} from './subject-bindings';
import {SUBJECT_COLORS, bindingPrompt, readSubjectBindings, type SubjectBinding, type GuideRepresentation} from '../lib/subject-bindings';
import SetupScreen from './setup-screen';
import {cutModeLabel, type CutMode} from './shot-plan';

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
const MODE_STYLE: Record<Mode, {accent: string; rgb: string}> = {
  swap: {accent: '#D6FF4B', rgb: '214,255,75'}, motion: {accent: '#AA8BFF', rgb: '170,139,255'},
  headswap: {accent: '#FF9F6B', rgb: '255,159,107'}, sharpness: {accent: '#6BE4FF', rgb: '107,228,255'},
};
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
  const [frameModal, setFrameModal] = useState(false);
  const [requestedProfile, setRequestedProfile] = useState<string | null>(null);
  const [editingVideo, setEditingVideo] = useState(false);
  const [subjects, setSubjects] = useState<SubjectBinding[]>([]);
  const [guideRepresentation, setGuideRepresentation] = useState<GuideRepresentation>('original');
  // 2D color marks: 1 = solid; lower keeps the guide person visible under a translucent tint (BFS Colored Mark used 0.35).
  const [markOpacity, setMarkOpacity] = useState(0.35);
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  // A new guide starts a new generation: the panel drops the selected job (its plan, shots and result) until one is
  // picked again from the history.
  const [freshRevision, setFreshRevision] = useState(0);
  const startFresh = () => {setGenerationJob(null); setFreshRevision(n => n + 1); setBringSlots([]);};
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
  const [shotSeconds, setShotSeconds] = useState(4.5);
  const [timelineFps, setTimelineFps] = useState(24);
  const [contextFrames, setContextFrames] = useState(22);
  const [cutMode, setCutMode] = useState<CutMode>('fit');
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
  const style = {'--accent': MODE_STYLE[mode].accent, '--accent-rgb': MODE_STYLE[mode].rgb} as CSSProperties;
  const modeName = (value: Mode) => ({swap: t.swap, motion: t.motion, headswap: tr('Head Swap', 'Troca de cabeça', 'Cambio de cabeza'), sharpness: tr('Sharpness', 'Nitidez', 'Nitidez')})[value];
  // Model names for History (from the bridge's model list), to search and filter generations by model.
  const [modelLabels, setModelLabels] = useState<Record<string, string>>({});
  const [historyModel, setHistoryModel] = useState('all');
  useEffect(() => {
    if (view !== 'history') return;
    fetch('/api/backend/health', {cache: 'no-store'}).then(r => r.ok ? r.json() : null).then(h => {if (h?.models) setModelLabels(Object.fromEntries(Object.entries(h.models as Record<string, {label: string}>).map(([k, m]) => [k, m.label])));}).catch(() => {});
  }, [view]);
  const jobModel = (j: GenerationJob) => {const id = typeof j.options?.profile === 'string' ? j.options.profile : ''; return {id, label: modelLabels[id] || id};};
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
        setKeepAudio(s.keepAudio !== false);
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
    try { localStorage.setItem('henge-draft', JSON.stringify({prompt, intent, mode, project, quality, audioConditioning, keepAudio, shotSeconds, timelineFps, contextFrames, cutMode, lang, subjects, guideRepresentation, guideSignature})); } catch { /* Editing still works without draft persistence. */ }
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
  const studioLive = useRef({mode, prompt, video, pictures, subjects, guideRepresentation, markOpacity, quality, generationJob, maxPictures});
  studioLive.current = {mode, prompt, video, pictures, subjects, guideRepresentation, markOpacity, quality, generationJob, maxPictures};
  const found = useRef(new Map<string, {width: number; height: number; people: {number: number; x: number; y: number}[]}>());
  const settle = () => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  const studioState = () => {
    const c = studioLive.current;
    return {mode: c.mode, guide_video: c.video ? {name: c.video.file.name, duration: c.video.duration ?? null, selected: c.video.range ?? null} : null,
      pictures: c.pictures.map(p => ({slot: p.slot, name: p.file.name})), max_pictures: c.maxPictures,
      subjects: c.subjects.map((s, i) => ({subject: i + 1, label: s.label, color: s.color, picture_slots: s.picture_slots, marks: s.anchors.map(a => a.time_seconds)})),
      guide_representation: c.guideRepresentation, mark_opacity: c.markOpacity, prompt: c.prompt, quality: c.quality,
      selected_job: c.generationJob ? {id: c.generationJob.id, status: c.generationJob.status, stage: c.generationJob.stage, message: c.generationJob.message} : null};
  };
  async function runStudioCall(call: StudioCall): Promise<StudioResult> {
    const c = studioLive.current, input = call.input;
    const num = (k: string) => Number(input[k]);
    const inRange = (t: number) => {if (!c.video?.range) throw Error('Attach and trim the guide video first'); if (!Number.isFinite(t) || t < c.video.range.start || t > c.video.range.end) throw Error(`Use a time inside the selected interval ${c.video.range.start.toFixed(2)}–${c.video.range.end.toFixed(2)} s`); return t;};
    switch (call.name) {
      case 'get_studio_state': return {text: JSON.stringify(studioState())};
      case 'view_pictures': {
        if (!c.pictures.length) return {text: 'No pictures attached.'};
        return {text: c.pictures.map((p, i) => `Image ${i + 1} = Picture ${p.slot} (${p.file.name})`).join('; '), images: await Promise.all(c.pictures.map(p => thumbnail(p.file, 640)))};
      }
      case 'view_frame': {
        const t = inRange(num('time')); const frame = await captureFrame(c.video!.url, t);
        return {text: `Guide frame at ${t.toFixed(2)} s (${frame.width}x${frame.height}).`, images: [await thumbnail(frame.blob, 960)]};
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
        setMode(m); await settle(); return {text: `Mode is now ${m}.`};
      }
      case 'set_prompt': setPrompt(String(input.text ?? '')); await settle(); return {text: 'Prompt updated.'};
      case 'mark_subject': {
        const t = num('time'), hit = found.current.get(t.toFixed(2));
        if (!hit) throw Error(`Call find_people at ${t} first`);
        const person = hit.people.find(p => p.number === num('person')); if (!person) throw Error(`No person #${input.person} at ${t}`);
        const slots = (input.picture_slots as number[] || []).map(Number);
        if (!slots.length || slots.some(n => !c.pictures.some(p => p.slot === n))) throw Error('Use attached picture slots');
        const color = SUBJECT_COLORS.find(col => !c.subjects.some(s => s.color === col.name));
        if (!color) throw Error('Every color is in use');
        const subject: SubjectBinding = {id: crypto.randomUUID(), label: String(input.label || `Subject ${c.subjects.length + 1}`), color: color.name, picture_slots: slots,
          anchors: [{x: person.x, y: person.y, time_seconds: t, frame_width: hit.width, frame_height: hit.height}]};
        setSubjects(current => [...current, subject]); await settle();
        return {text: `Subject ${c.subjects.length + 1} (${color.name}) = person #${person.number} → Picture ${slots.join(', ')}.`};
      }
      case 'clear_subjects': setSubjects([]); await settle(); return {text: 'All subjects removed.'};
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
        await settle(); const id = await panelControls.current.submit();
        return {text: `Generation started: job ${id}. Use wait_for_job.`};
      }
      default: throw Error(`Unknown studio tool ${call.name}`);
    }
  }
  // Improve at Generate: in Improve mode, and in Auto Prompt mode until the AI has written the final prompt.
  useEffect(() => {panelControls.current?.setEnhancePrompt(promptMode === 'improve' || (promptMode === 'auto' && autoSource === null));}, [promptMode, autoSource]);
  useEffect(() => {setReadLang(lang === 'en' ? 'pt' : lang);}, [lang]);
  const assistantController: StudioController = {state: studioState, run: runStudioCall};
  const contextWindow = selectedDuration > 15;
  const shotFrames = Math.max(22, Math.floor((Math.round(shotSeconds * 24) - 5) / 17) * 17 + 5);
  const estimatedShots = selectedDuration ? Math.ceil(Math.round(selectedDuration * timelineFps) / shotFrames) : 0;
  const subjectErrors = subjects.some(s => !s.anchors.length || !s.picture_slots.length || s.picture_slots.some(n => !pictures.some(p => p.slot === n)) || s.anchors.some(a => !video?.range || a.time_seconds < video.range.start || a.time_seconds >= video.range.end));
  const executionPrompt = prompt + (subjects.length && !subjectErrors ? '\n\n' + bindingPrompt(subjects, guideRepresentation) : '');
  const canExport = !!video?.range && !editingVideo && ready && !busy && (fixedRecipe
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
  function addPictures(files: FileList | null) {
    if (!files) return;
    const slots = [...new Set([...expectedSlots, ...Array.from({length: MAX_PICTURES}, (_, i) => i + 1)])].filter(i => i <= maxPictures);
    const available = slots.filter(i => !pictures.some(p => p.slot === i));
    const valid = Array.from(files).filter(f => ['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(f.type) && f.size <= 25 * 1024 * 1024);
    setNotice(valid.length !== files.length ? tr('Use JPG, PNG, WebP or GIF (first frame), up to 25 MB each.', 'Use JPG, PNG, WebP ou GIF (primeiro quadro), até 25 MB por imagem.', 'Usa JPG, PNG, WebP o GIF (primer fotograma), hasta 25 MB por imagen.') : valid.length > available.length ? (mode === 'headswap' ? tr('Head Swap uses one face picture.', 'A troca de cabeça usa uma foto de rosto.', 'El cambio de cabeza usa una foto de rostro.') : tr('Up to 11 reference pictures.', 'Até 11 imagens de referência.', 'Hasta 11 imágenes de referencia.')) : '');
    setPictures(current => [...current, ...valid.slice(0, available.length).map((file, i) => ({slot: available[i], file, url: URL.createObjectURL(file)}))].sort((a, b) => a.slot - b.slot));
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
    } catch { setNotice(tr('Could not load that video from the backend.', 'Não foi possível carregar esse vídeo do backend.', 'No se pudo cargar ese vídeo del backend.')); }
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
      const body = new FormData(); body.set('direction', JSON.stringify(request)); body.set('options', JSON.stringify({profile: mode === 'motion' ? 'motion' : 'character', fibo: 'auto', seed: 42, steps: 8, clip_fps: 2})); body.set('video', video.file);
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
      processing: {mode: contextWindow ? 'context_window' : 'single', max_shots: 0, requested_seconds_per_shot: shotSeconds, frames_per_shot: shotFrames, timeline_fps: timelineFps, frame_grid: '17n+5', trim_to_source_length: true, join: 'ordered', execution_status: 'comfy_backend', context_frames: contextFrames, cut_mode: cutMode},
      audio_conditioning: {enabled: audioConditioning, source: audioConditioning ? 'guide_video' : null},
      output_audio: {keep_source: keepAudio}, prompt: fixedRecipe ? '' : nativePrompt(executionPrompt), editor_prompt: fixedRecipe ? '' : prompt,
      subject_guidance: {representation: guideRepresentation, bindings: subjects, status: 'selection_only', marker_colors_are_output_appearance: false, ...(guideRepresentation === '2d' ? {mark_opacity: markOpacity} : {})},
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
  // The same guide is back (reload, re-upload or a restored job): bring back its FIBO-edited first frame.
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
    {frameModal && video?.range && <FirstFrameModal videoUrl={video.url} start={video.range.start} pictures={pictures.filter(p => p.slot !== firstFrameSlot)} lang={lang} onClose={() => setFrameModal(false)} onUse={(file, edit) => {
      const slot = firstFrameSlot ?? Array.from({length: maxPictures}, (_, i) => i + 1).find(i => !pictures.some(p => p.slot === i));
      if (!slot) {setNotice(tr('Remove a picture to make room for the first frame.', 'Remova uma Picture para abrir espaço para o primeiro quadro.', 'Quita una imagen para dejar espacio al primer fotograma.')); return;}
      setPictures(current => [...current.filter(p => {if (p.slot === slot) URL.revokeObjectURL(p.url); return p.slot !== slot;}), {slot, file, url: URL.createObjectURL(file)}].sort((a, b) => a.slot - b.slot));
      setFirstFrameSlot(slot); setRequestedProfile('motion_ffp'); setFrameModal(false);
      // A FIBO edit lives on the bridge: remember it with this guide so a reload can bring it back.
      try {if (edit) localStorage.setItem(FIRST_FRAME_KEY, JSON.stringify({...edit, slot, guide: guideSignature})); else localStorage.removeItem(FIRST_FRAME_KEY);} catch {/* private mode */}
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
      <div className="topbar-end"><div className="language-switch" role="group" aria-label="Language">{(['en', 'pt', 'es'] as Language[]).map(l => <button key={l} className={'mono ' + (lang === l ? 'active' : '')} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}</div><a className="source-link ghost" href="https://github.com/alisson-anjos/Henge" target="_blank" rel="noreferrer"><Icon name="github" size={16}/>{t.openSource}</a></div>
    </header>

    {/* Kept mounted on other tabs so the generation panel keeps its settings and selected job. */}
    <div className="studio-view" hidden={view !== 'studio'}>
      {ready && <AssistantPanel controller={assistantController} lang={lang} jobId={generationJob?.id}/>}
      <main className="workspace">
        <aside className="controls">
          <div className="create-heading rise"><span className="eyebrow accent">{t.create}</span><h1>{t[`h1a_${mode}`]}<br/><span>{t[`h1b_${mode}`]}</span></h1></div>
          <div className="mode-switch" role="group" aria-label={t.mode}>{MODES.map(m => <button key={m} disabled={!ready || busy} className={mode === m ? 'selected' : ''} onClick={() => setMode(m)} aria-pressed={mode === m}><Icon name={m} size={16}/>{modeName(m)}</button>)}</div>
          <p className="mode-description">{modeDescription}</p>
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
            {contextWindow && <details className="context-window-panel" open><summary><Icon name="scissors" size={16}/><strong>{t.autoCut}</strong><span className="mini-badge">{t.unlimited}</span></summary><p>{tr('This interval uses short segments joined in order.', 'Este intervalo usa segmentos curtos unidos em sequência.', 'Este intervalo usa segmentos cortos unidos en orden.')}</p><div className="shot-settings"><label>{t.fixedLabel}<input aria-label={t.fixedLabel} type="number" min="1" max="15" step="0.1" value={shotSeconds} onChange={e => setShotSeconds(Math.min(15, Math.max(1, Number(e.target.value) || 4.5)))}/></label><label>Timeline FPS<input aria-label="Timeline FPS" type="number" min="1" max="120" value={timelineFps} onChange={e => setTimelineFps(Math.min(120, Math.max(1, Number(e.target.value) || 24)))}/></label></div><div className="label-row"><span>{t.ctxLen}</span><div className="context-options">{[5, 22, 39].map(f => <button key={f} aria-pressed={contextFrames === f} className={contextFrames === f ? 'chosen' : ''} onClick={() => setContextFrames(f)}>{f}f</button>)}</div></div><label className="cut-mode-field">{tr('Camera cuts', 'Cortes de câmera', 'Cortes de cámara')}<select value={cutMode} onChange={e => setCutMode(e.target.value as CutMode)}>{(['fit', 'every', 'off'] as CutMode[]).map(m => <option key={m} value={m}>{cutModeLabel(m, lang)}</option>)}</select></label><small className="muted">{shotFrames}f · 17n+5 · {cutMode === 'every' ? tr('a shot per camera cut', 'um trecho por corte de câmera', 'un tramo por corte de cámara') : `~${estimatedShots} ${t.cutsWord}`}</small></details>}
          </section>
          {maxPictures > 0 && <section className={'input-card surface reference-dropzone ' + (draggingPictures ? 'dragging' : '')} onDragEnter={e => {e.preventDefault(); if (e.dataTransfer.types.includes('Files')) {pictureDragDepth.current++; setDraggingPictures(true);}}} onDragOver={e => {e.preventDefault(); e.dataTransfer.dropEffect = 'copy';}} onDragLeave={e => {e.preventDefault(); pictureDragDepth.current = Math.max(0, pictureDragDepth.current - 1); if (!pictureDragDepth.current) setDraggingPictures(false);}} onDrop={e => {e.preventDefault(); e.stopPropagation(); pictureDragDepth.current = 0; setDraggingPictures(false); addPictures(e.dataTransfer.files);}}>
            <div className="label-row"><h2><span className="step-number">02</span>{mode === 'headswap' ? tr('Face reference', 'Rosto de referência', 'Rostro de referencia') : t.refs}</h2><span className="ref-header-end">{pictures.length > 0 && <button type="button" className="text-link remove-all-refs" onClick={removeAllPictures}>{tr('Remove all', 'Remover todas', 'Quitar todas')}</button>}<span className="mono muted">{String(activePictures.length).padStart(2, '0')} / {String(maxPictures).padStart(2, '0')}</span></span></div>
            <input data-testid="picture-input" hidden ref={imageInput} type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple onChange={e => {addPictures(e.target.files); e.target.value = '';}}/>
            <div className="reference-grid">{activePictures.map(p => <div className="reference" key={p.slot}><img draggable={false} src={p.url} alt={`Picture ${p.slot}: ${p.file.name}`}/><button className="remove-ref" aria-label={`Remove Picture ${p.slot}`} onClick={() => removePicture(p.slot)}><Icon name="close" size={11}/></button><button className="ref-label mono nc" onClick={() => insertTag(`@Picture${p.slot}`)}>@Picture{p.slot}</button>{p.slot === firstFrameSlot && <span className="first-frame-badge mono">{tr('1st frame', '1º quadro', '1er fotograma')}</span>}</div>)}{bringSlots.filter(b => b.slot <= maxPictures && !pictures.some(p => p.slot === b.slot)).map(b => <button key={`bring-${b.slot}`} className="add-reference bring-reference" onClick={() => imageInput.current?.click()}><Icon name="plus" size={18}/><span className="mono">@Picture{b.slot}</span><small>{b.label[lang]} · {tr('add your photo', 'adicione sua foto', 'añade tu foto')}</small></button>)}{activePictures.length < maxPictures && !bringSlots.some(b => !pictures.some(p => p.slot === b.slot)) && <button className="add-reference" onClick={() => imageInput.current?.click()}><Icon name="plus" size={18}/><span>{t.add}</span></button>}</div>
            {mode === 'motion' && video?.range && <button className="quiet-button first-frame-button" onClick={() => setFrameModal(true)}><Icon name="image" size={14}/>{firstFrameSlot ? tr('Change the edited first frame', 'Trocar o primeiro quadro editado', 'Cambiar el primer fotograma editado') : tr('Edit the first frame (FIBO or upload)', 'Editar o primeiro quadro (FIBO ou upload)', 'Editar el primer fotograma (FIBO o subir)')}</button>}
            <p className="micro-copy">{draggingPictures ? tr('Drop to add references', 'Solte para adicionar referências', 'Suelta para añadir referencias') : mode === 'headswap' ? tr('One clear photo of the new face. The head is placed on the person in the video.', 'Uma foto nítida do novo rosto. A cabeça é aplicada na pessoa do vídeo.', 'Una foto nítida del nuevo rostro. La cabeza se aplica a la persona del vídeo.') : tr('JPG, PNG, WebP, GIF · 25 MB each. Slots keep their numbers.', 'JPG, PNG, WebP, GIF · 25 MB cada. Os slots mantêm seus números.', 'JPG, PNG, WebP, GIF · 25 MB cada. Los slots conservan sus números.')}</p>
          </section>}
          <section className="input-card surface generation-settings-card" id="generation-settings"/>
          <section className="input-card surface output-settings"><div className="label-row"><h2><span className="step-number">03</span>{t.output}</h2></div>{mode !== 'sharpness' && qualityRow}
            <div className="setting-row"><label htmlFor="keep-audio">{t.audio}</label><button id="keep-audio" className="toggle" role="switch" aria-label={t.audio} aria-checked={keepAudio} onClick={() => setKeepAudio(v => !v)}><span/></button></div>
            <div className="setting-row"><label htmlFor="audio-conditioning">{tr('Audio conditioning', 'Condicionamento de áudio', 'Condicionamiento de audio')}</label><button id="audio-conditioning" className="toggle" role="switch" aria-label={tr('Audio conditioning', 'Condicionamento de áudio', 'Condicionamiento de audio')} aria-checked={audioConditioning} onClick={() => setAudioConditioning(v => !v)}><span/></button></div>
            <div className="model-badge"><span className="model-symbol"><Icon name="spark" size={19}/></span><div><strong>MiniMax H3</strong><small>{mode === 'sharpness' ? 'Little More Sharpness' : t.model}</small></div><span className="mono nc muted">{quality}</span></div>
          </section>
        </aside>

        <section className="canvas-column">
          <div className="canvas-toolbar"><span><i className="status-dot"/>{t.workspace}<small className="mono muted">/ {modeName(mode)}</small></span><span className="mono muted">{working ? tr('Building prompt', 'Criando prompt', 'Creando prompt') : video ? tr('Source preview', 'Prévia do guia', 'Vista previa de la guía') : t.stIdle}</span></div>
          <div className={'stage ' + (video ? 'has-video' : '')}>
            <div className="blob blob-a"/><div className="blob blob-b"/>
            {!video ? <div className="empty-stage"><div className="ring ring-one"/><div className="ring ring-two"/><div className="orbit-dot"/><div className="stage-message"><span className="eyebrow accent">{t.idleKicker}</span><h2>{t.idleTitle1}<br/><span>{t.idleTitle2}</span></h2><p>{t.idleSub}</p><button className="quiet-button" onClick={() => videoInput.current?.click()}><Icon name="plus" size={17}/>{t.addVideo}</button></div></div> : <div className="preview-panes"><div className="source-pane"><span className="badge mono">{t.source}</span><SubjectVideo url={video.url} range={video.range} subjects={mode === 'sharpness' ? [] : subjects} pickingId={mode === 'sharpness' ? null : pickingId} onAnchor={(id, anchor) => {setSubjects(current => current.map(s => s.id === id ? {...s, anchors: [...s.anchors.filter(a => Math.abs(a.time_seconds - anchor.time_seconds) > .05), anchor]} : s)); setPickingId(null);}} onDuration={(duration, width, height) => {setVideo(v => v?.url === video.url ? {...v, duration} : v); if (width && height) setGuideSize({width, height});}}/>{video.range && <span className="badge range-label mono nc">{formatTime(video.range.start)} / {formatTime(video.range.end)}</span>}</div><div className="output-pane"><span className="badge mono accent">{t.outputLabel}</span>{generationJob && !['completed','failed','cancelled','awaiting_approval'].includes(generationJob.status) ? <div className="live-stage">{generationJob.sampling_preview_url ? <><img src={generationJob.sampling_preview_url} alt={tr('Live generation preview', 'Prévia da geração ao vivo', 'Vista previa en vivo')}/><span className="live-caption">{tr('Live preview · approximate', 'Prévia ao vivo · aproximada', 'Vista previa en vivo · aproximada')}</span></> : <Icon name="spark" size={42}/>}<JobProgress job={generationJob} lang={lang}/></div> : generationJob?.result_url ? <div className="result-stage"><video key={generationJob.id} controls playsInline src={generationJob.result_url}/><div className="result-toolbar">
                <div className="result-row">
                  <a className="primary result-download" href={generationJob.result_url} download="henge-result.mp4"><Icon name="download" size={15}/>{tr('Download video', 'Baixar vídeo', 'Descargar vídeo')}</a>
                  <details className="result-more">
                    <summary className="quiet-button">{tr('More', 'Mais', 'Más')}<span aria-hidden="true" className="result-caret">▾</span></summary>
                    <div className="result-menu" role="menu" onClick={e => {(e.currentTarget.parentElement as HTMLDetailsElement).open = false;}}>
                      {generationJob.comparison_url && <a role="menuitem" href={generationJob.comparison_url} download="henge-comparison.mp4"><Icon name="film" size={14}/><span>{tr('Comparison', 'Comparação', 'Comparación')}<small>{tr('Guide and result side by side', 'Guia e resultado lado a lado', 'Guía y resultado lado a lado')}</small></span></a>}
                      {generationJob.comparison_url && <a role="menuitem" href={`/api/backend/jobs/${generationJob.id}/comparison-with-refs`} download="henge-guide-result-references.mp4"><Icon name="pictures" size={14}/><span>{tr('Comparison + references', 'Comparação + referências', 'Comparación + referencias')}<small>{tr('Adds the reference pictures', 'Inclui as imagens de referência', 'Incluye las imágenes de referencia')}</small></span></a>}
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
          {video?.range && (!fixedRecipe || mode === 'headswap') && <SubjectBindings subjects={subjects} onChange={setSubjects} representation={guideRepresentation} onRepresentation={setGuideRepresentation} pictures={pictures} lang={lang} pickingId={pickingId} onPick={setPickingId} onPrompt={() => setNative(true)} mode={mode} markOpacity={markOpacity} onMarkOpacity={setMarkOpacity}/>}
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
              {prompt.trim() && <span className="read-in"><label>{tr('Read in', 'Ler em', 'Leer en')} <select value={readLang} onChange={e => setReadLang(e.target.value as Language)}><option value="pt">Português</option><option value="es">Español</option><option value="en">English</option></select></label><button type="button" className="quiet-button" disabled={translating} onClick={readPrompt}>{translating ? tr('Translating…', 'Traduzindo…', 'Traduciendo…') : tr('Show', 'Mostrar', 'Mostrar')}</button></span>}
            </div>}
            {!fixedRecipe && translation && translation.source === prompt && <div className="prompt-translation"><span className="eyebrow muted">{tr('For reading only: the model gets the English text above.', 'Só para leitura: o modelo recebe o texto em inglês acima.', 'Solo para leer: el modelo recibe el texto en inglés de arriba.')}</span><pre>{translation.text}</pre></div>}
            {!fixedRecipe && invalid.length > 0 && <p className="validation missing-pictures" role="alert">{tr('Missing in the prompt:', 'Falta no prompt:', 'Falta en el prompt:')} {invalid.map(tag => {const slot = Number(tag.match(/\d+/)?.[0]); const bring = bringSlots.find(b => b.slot === slot); return `Picture ${slot}${bring ? ` (${bring.label[lang]})` : ''}`;}).join(', ')}. {tr('Add the picture, or remove the tag from the prompt.', 'Adicione a imagem ou tire a marcação do prompt.', 'Añade la imagen o quita la etiqueta del prompt.')} <button type="button" className="quiet-button" onClick={() => imageInput.current?.click()}>{tr('Add picture', 'Adicionar imagem', 'Añadir imagen')}</button></p>}
            {!fixedRecipe && native && <pre className="native-preview">{nativePrompt(executionPrompt) || tr('Your H3 prompt will appear here.', 'Seu prompt H3 aparecerá aqui.', 'Tu prompt H3 aparecerá aquí.')}</pre>}
            <div className="prompt-footer">{!fixedRecipe && <><span className="eyebrow muted">{t.insert}</span><div className="mention-chips">{mentions.map(tag => <button key={tag} className="chip mono nc" onClick={() => insertTag(tag)}>{tag}</button>)}{!mentions.length && <span className="muted">—</span>}</div></>}<div className="prompt-generation-actions" id="prompt-generation-actions"/></div>
          </section>
          <input hidden ref={importSettingsInput} type="file" accept="application/json,.json" onChange={e => {importSettings(e.target.files?.[0]); e.target.value = '';}}/>
          <GenerationPanel key={importRevision} onEnhanceChange={setEnhanceOn} registerControls={controls => {panelControls.current = controls;}} freshRevision={freshRevision} requestedProfile={requestedProfile} initialSettings={importedSettings} onSelectJob={selectServerJob} onImportSettings={() => importSettingsInput.current?.click()} onShareSettings={options => {const direction = makeRequest(); if (direction) downloadJSON({kind: 'henge_settings', schema_version: 1, direction, generation: options}, 'henge-shared-settings.json');}} mode={mode} request={makeRequest()} video={video?.file || null} pictures={activePictures} canSubmit={canExport} lang={lang} requestedJobId={pendingAutoPromptJob} onResult={job => {setGenerationJob(job); if (job.id === pendingAutoPromptJob && job.plan && job.status === 'awaiting_approval') {setPrompt(job.plan.prompt); setPendingAutoPromptJob(null);}}}/>
          </section>
        </section>

        <aside className="direction-panel"><section className="surface pipeline-card"><span className="eyebrow muted">{t.pipeline}</span><div className="pipeline-list">{[[!!video?.range, t.p1, t.p1s], [maxPictures === 0 || activePictures.length > 0, t.p2, maxPictures === 0 ? tr('Not needed', 'Não necessárias', 'No necesarias') : `${activePictures.length} ${t.p2s}`], [fixedRecipe || (!!prompt.trim() && !invalid.length), t.p3, fixedRecipe ? tr('Automatic', 'Automática', 'Automática') : t.p3s], [generationJob?.status === 'completed', tr('Generate video', 'Gerar vídeo', 'Generar vídeo'), generationJob?.status === 'completed' ? tr('Video ready', 'Vídeo pronto', 'Vídeo listo') : tr('Review, then generate', 'Revise e gere', 'Revisa y genera')]].map(([ok, title, sub], i) => <div className={'pipeline-item ' + (ok ? 'complete' : '')} key={String(title)}><span className="pipeline-circle">{ok && <Icon name="check" size={11}/>}</span><div><strong>{title}</strong><small>{sub}</small></div>{i === 3 && <span className="mono step-end">04</span>}</div>)}</div></section>
          <section className="surface recent-card"><div className="label-row"><span className="eyebrow muted">{t.recent}</span><button className="text-link" onClick={() => setView('history')}>{t.viewAll} →</button></div>{recentJobs.length ? recentJobs.map(j => <button className={'recent-item' + (generationJob?.id === j.id ? ' active' : '')} key={j.id} onClick={() => panelControls.current?.selectJob(j.id)}><span className={'recent-thumb ' + (j.mode === 'swap' ? 'th-b' : 'th-a')}>{j.result_url ? <video muted playsInline preload="metadata" src={j.result_url + '#t=0.5'}/> : <Icon name="film" size={16}/>}</span><span><strong>{j.project || modeName((j.mode || 'swap') as Mode)}</strong><small><i style={{background: j.status === 'completed' ? '#48d17a' : j.status === 'failed' ? '#ef5a50' : ['cancelled'].includes(j.status) ? '#777185' : '#f0c35a'}}/>{modeName((j.mode || 'swap') as Mode)} · {jobStatusLabel(j.status, lang)}</small></span></button>) : <div className="recent-empty"><Icon name="clock" size={22}/><p>{tr('Your generations will appear here.', 'Suas gerações aparecerão aqui.', 'Tus generaciones aparecerán aquí.')}</p></div>}</section>
          <p className="direction-tip"><span className="eyebrow accent">Tip</span> — {({swap: t.tipSwap, motion: t.tipMotion, headswap: tr('Use a front-facing, well-lit face. Clips where the head stays visible and not too small work best.', 'Use um rosto de frente e bem iluminado. Funciona melhor quando a cabeça aparece bem e não é pequena.', 'Usa un rostro de frente y bien iluminado. Funciona mejor si la cabeza se ve bien y no es pequeña.'), sharpness: tr('Run it as a second pass on a finished generation: pick it from "Use a video generated in the studio".', 'Use como segunda passada numa geração pronta: escolha em "Usar um vídeo gerado no estúdio".', 'Úsalo como segunda pasada sobre una generación: elígela en "Usar un vídeo generado en el estudio".')})[mode]}</p>
        </aside>
      </main>


    </div>

    {view === 'history' && <main className="history-page"><div className="section-top"><div><span className="eyebrow accent">{t.history} · {serverJobs.length}</span><h1>{tr('Your generations', 'Suas gerações', 'Tus generaciones')}</h1><p>{tr('Everything rendered on this Henge. Open one to see its result, plan and settings, or to run it again.', 'Tudo o que foi gerado neste Henge. Abra uma geração para ver o resultado, o plano e os ajustes, ou para rodar de novo.', 'Todo lo generado en este Henge. Abre una para ver el resultado, el plan y los ajustes, o para repetirla.')}</p></div><div className="history-tools"><input className="history-search" type="search" value={historySearch} onChange={e => setHistorySearch(e.target.value)} placeholder={tr('Search by name, mode or model', 'Buscar por nome, modo ou modelo', 'Buscar por nombre, modo o modelo')} aria-label={tr('Search generations', 'Buscar gerações', 'Buscar generaciones')}/>{historyModels.length > 1 && <select className="history-model" value={historyModel} onChange={e => setHistoryModel(e.target.value)} aria-label={tr('Model', 'Modelo', 'Modelo')}><option value="all">{tr('All models', 'Todos os modelos', 'Todos los modelos')}</option>{historyModels.map(id => <option key={id} value={id}>{modelLabels[id] || id}</option>)}</select>}<div className="filter-chips">{(['all', ...MODES] as const).map(key => <button key={key} className={historyFilter === key ? 'active' : ''} aria-pressed={historyFilter === key} onClick={() => setHistoryFilter(key)}>{key === 'all' ? t.all : modeName(key)}</button>)}</div></div></div>
      <div className="generation-grid">{historyJobs.slice(0, historyShown).map(j => {
        const open = () => {panelControls.current?.selectJob(j.id); setView('studio');};
        const name = `henge-${j.id.slice(0, 8)}`;
        const downloads = [
          j.result_url && {href: j.result_url, file: `${name}.mp4`, label: tr('Video', 'Vídeo', 'Vídeo')},
          j.comparison_url && {href: j.comparison_url, file: `${name}-comparison.mp4`, label: tr('Comparison', 'Comparação', 'Comparación')},
          j.comparison_url && {href: `/api/backend/jobs/${j.id}/comparison-with-refs`, file: `${name}-comparison-references.mp4`, label: tr('+ references', '+ referências', '+ referencias')},
          j.status === 'completed' && j.guide_preview_url && {href: j.guide_preview_url, file: `${name}-guide.mp4`, label: tr('Guide', 'Guia', 'Guía')},
        ].filter(Boolean) as {href: string; file: string; label: string}[];
        return <div key={j.id} className={'history-card generation-card surface' + (generationJob?.id === j.id ? ' selected' : '')} style={{'--item-accent': MODE_STYLE[(j.mode || 'swap') as Mode]?.accent} as CSSProperties}>
          <button type="button" className="generation-open" onClick={open} aria-label={`${tr('Open', 'Abrir', 'Abrir')} ${j.project || 'Henge'}`}><div className={'history-art ' + (j.mode === 'swap' ? 'th-b' : 'th-a')}>{j.result_url ? <video muted playsInline preload="metadata" src={j.result_url + '#t=0.5'}/> : <Icon name="film" size={30}/>}<span className={'badge mono mode-badge ' + (j.mode || '')}>{modeName((j.mode || 'swap') as Mode)}</span>{typeof j.duration === 'number' && <span className="badge duration-badge mono nc">{j.duration.toFixed(1)}s</span>}</div><div className="history-caption"><strong>{j.project || 'Henge'}</strong><span className="mono nc muted">{dateLabel(new Date(j.created * 1000).toISOString())}{j.quality ? ` · ${j.quality}` : ''}</span>{(() => {const secs = j.run_seconds ?? (j.run_started ? Date.now() / 1000 - j.run_started : undefined); return secs !== undefined ? <span className="mono nc muted job-time">⏱ {secs >= 60 ? `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s` : `${Math.round(secs)}s`}{j.run_started && j.run_seconds === undefined ? '…' : ''}</span> : null;})()}{jobModel(j).label && <span className="mono nc muted job-model">{jobModel(j).label}{j.options?.conditioning_mode === 'tara' ? ' · TARA' : ''}</span>}<span className={'job-status ' + j.status}>{jobStatusLabel(j.status, lang)}</span></div></button>
          {downloads.length > 0 && <div className="generation-downloads">{downloads.map(d => <a key={d.file} className="quiet-button" href={d.href} download={d.file}><Icon name="download" size={12}/>{d.label}</a>)}</div>}
        </div>;
      })}{!serverJobs.length && <div className="history-empty"><span className="empty-emblem"><Icon name="clock" size={30}/></span><h2>{tr('Nothing generated yet.', 'Nada gerado ainda.', 'Nada generado todavía.')}</h2><button className="primary" onClick={() => setView('studio')}><Icon name="plus" size={16}/>{tr('Open studio', 'Abrir estúdio', 'Abrir estudio')}</button></div>}{serverJobs.length > 0 && !historyJobs.length && <p className="muted history-none">{tr('No generation matches this search.', 'Nenhuma geração encontrada com essa busca.', 'Ninguna generación coincide con la búsqueda.')}</p>}</div>
      <div ref={historyEnd} className="history-end">{historyShown < historyJobs.length ? tr('Loading more…', 'Carregando mais…', 'Cargando más…') : historyJobs.length > 24 ? tr('That is all.', 'Isso é tudo.', 'Eso es todo.') : ''}</div>
      <details className="saved-directions"><summary>{tr('Saved directions', 'Direções salvas', 'Direcciones guardadas')} · {history.length} <small className="muted">{tr('prompts and settings exported on this device', 'prompts e ajustes exportados neste dispositivo', 'prompts y ajustes exportados en este dispositivo')}</small></summary>
      <div className="history-layout"><div className="history-grid">{filteredHistory.map(h => <button key={h.id} className={'history-card surface ' + (selected?.id === h.id ? 'selected' : '')} style={{'--item-accent': MODE_STYLE[h.request.mode].accent} as CSSProperties} onClick={() => setSelectedId(h.id)}><div className={'history-art ' + (h.request.mode === 'swap' ? 'th-b' : 'th-a')}>{h.thumbnail ? <img src={h.thumbnail} alt={h.request.video.name}/> : <Icon name="film" size={30}/>}<span className={'badge mono mode-badge ' + h.request.mode}>{modeName(h.request.mode)}</span><span className="badge duration-badge mono nc">{h.request.video.duration.toFixed(1)}s</span><span className="badge draft-badge mono">{tr('Direction', 'Direção', 'Dirección')}</span></div><div className="history-caption"><strong>{h.request.project}</strong><span className="mono nc muted">{dateLabel(h.created)} · {h.request.quality}</span><span className="stars" aria-label={`${h.rating}/5`}>{'★'.repeat(h.rating)}<span>{'☆'.repeat(5 - h.rating)}</span></span></div></button>)}{!filteredHistory.length && <div className="history-empty"><span className="empty-emblem"><Icon name="clock" size={30}/></span><h2>{history.length ? tr('No directions in this mode.', 'Nenhuma direção neste modo.', 'No hay direcciones en este modo.') : tr('Your next idea starts here.', 'Sua próxima ideia começa aqui.', 'Tu próxima idea empieza aquí.')}</h2><p>{tr('Export a direction from the Studio to save its prompt, settings and source preview.', 'Exporte uma direção no Estúdio para guardar o prompt, os ajustes e a prévia do guia.', 'Exporta una dirección del Estudio para guardar el prompt, los ajustes y la vista previa de la guía.')}</p><button className="primary" onClick={() => setView('studio')}><Icon name="plus" size={16}/>{tr('Open studio', 'Abrir estúdio', 'Abrir estudio')}</button></div>}</div>
        {selected && <aside className="history-detail surface"><div className={'detail-art ' + (selected.request.mode === 'swap' ? 'th-b' : 'th-a')}>{selected.thumbnail ? <img src={selected.thumbnail} alt={selected.request.video.name}/> : <Icon name="film" size={40}/>}<span className="badge mono">{tr('Source preview', 'Prévia do guia', 'Vista previa de la guía')}</span></div><div className="detail-body"><h2>{selected.request.project}</h2><p className="detail-prompt">{selected.request.editor_prompt}</p><div className="detail-facts">{[[t.mode, modeName(selected.request.mode)], [t.duration, `${selected.request.video.duration.toFixed(1)}s`], [t.quality, selected.request.quality], [t.created, dateLabel(selected.created)]].map(([label, value]) => <div key={label}><span className="eyebrow muted">{label}</span><strong>{value}</strong></div>)}</div><div className="feedback-panel"><div className="label-row"><strong>{tr('Rate this direction', 'Avalie esta direção', 'Valora esta dirección')}</strong><small className="muted">{selected.rating ? t.rl[selected.rating - 1] : t.noRating}</small></div><div className="rating-buttons" role="group" aria-label={tr('Direction rating', 'Avaliação da direção', 'Valoración de la dirección')}>{[1, 2, 3, 4, 5].map(n => <button key={n} aria-label={`${n} / 5`} aria-pressed={selected.rating === n} className={selected.rating >= n ? 'filled' : ''} onClick={() => patchHistory(selected.id, {rating: selected.rating === n ? 0 : n})}>{selected.rating >= n ? '★' : '☆'}</button>)}</div><div className="feedback-tags">{FEEDBACK.map((tag, i) => <button key={tag} aria-pressed={selected.tags.includes(tag)} className={selected.tags.includes(tag) ? 'chosen' : ''} onClick={() => patchHistory(selected.id, {tags: selected.tags.includes(tag) ? selected.tags.filter(x => x !== tag) : [...selected.tags, tag]})}>{feedbackLabels[i]}</button>)}</div></div><div className="detail-actions"><button className="primary" onClick={() => downloadJSON(selected.request, 'henge-request.json')}><Icon name="download" size={15}/>{t.export}</button><button className="quiet-button" onClick={() => setModal('share')}><Icon name="share" size={15}/>{tr('Share preset', 'Compartilhar template', 'Compartir plantilla')}</button><button className="quiet-button reuse-button" onClick={() => reuse(selected)}>{t.reuse}</button><button className="icon-btn delete-button" aria-label={t.del} onClick={() => setModal('delete')}><Icon name="trash" size={17}/></button></div></div></aside>}
      </div>
      </details>
    </main>}

    {view === 'community' && <main className="community-page"><span className="eyebrow accent">{t.community}</span><h1>{tr('Find your next idea.', 'Encontre sua próxima ideia.', 'Encuentra tu próxima idea.')}</h1><p className="community-intro">{tr('Open an example in Character Swap or Motion transfer, change the pictures, and make it yours.', 'Abra um exemplo no Character Swap ou no Motion transfer, troque as imagens e crie sua versão.', 'Abre un ejemplo en Character Swap o Motion transfer, cambia las imágenes y crea tu versión.')}</p>
      <section className="templates-section"><div className="section-top"><div><span className="eyebrow accent">{tr('Examples', 'Exemplos', 'Ejemplos')} · {COMMUNITY.length}</span><h2>{tr('Start from a real case.', 'Comece de um caso pronto.', 'Empieza con un caso listo.')}</h2><p>{tr('Guide video, references and prompt load together. Add your own picture where it says "You".', 'Vídeo guia, referências e prompt carregam juntos. Adicione sua foto onde aparece "Você".', 'Vídeo guía, referencias y prompt se cargan juntos. Añade tu foto donde dice "Tú".')}</p></div></div>
        <div className="template-grid">{COMMUNITY.map(preset => <div key={preset.id} className="template-card community-card"><div className="template-art"><img src={`/community/${preset.id}/poster.jpg`} alt="" loading="lazy"/>{loadingCommunity === preset.id && <span className="template-cta">{tr('Loading…', 'Carregando…', 'Cargando…')}</span>}<div className="template-slots">{[...preset.refs, ...preset.bring].sort((a, b) => a.slot - b.slot).map(r => <span key={r.slot} className={preset.bring.includes(r) ? 'bring' : ''}><Icon name="swap" size={10}/>{r.label[lang]}</span>)}</div></div><div className="template-caption"><h3>{preset.title[lang]}</h3><p>{preset.prompt[lang]}</p></div><div className="community-modes">{(['swap', 'motion'] as Mode[]).map(m => <button key={m} className="quiet-button" disabled={!!loadingCommunity} onClick={() => useCommunity(preset, m)}><Icon name={m} size={14}/><span>{modeName(m)}</span></button>)}</div></div>)}</div>
      </section>
      </main>}


    <footer className="app-footer"><span className="mono">Henge <Icon name="spark" size={12}/> {tr('An open canvas for moving ideas.', 'Uma tela aberta para ideias em movimento.', 'Un lienzo abierto para ideas en movimiento.')}</span><span>{tr('Made for creators. Built on Comfy.', 'Feito para criadores. Construído com Comfy.', 'Hecho para creadores. Construido con Comfy.')}</span></footer>
    {notice && <div className="notification" role="status" aria-live="polite"><span>{notice}</span><button className="icon-btn" aria-label={tr('Dismiss notification', 'Fechar notificação', 'Cerrar notificación')} onClick={() => setNotice('')}><Icon name="close" size={16}/></button></div>}
    <dialog className="action-modal" ref={dialog} onCancel={e => {e.preventDefault(); setModal(null);}} aria-labelledby="action-title"><button className="modal-close icon-btn" aria-label={t.cancel} onClick={() => setModal(null)}><Icon name="close" size={18}/></button><span className="modal-emblem"><Icon name={modal === 'delete' ? 'trash' : 'share'} size={26}/></span><h2 id="action-title">{modal === 'delete' ? tr('Delete this direction?', 'Excluir esta direção?', '¿Eliminar esta dirección?') : tr('Share a direction', 'Compartilhe uma direção', 'Comparte una dirección')}</h2><p>{modal === 'delete' ? tr('This removes its local history entry. Your original media files are unchanged.', 'Isso remove a entrada do histórico local. Seus arquivos originais permanecem intactos.', 'Esto elimina la entrada del historial local. Tus archivos originales no cambian.') : tr('Export the prompt and settings as a JSON preset. Media, ratings and local file names are not included.', 'Exporte o prompt e os ajustes como um template JSON. Mídia, avaliações e nomes de arquivos locais não são incluídos.', 'Exporta el prompt y los ajustes como plantilla JSON. No incluye archivos, valoraciones ni nombres de archivos locales.')}</p><div className="modal-actions"><button className="quiet-button" onClick={() => setModal(null)}>{t.cancel}</button><button className="primary" onClick={() => {if (!selected) return; if (modal === 'delete') {setHistory(h => h.filter(x => x.id !== selected.id)); setSelectedId(null);} else {const r = selected.request; downloadJSON({schema_version: 1, kind: 'henge_prompt_preset', title: r.project, mode: r.mode, quality: r.quality, prompt: r.editor_prompt, processing: r.processing, audio_conditioning: r.audio_conditioning, output_audio: r.output_audio, reference_slots: r.pictures.map(p => p.slot)}, 'henge-preset.json');} setModal(null);}}>{modal === 'delete' ? t.del : tr('Download preset', 'Baixar template', 'Descargar plantilla')}</button></div></dialog>
  </div>;
}
