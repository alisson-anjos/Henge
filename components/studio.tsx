'use client';

import {useEffect, useRef, useState, type CSSProperties} from 'react';
import {MAX_PICTURES, nativePrompt, invalidReferences, type Mode} from '../lib/prompt';
import {imageData, videoFrames, type Picture} from '../lib/media';
import {DESIGN_COPY, type Language} from '../lib/design-copy';
import {TEMPLATES, type StudioTemplate} from '../lib/templates';
import {downloadJSON, FEEDBACK, HISTORY_KEY, HISTORY_LIMIT, readHistory, type DirectionRequest, type SavedDirection} from '../lib/history';
import VideoTrimModal, {type ClipRange} from './video-trim-modal';
import GenerationPanel, {type GenerationJob} from './generation-panel';
import SubjectBindings, {SubjectVideo} from './subject-bindings';
import {bindingPrompt, readSubjectBindings, type SubjectBinding, type GuideRepresentation} from '../lib/subject-bindings';

function Icon({name, size = 20}: {name: string; size?: number}) {
  const paths: Record<string, React.ReactNode> = {
    plus: <path d="M12 5v14M5 12h14"/>, arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
    film: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 4v16M17 4v16M3 9h4m10 0h4M3 15h4m10 0h4"/></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1"/><path d="m3 17 5-5 4 4 4-6 5 7"/></>,
    swap: <path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>,
    motion: <path d="M3 12h4l3-8 4 16 3-8h4"/>,
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
type View = 'studio' | 'history' | 'community';
const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, '0')}`;

export default function Studio() {
  const [lang, setLang] = useState<Language>('pt');
  const [mode, setMode] = useState<Mode>('swap');
  const [view, setView] = useState<View>('studio');
  const [pictures, setPictures] = useState<Picture[]>([]);
  const [expectedSlots, setExpectedSlots] = useState<number[]>([]);
  const [video, setVideo] = useState<GuideVideo | null>(null);
  const [editingVideo, setEditingVideo] = useState(false);
  const [subjects, setSubjects] = useState<SubjectBinding[]>([]);
  const [guideRepresentation, setGuideRepresentation] = useState<GuideRepresentation>('original');
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  const [pendingAutoPromptJob, setPendingAutoPromptJob] = useState<string | null>(null);
  const [pickingId, setPickingId] = useState<string | null>(null);
  const [guideSignature, setGuideSignature] = useState('');
  const [prompt, setPrompt] = useState('');
  const [intent, setIntent] = useState('');
  const [auto, setAuto] = useState(false);
  const [working, setWorking] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [notice, setNotice] = useState('');
  const [native, setNative] = useState(false);
  const [quality, setQuality] = useState('720p');
  const [project, setProject] = useState('');
  const [ready, setReady] = useState(false);
  const [draggingPictures, setDraggingPictures] = useState(false);
  const [audioConditioning, setAudioConditioning] = useState(false);
  const [keepAudio, setKeepAudio] = useState(true);
  const [shotSeconds, setShotSeconds] = useState(4.5);
  const [timelineFps, setTimelineFps] = useState(24);
  const [contextFrames, setContextFrames] = useState(22);
  const [history, setHistory] = useState<SavedDirection[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState<Mode | 'all'>('all');
  const [templateFilter, setTemplateFilter] = useState('all');
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
  const accent = mode === 'swap' ? '#D6FF4B' : '#AA8BFF';
  const style = {'--accent': accent, '--accent-rgb': mode === 'swap' ? '214,255,75' : '170,139,255'} as CSSProperties;
  const modeName = (value: Mode) => value === 'swap' ? t.swap : t.motion;
  const busy = working || exporting;

  useEffect(() => () => {
    live.current.pictures.forEach(p => URL.revokeObjectURL(p.url));
    if (live.current.video) URL.revokeObjectURL(live.current.video.url);
  }, []);
  useEffect(() => {
    try {
      const s = JSON.parse(localStorage.getItem('openjutsu-draft') || 'null');
      if (s && typeof s === 'object') {
        setPrompt(typeof s.prompt === 'string' ? s.prompt : '');
        setSubjects(readSubjectBindings(s.subjects));
        setGuideRepresentation(s.guideRepresentation === '2d' ? '2d' : s.guideRepresentation === '3d' ? '3d' : 'original');
        setGuideSignature(typeof s.guideSignature === 'string' ? s.guideSignature : '');
        setIntent(typeof s.intent === 'string' ? s.intent : '');
        setMode(s.mode === 'motion' ? 'motion' : 'swap');
        setProject(typeof s.project === 'string' && s.project !== 'Untitled project' ? s.project : '');
        setQuality(['480p', '720p', '1080p'].includes(s.quality) ? s.quality : '720p');
        setAudioConditioning(s.audioConditioning === true);
        setKeepAudio(s.keepAudio !== false);
        setShotSeconds(Math.min(15, Math.max(1, Number(s.shotSeconds) || 4.5)));
        setTimelineFps(Math.min(120, Math.max(1, Number(s.timelineFps) || 24)));
        setContextFrames([5, 22, 39].includes(s.contextFrames) ? s.contextFrames : 22);
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
    try { localStorage.setItem('openjutsu-draft', JSON.stringify({prompt, intent, mode, project, quality, audioConditioning, keepAudio, shotSeconds, timelineFps, contextFrames, lang, subjects, guideRepresentation, guideSignature})); } catch { /* Editing still works without draft persistence. */ }
  }, [ready, prompt, intent, mode, project, quality, audioConditioning, keepAudio, shotSeconds, timelineFps, contextFrames, lang, subjects, guideRepresentation, guideSignature]);
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
  const contextWindow = selectedDuration > 15;
  const shotFrames = Math.max(22, Math.floor((Math.round(shotSeconds * 24) - 5) / 17) * 17 + 5);
  const estimatedShots = selectedDuration ? Math.ceil(Math.round(selectedDuration * timelineFps) / shotFrames) : 0;
  const subjectErrors = subjects.some(s => !s.anchors.length || !s.picture_slots.length || s.picture_slots.some(n => !pictures.some(p => p.slot === n)) || s.anchors.some(a => !video?.range || a.time_seconds < video.range.start || a.time_seconds >= video.range.end));
  const executionPrompt = prompt + (subjects.length && !subjectErrors ? '\n\n' + bindingPrompt(subjects, guideRepresentation) : '');
  const canExport = !!video?.range && !editingVideo && pictures.length > 0 && !!prompt.trim() && !invalid.length && !subjectErrors && ready && !busy;
  const selected = history.find(h => h.id === selectedId) || null;
  const filteredHistory = history.filter(h => historyFilter === 'all' || h.request.mode === historyFilter);
  const filteredTemplates = TEMPLATES.filter(x => templateFilter === 'all' || x.cat === templateFilter);
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
    const slots = [...new Set([...expectedSlots, ...Array.from({length: MAX_PICTURES}, (_, i) => i + 1)])];
    const available = slots.filter(i => !pictures.some(p => p.slot === i));
    const valid = Array.from(files).filter(f => ['image/jpeg', 'image/png', 'image/webp'].includes(f.type) && f.size <= 25 * 1024 * 1024);
    setNotice(valid.length !== files.length ? tr('Use JPG, PNG or WebP, up to 25 MB each.', 'Use JPG, PNG ou WebP, até 25 MB por imagem.', 'Usa JPG, PNG o WebP, hasta 25 MB por imagen.') : valid.length > available.length ? tr('Up to 11 reference pictures.', 'Até 11 imagens de referência.', 'Hasta 11 imágenes de referencia.') : '');
    setPictures(current => [...current, ...valid.slice(0, available.length).map((file, i) => ({slot: available[i], file, url: URL.createObjectURL(file)}))].sort((a, b) => a.slot - b.slot));
  }
  function addVideo(files: FileList | null) {
    if (!files?.length) return;
    if (files.length > 1 || video) { setNotice(tr('Use one guide video. Remove the current guide to replace it.', 'Use um vídeo guia. Remova o atual para substituí-lo.', 'Usa un vídeo guía. Elimina el actual para reemplazarlo.')); return; }
    const file = files[0];
    if (!file.type.startsWith('video/') || file.size > 500 * 1024 * 1024) { setNotice(tr('Choose a video up to 500 MB.', 'Escolha um vídeo de até 500 MB.', 'Elige un vídeo de hasta 500 MB.')); return; }
    const signature = JSON.stringify([file.name, file.size, file.lastModified]);
    if (signature !== guideSignature) setSubjects(current => current.map(s => ({...s, anchors: []})));
    setGuideSignature(signature); setPickingId(null);
    setVideo({file, url: URL.createObjectURL(file)}); setEditingVideo(true); setNotice('');
  }
  function removeVideo() { if (video) URL.revokeObjectURL(video.url); setVideo(null); setPickingId(null); }
  function removePicture(slot: number) {
    const item = pictures.find(p => p.slot === slot);
    if (item) URL.revokeObjectURL(item.url);
    setPictures(pictures.filter(p => p.slot !== slot));
    setSubjects(current => current.map(s => ({...s, picture_slots: s.picture_slots.filter(n => n !== slot)})));
  }
  async function autoPrompt() {
    if (!video?.range || editingVideo || !pictures.length || !intent.trim()) { setNotice(tr('Add a guide, references and a short brief.', 'Adicione um guia, referências e uma breve descrição.', 'Añade una guía, referencias y una breve descripción.')); return; }
    setWorking(true); setNotice('');
    try {
      const request = makeRequest(); if (!request) throw Error('Select a guide interval.');
      request.prompt = nativePrompt(intent + (subjects.length && !subjectErrors ? '\n' + bindingPrompt(subjects, guideRepresentation) : ''));
      request.editor_prompt = intent;
      const body = new FormData(); body.set('direction', JSON.stringify(request)); body.set('options', JSON.stringify({profile: mode === 'motion' ? 'motion' : 'character', fibo: 'auto', seed: 42, steps: 8, clip_fps: 2})); body.set('video', video.file);
      pictures.forEach(p => body.set(`picture_${p.slot}`, p.file));
      const response = await fetch('/api/backend/jobs', {method: 'POST', body}); const result = await response.json();
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
      processing: {mode: contextWindow ? 'context_window' : 'single', max_shots: 0, requested_seconds_per_shot: shotSeconds, frames_per_shot: shotFrames, timeline_fps: timelineFps, frame_grid: '17n+5', trim_to_source_length: true, join: 'ordered', execution_status: 'comfy_backend', context_frames: contextFrames},
      audio_conditioning: {enabled: audioConditioning, source: audioConditioning ? 'guide_video' : null},
      output_audio: {keep_source: keepAudio}, prompt: nativePrompt(executionPrompt), editor_prompt: prompt,
      subject_guidance: {representation: guideRepresentation, bindings: subjects, status: 'selection_only', marker_colors_are_output_appearance: false},
      video: {name: video.file.name, source_signature: guideSignature, conditioning: 'guide_latents', source_duration: video.duration, start_seconds: video.range.start, end_seconds: video.range.end, duration: selectedDuration},
      pictures: pictures.map(p => ({slot: p.slot, token: `<Picture ${p.slot}>`, name: p.file.name})), generation_status: 'not_submitted',
    };
  }
  async function exportRequest() {
    if (!canExport) return;
    const request = makeRequest(); if (!request || !video) return;
    // Download in the click gesture; a slow thumbnail decode cannot block the export.
    downloadJSON(request, 'kagemage-request.json'); setExporting(true);
    let thumbnail = '';
    try {
      const frames = await videoFrames(video.file, video.range, 2);
      thumbnail = frames[0]?.data || '';
    } catch { try { if (pictures[0]) thumbnail = await imageData(pictures[0].file, 320); } catch { /* A preview is optional. */ } }
    const item: SavedDirection = {id: (typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `direction-${Date.now()}-${Math.random().toString(36).slice(2)}`), created: new Date().toISOString(), request, thumbnail, rating: 0, tags: []};
    setHistory(current => [item, ...current].slice(0, HISTORY_LIMIT)); setSelectedId(item.id); setExporting(false);
    setNotice(tr('Direction exported and saved to local history.', 'Direção exportada e salva no histórico local.', 'Dirección exportada y guardada en el historial local.'));
  }
  function reuse(item: SavedDirection) {
    const r = item.request;
    removeVideo(); pictures.forEach(p => URL.revokeObjectURL(p.url)); setPictures([]);
    setExpectedSlots(r.pictures.map(p => p.slot)); setMode(r.mode); setQuality(r.quality);
    setSubjects(readSubjectBindings(r.subject_guidance?.bindings)); setGuideRepresentation(r.subject_guidance?.representation === '2d' ? '2d' : r.subject_guidance?.representation === '3d' ? '3d' : 'original'); setGuideSignature(r.video.source_signature || '');
    setProject(r.project); setPrompt(r.editor_prompt); setAudioConditioning(r.audio_conditioning.enabled);
    setKeepAudio(r.output_audio.keep_source); setShotSeconds(r.processing.requested_seconds_per_shot);
    setTimelineFps(r.processing.timeline_fps); setContextFrames(r.processing.context_frames || 22);
    setView('studio'); setAuto(false); setActiveTemplate(null);
    setNotice(tr('Settings restored. Reattach the guide and reference pictures to export again.', 'Ajustes restaurados. Anexe novamente o guia e as referências para exportar.', 'Ajustes restaurados. Vuelve a adjuntar la guía y las referencias para exportar.'));
  }
  function useTemplate(template: StudioTemplate) {
    setActiveTemplate(template.id); setMode(template.mode); setPrompt(template.prompt[lang]); setAuto(false); setView('studio');
    setNotice(tr('Prompt preset applied. Add your own guide and reference pictures.', 'Prompt do template aplicado. Adicione seu vídeo guia e suas referências.', 'Prompt de la plantilla aplicado. Añade tu guía y tus referencias.'));
    window.scrollTo({top: 0, behavior: 'smooth'});
  }
  function patchHistory(id: string, patch: Partial<Pick<SavedDirection, 'rating' | 'tags'>>) { setHistory(current => current.map(h => h.id === id ? {...h, ...patch} : h)); }
  function exportFeedback() {
    const rows = history.filter(h => h.rating).map(h => ({schema_version: 1, kind: 'direction_feedback', id: h.id, created: h.created, request: h.request, rating: h.rating, tags: h.tags, output_video: null}));
    const url = URL.createObjectURL(new Blob([rows.map(r => JSON.stringify(r)).join('\n') + '\n'], {type: 'application/x-ndjson'}));
    const a = document.createElement('a'); a.href = url; a.download = 'kagemage-direction-feedback.jsonl'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const dateLabel = (value: string) => new Intl.DateTimeFormat({en: 'en', pt: 'pt-BR', es: 'es'}[lang], {day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'}).format(new Date(value));
  const feedbackLabels = [tr('Clear identity', 'Identidade definida', 'Identidad definida'), tr('Clear motion', 'Movimento definido', 'Movimiento definido'), tr('Clear preservation', 'Preservação definida', 'Conservación definida'), tr('Prompt ready', 'Prompt pronto', 'Prompt listo')];
  const exportLabel = tr('Export direction', 'Exportar direção', 'Exportar dirección');
  const historyTitle = tr('Your directions', 'Suas direções', 'Tus direcciones');

  return <div className={`app-shell mode-${mode}`} style={style}>
    {editingVideo && video && <VideoTrimModal file={video.file} url={video.url} initial={video.range} onConfirm={(range, duration) => {setVideo(v => v ? {...v, range, duration} : v); setEditingVideo(false);}} onCancel={() => {if (!video.range) removeVideo(); setEditingVideo(false);}}/>}
    <header className="topbar">
      <button className="wordmark" onClick={() => setView('studio')} aria-label="Kagemage Studio"><span className="brandmark"><Icon name="spark" size={23}/></span><strong>Kagemage</strong><span className="alpha mono">Studio · α</span></button>
      <div className="project-field"><label className="mono" htmlFor="project-name">{t.project}</label><input id="project-name" value={project} onChange={e => setProject(e.target.value)} placeholder={t.projectPh}/></div>
      <nav className="main-nav" aria-label={tr('Main navigation', 'Navegação principal', 'Navegación principal')}>
        {(['studio', 'history', 'community'] as View[]).map(v => <button key={v} className={view === v ? 'active' : ''} onClick={() => setView(v)} aria-current={view === v ? 'page' : undefined}>{t[v]}{v === 'history' && history.length > 0 && <span className="count mono">{history.length}</span>}</button>)}
      </nav>
      <span className="draft-status"><i/>{t.draft}</span>
      <div className="topbar-end"><div className="language-switch" role="group" aria-label="Language">{(['en', 'pt', 'es'] as Language[]).map(l => <button key={l} className={'mono ' + (lang === l ? 'active' : '')} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}</div><a className="source-link ghost" href="https://github.com/alisson-anjos/OpenJutsu" target="_blank" rel="noreferrer"><Icon name="github" size={16}/>{t.openSource}</a></div>
    </header>

    {view === 'studio' && <>
      <main className="workspace">
        <aside className="controls">
          <div className="create-heading rise"><span className="eyebrow accent">{t.create}</span><h1>{t.h1a}<br/><span>{t.h1b}</span></h1></div>
          <div className="mode-switch" role="group" aria-label={t.mode}>{(['swap', 'motion'] as Mode[]).map(m => <button key={m} disabled={!ready || busy} className={mode === m ? 'selected' : ''} onClick={() => setMode(m)} aria-pressed={mode === m}><Icon name={m} size={16}/>{modeName(m)}</button>)}</div>
          <p className="mode-description">{mode === 'swap' ? t.swapDesc : t.motionDesc}</p>
          {chosenTemplate && <div className="active-template surface"><Icon name="spark"/><div><span className="eyebrow accent">{t.tplActive}</span><strong>{chosenTemplate.title[lang]}</strong></div><button className="icon-btn" aria-label={t.exitTpl} onClick={() => setActiveTemplate(null)}><Icon name="close" size={15}/></button></div>}
          <section className="input-card surface">
            <div className="label-row"><h2><span className="step-number">01</span>{t.guide}</h2><span className="mono muted">{video ? '01' : '00'} / 01</span></div>
            <input data-testid="guide-input" hidden ref={videoInput} type="file" accept="video/*" onChange={e => {addVideo(e.target.files); e.target.value = '';}}/>
            <div className={'video-drop ' + (video ? 'has-file' : '')} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault(); addVideo(e.dataTransfer.files);}}>
              {video ? <><span className="file-icon"><Icon name="film"/></span><div><strong>{video.file.name}</strong><small>{(video.file.size / 1048576).toFixed(1)} MB · {selectedDuration.toFixed(1)}s {t.selected}</small></div><button className="icon-btn" aria-label={tr('Edit video interval', 'Editar intervalo do vídeo', 'Editar intervalo del vídeo')} onClick={() => setEditingVideo(true)}><Icon name="scissors" size={16}/></button><button className="icon-btn" aria-label={tr('Remove video', 'Remover vídeo', 'Eliminar vídeo')} onClick={removeVideo}><Icon name="close" size={16}/></button></> : <button className="drop-button" onClick={() => videoInput.current?.click()}><span className="upload-icon"><Icon name="upload"/></span><strong>{t.drop}</strong><small>{t.dropSub}</small></button>}
            </div>
            {video?.range && <button className="interval-summary" onClick={() => setEditingVideo(true)}><Icon name="scissors" size={14}/><span className="mono nc">{formatTime(video.range.start)} → {formatTime(video.range.end)}</span><span className="accent mono nc">{selectedDuration.toFixed(1)}s</span></button>}
            {contextWindow && <details className="context-window-panel" open><summary><Icon name="scissors" size={16}/><strong>{t.autoCut}</strong><span className="mini-badge">{t.unlimited}</span></summary><p>{tr('This interval uses short segments joined in order.', 'Este intervalo usa segmentos curtos unidos em sequência.', 'Este intervalo usa segmentos cortos unidos en orden.')}</p><div className="shot-settings"><label>{t.fixedLabel}<input aria-label={t.fixedLabel} type="number" min="1" max="15" step="0.1" value={shotSeconds} onChange={e => setShotSeconds(Math.min(15, Math.max(1, Number(e.target.value) || 4.5)))}/></label><label>Timeline FPS<input aria-label="Timeline FPS" type="number" min="1" max="120" value={timelineFps} onChange={e => setTimelineFps(Math.min(120, Math.max(1, Number(e.target.value) || 24)))}/></label></div><div className="label-row"><span>{t.ctxLen}</span><div className="context-options">{[5, 22, 39].map(f => <button key={f} aria-pressed={contextFrames === f} className={contextFrames === f ? 'chosen' : ''} onClick={() => setContextFrames(f)}>{f}f</button>)}</div></div><small className="muted">{shotFrames}f · 17n+5 · ~{estimatedShots} {t.cutsWord}</small></details>}
          </section>
          <section className={'input-card surface reference-dropzone ' + (draggingPictures ? 'dragging' : '')} onDragEnter={e => {e.preventDefault(); if (e.dataTransfer.types.includes('Files')) {pictureDragDepth.current++; setDraggingPictures(true);}}} onDragOver={e => {e.preventDefault(); e.dataTransfer.dropEffect = 'copy';}} onDragLeave={e => {e.preventDefault(); pictureDragDepth.current = Math.max(0, pictureDragDepth.current - 1); if (!pictureDragDepth.current) setDraggingPictures(false);}} onDrop={e => {e.preventDefault(); e.stopPropagation(); pictureDragDepth.current = 0; setDraggingPictures(false); addPictures(e.dataTransfer.files);}}>
            <div className="label-row"><h2><span className="step-number">02</span>{t.refs}</h2><span className="mono muted">{String(pictures.length).padStart(2, '0')} / 11</span></div>
            <input data-testid="picture-input" hidden ref={imageInput} type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e => {addPictures(e.target.files); e.target.value = '';}}/>
            <div className="reference-grid">{pictures.map(p => <div className="reference" key={p.slot}><img draggable={false} src={p.url} alt={`Picture ${p.slot}: ${p.file.name}`}/><button className="remove-ref" aria-label={`Remove Picture ${p.slot}`} onClick={() => removePicture(p.slot)}><Icon name="close" size={11}/></button><button className="ref-label mono nc" onClick={() => insertTag(`@Picture${p.slot}`)}>@Picture{p.slot}</button></div>)}{pictures.length < MAX_PICTURES && <button className="add-reference" onClick={() => imageInput.current?.click()}><Icon name="plus" size={18}/><span>{t.add}</span></button>}</div>
            <p className="micro-copy">{draggingPictures ? tr('Drop to add references', 'Solte para adicionar referências', 'Suelta para añadir referencias') : tr('JPG, PNG, WebP · 25 MB each. Slots keep their numbers.', 'JPG, PNG, WebP · 25 MB cada. Os slots mantêm seus números.', 'JPG, PNG, WebP · 25 MB cada. Los slots conservan sus números.')}</p>
          </section>
          <section className="input-card surface output-settings"><div className="label-row"><h2><span className="step-number">03</span>{t.output}</h2></div><div className="setting-row"><span>{t.quality}</span><div className="quality-options">{['480p', '720p', '1080p'].map(q => <button key={q} className={'mono nc ' + (quality === q ? 'chosen' : '')} aria-pressed={quality === q} onClick={() => setQuality(q)}>{q}</button>)}</div></div>
            <div className="setting-row"><label htmlFor="keep-audio">{t.audio}</label><button id="keep-audio" className="toggle" role="switch" aria-label={t.audio} aria-checked={keepAudio} onClick={() => setKeepAudio(v => !v)}><span/></button></div>
            <div className="setting-row"><label htmlFor="audio-conditioning">{tr('Audio conditioning', 'Condicionamento de áudio', 'Condicionamiento de audio')}</label><button id="audio-conditioning" className="toggle" role="switch" aria-label={tr('Audio conditioning', 'Condicionamento de áudio', 'Condicionamiento de audio')} aria-checked={audioConditioning} onClick={() => setAudioConditioning(v => !v)}><span/></button></div>
            <div className="model-badge"><span className="model-symbol"><Icon name="spark" size={19}/></span><div><strong>MiniMax H3</strong><small>{t.model}</small></div><span className="mono nc muted">{quality}</span></div>
          </section>
        </aside>

        <section className="canvas-column">
          <div className="canvas-toolbar"><span><i className="status-dot"/>{t.workspace}<small className="mono muted">/ {modeName(mode)}</small></span><span className="mono muted">{working ? tr('Building prompt', 'Criando prompt', 'Creando prompt') : video ? tr('Source preview', 'Prévia do guia', 'Vista previa de la guía') : t.stIdle}</span></div>
          <div className={'stage ' + (video ? 'has-video' : '')}>
            <div className="blob blob-a"/><div className="blob blob-b"/>
            {!video ? <div className="empty-stage"><div className="ring ring-one"/><div className="ring ring-two"/><div className="orbit-dot"/><div className="stage-message"><span className="eyebrow accent">{t.idleKicker}</span><h2>{t.idleTitle1}<br/><span>{t.idleTitle2}</span></h2><p>{t.idleSub}</p><button className="quiet-button" onClick={() => videoInput.current?.click()}><Icon name="plus" size={17}/>{t.addVideo}</button></div></div> : <div className="preview-panes"><div className="source-pane"><span className="badge mono">{t.source}</span><SubjectVideo url={video.url} range={video.range} subjects={subjects} pickingId={pickingId} onAnchor={(id, anchor) => {setSubjects(current => current.map(s => s.id === id ? {...s, anchors: [...s.anchors.filter(a => Math.abs(a.time_seconds - anchor.time_seconds) > .05), anchor]} : s)); setPickingId(null);}} onDuration={duration => setVideo(v => v?.url === video.url ? {...v, duration} : v)}/>{video.range && <span className="badge range-label mono nc">{formatTime(video.range.start)} / {formatTime(video.range.end)}</span>}</div><div className="output-pane"><span className="badge mono accent">{t.outputLabel}</span>{generationJob?.result_url ? <video key={generationJob.id} controls playsInline src={generationJob.result_url}/> : <><Icon name="spark" size={42}/><p>{generationJob?.error || generationJob?.message || tr('Upload your media and plan the edit below.', 'Envie suas mídias e planeje a edição abaixo.', 'Sube tus medios y planifica la edición abajo.')}</p><span className="status-pill">{generationJob?.status || tr('Ready to plan', 'Pronto para planejar', 'Listo para planificar')}</span></>}</div></div>}
            {working && <div className="jutsu-loading" role="status"><div className="jutsu-seal"><i/><i/><Icon name="spark" size={42}/></div><strong>{tr('Directing your scene', 'Preparando sua direção', 'Preparando tu dirección')}</strong><small>{tr('Reading references and sampled guide frames', 'Lendo referências e quadros do vídeo guia', 'Leyendo referencias y fotogramas de la guía')}</small></div>}
            <span className="stage-corner mono">Kagemage / {mode === 'swap' ? 'Swap' : 'Motion'}</span>
          </div>
          {video?.range && <SubjectBindings subjects={subjects} onChange={setSubjects} representation={guideRepresentation} onRepresentation={setGuideRepresentation} pictures={pictures} lang={lang} pickingId={pickingId} onPick={setPickingId} onPrompt={() => setNative(true)}/>}
          {subjects.length > 0 && subjectErrors && <p className="validation" role="status">{tr('Mark each subject inside the selected interval and attach its references.', 'Marque cada personagem dentro do intervalo selecionado e vincule suas referências.', 'Marca cada personaje dentro del intervalo seleccionado y vincula sus referencias.')}</p>}
          <section className="prompt-card surface"><div className="prompt-header"><h2><Icon name="spark" size={16}/>{t.direct}</h2><div className="editor-tabs"><button aria-pressed={!auto} className={!auto ? 'active' : ''} onClick={() => setAuto(false)}>{t.write}</button><button aria-pressed={auto} className={auto ? 'active' : ''} onClick={() => setAuto(true)}>{t.auto}</button></div></div>
            {auto && <div className="auto-brief"><label htmlFor="brief">{tr('Describe your edit', 'Descreva sua edição', 'Describe tu edición')}</label><textarea id="brief" value={intent} onChange={e => setIntent(e.target.value)} placeholder={mode === 'swap' ? tr('Replace the dancer with Picture 1. Keep the room and lighting.', 'Substitua a dançarina pela Imagem 1. Mantenha a sala e a luz.', 'Reemplaza a la bailarina por la Imagen 1. Conserva la sala y la luz.') : tr('Use the guide motion for Picture 1, on a rooftop at night.', 'Use o movimento do guia para a Imagem 1, em um telhado à noite.', 'Usa el movimiento de la guía para la Imagen 1, en una azotea de noche.')}/><div><small>{tr('The VLM reads the references and 6 guide frames; planning enters the backend queue.', 'O VLM lê referências e 6 quadros do guia; o planejamento entra na fila do backend.', 'El VLM lee referencias y 6 fotogramas; la planificación entra en la cola.')}</small><button className="quiet-button" disabled={busy || !video?.range || !pictures.length || !intent.trim()} onClick={autoPrompt}><Icon name="spark" size={14}/>{working ? tr('Building…', 'Criando…', 'Creando…') : tr('Build prompt', 'Criar prompt', 'Crear prompt')}</button></div></div>}
            <div className="prompt-editor"><textarea ref={textarea} aria-label="Execution prompt" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={mode === 'swap' ? t.phSwap : t.phMotion}/>{query && suggestions.length > 0 && <div className="mention-menu">{suggestions.map(tag => <button key={tag} onClick={() => insertTag(tag)}>{tag}</button>)}</div>}</div>
            {invalid.length > 0 && <p className="validation" role="alert">{tr('Attach or update:', 'Anexe ou atualize:', 'Adjunta o actualiza:')} {invalid.join(', ')}</p>}
            {native && <pre className="native-preview">{nativePrompt(executionPrompt) || tr('Your H3 prompt will appear here.', 'Seu prompt H3 aparecerá aqui.', 'Tu prompt H3 aparecerá aquí.')}</pre>}
            <div className="prompt-footer"><span className="eyebrow muted">{t.insert}</span><div className="mention-chips">{mentions.map(tag => <button key={tag} className="chip mono nc" onClick={() => insertTag(tag)}>{tag}</button>)}{!mentions.length && <span className="muted">—</span>}</div><button className="native-toggle" onClick={() => setNative(v => !v)} aria-expanded={native}><Icon name="code" size={13}/>H3</button><button className="primary export-button" disabled={!canExport} onClick={exportRequest}><Icon name="download" size={16}/>{exporting ? tr('Saving…', 'Salvando…', 'Guardando…') : exportLabel}</button></div>
          </section>
          <GenerationPanel mode={mode} request={makeRequest()} video={video?.file || null} pictures={pictures} canSubmit={canExport} lang={lang} requestedJobId={pendingAutoPromptJob} onResult={job => {setGenerationJob(job); if (job.id === pendingAutoPromptJob && job.plan && job.status === 'awaiting_approval') {setPrompt(job.plan.prompt); setPendingAutoPromptJob(null);}}}/>
          <p className="execution-note">{tr('Direction export stays available separately. Generation jobs and results are stored on the server.', 'A exportação da direção continua disponível separadamente. Pedidos de geração e resultados são salvos no servidor.', 'La exportación sigue disponible por separado. Los pedidos y resultados se guardan en el servidor.')}</p>
        </section>

        <aside className="direction-panel"><section className="surface pipeline-card"><span className="eyebrow muted">{t.pipeline}</span><div className="pipeline-list">{[[!!video?.range, t.p1, t.p1s], [!!pictures.length, t.p2, `${pictures.length} ${t.p2s}`], [!!prompt.trim() && !invalid.length, t.p3, t.p3s], [canExport, tr('Export direction', 'Exportar direção', 'Exportar dirección'), tr('JSON request', 'Solicitação JSON', 'Solicitud JSON')]].map(([ok, title, sub], i) => <div className={'pipeline-item ' + (ok ? 'complete' : '')} key={String(title)}><span className="pipeline-circle">{ok && <Icon name="check" size={11}/>}</span><div><strong>{title}</strong><small>{sub}</small></div>{i === 3 && <span className="mono step-end">04</span>}</div>)}</div></section>
          <section className="surface recent-card"><div className="label-row"><span className="eyebrow muted">{t.recent}</span><button className="text-link" onClick={() => setView('history')}>{t.viewAll} →</button></div>{history.length ? history.slice(0, 3).map(h => <button className="recent-item" key={h.id} onClick={() => {setSelectedId(h.id); setView('history');}}><span className={'recent-thumb ' + (h.request.mode === 'swap' ? 'th-b' : 'th-a')}>{h.thumbnail ? <img src={h.thumbnail} alt=""/> : <Icon name="film" size={16}/>}</span><span><strong>{h.request.project}</strong><small><i style={{background: h.request.mode === 'swap' ? '#D6FF4B' : '#AA8BFF'}}/>{modeName(h.request.mode)} · {h.request.video.duration.toFixed(1)}s</small></span></button>) : <div className="recent-empty"><Icon name="clock" size={22}/><p>{tr('Your exported directions will appear here.', 'Suas direções exportadas aparecerão aqui.', 'Tus direcciones exportadas aparecerán aquí.')}</p></div>}</section>
          <p className="direction-tip"><span className="eyebrow accent">Tip</span> — {mode === 'swap' ? t.tipSwap : t.tipMotion}</p>
        </aside>
      </main>

      <section className="templates-section"><div className="section-top"><div><span className="eyebrow accent">{t.tplKicker} · {TEMPLATES.length}</span><h2>{tr('Start with a direction.', 'Comece com uma direção.', 'Empieza con una dirección.')}</h2><p>{tr('Prompt presets for your own guide video and reference pictures.', 'Prompts prontos para seu vídeo guia e suas imagens de referência.', 'Prompts para tu propio vídeo guía e imágenes de referencia.')}</p></div><div className="filter-chips">{[['all', t.catAll], ['dance', t.catDance], ['action', t.catAction], ['product', t.catProduct], ['fun', t.catFun]].map(([key, label]) => <button className={templateFilter === key ? 'active' : ''} aria-pressed={templateFilter === key} onClick={() => setTemplateFilter(key)} key={key}>{label}</button>)}</div></div>
        <div className="template-grid">{filteredTemplates.map(template => <button key={template.id} className="template-card" onClick={() => useTemplate(template)}><div className={'template-art ' + template.th}>{template.img ? <img src={template.img} alt="" loading="lazy"/> : <div className="template-placeholder"><Icon name={template.mode === 'motion' ? 'motion' : 'film'} size={30}/><span className="eyebrow">{tr('Prompt preset', 'Template de prompt', 'Plantilla de prompt')}</span></div>}<span className={'badge mono mode-badge ' + template.mode}>{modeName(template.mode)}</span><span className="template-cta"><Icon name="plus" size={15}/>{t.useTpl}</span><div className="template-slots">{template.slots[lang].map(slot => <span key={slot}><Icon name="swap" size={10}/>{slot}</span>)}</div></div><div className="template-caption"><h3>{template.title[lang]}</h3><p>{template.prompt[lang]}</p></div></button>)}</div>
      </section>
    </>}

    {view === 'history' && <main className="history-page"><div className="section-top"><div><span className="eyebrow accent">{t.history} · {history.length}</span><h1>{historyTitle}</h1><p>{tr('Your exported prompts and settings, saved on this device.', 'Seus prompts e ajustes exportados, salvos neste dispositivo.', 'Tus prompts y ajustes exportados, guardados en este dispositivo.')}</p></div><div className="history-tools"><div className="filter-chips">{(['all', 'swap', 'motion'] as const).map(key => <button key={key} className={historyFilter === key ? 'active' : ''} aria-pressed={historyFilter === key} onClick={() => setHistoryFilter(key)}>{key === 'all' ? t.all : modeName(key)}</button>)}</div><button className="quiet-button" disabled={!history.some(h => h.rating)} onClick={exportFeedback}><Icon name="download" size={15}/>{tr('Export feedback', 'Exportar avaliações', 'Exportar valoraciones')}<span className="mono muted">{history.filter(h => h.rating).length}</span></button><button className="quiet-button" onClick={() => setView('studio')}><Icon name="plus" size={15}/>{tr('New direction', 'Nova direção', 'Nueva dirección')}</button></div></div>
      <div className="history-layout"><div className="history-grid">{filteredHistory.map(h => <button key={h.id} className={'history-card surface ' + (selected?.id === h.id ? 'selected' : '')} style={{'--item-accent': h.request.mode === 'swap' ? '#D6FF4B' : '#AA8BFF'} as CSSProperties} onClick={() => setSelectedId(h.id)}><div className={'history-art ' + (h.request.mode === 'swap' ? 'th-b' : 'th-a')}>{h.thumbnail ? <img src={h.thumbnail} alt={h.request.video.name}/> : <Icon name="film" size={30}/>}<span className={'badge mono mode-badge ' + h.request.mode}>{modeName(h.request.mode)}</span><span className="badge duration-badge mono nc">{h.request.video.duration.toFixed(1)}s</span><span className="badge draft-badge mono">{tr('Direction', 'Direção', 'Dirección')}</span></div><div className="history-caption"><strong>{h.request.project}</strong><span className="mono nc muted">{dateLabel(h.created)} · {h.request.quality}</span><span className="stars" aria-label={`${h.rating}/5`}>{'★'.repeat(h.rating)}<span>{'☆'.repeat(5 - h.rating)}</span></span></div></button>)}{!filteredHistory.length && <div className="history-empty"><span className="empty-emblem"><Icon name="clock" size={30}/></span><h2>{history.length ? tr('No directions in this mode.', 'Nenhuma direção neste modo.', 'No hay direcciones en este modo.') : tr('Your next idea starts here.', 'Sua próxima ideia começa aqui.', 'Tu próxima idea empieza aquí.')}</h2><p>{tr('Export a direction from the Studio to save its prompt, settings and source preview.', 'Exporte uma direção no Estúdio para guardar o prompt, os ajustes e a prévia do guia.', 'Exporta una dirección del Estudio para guardar el prompt, los ajustes y la vista previa de la guía.')}</p><button className="primary" onClick={() => setView('studio')}><Icon name="plus" size={16}/>{tr('Open studio', 'Abrir estúdio', 'Abrir estudio')}</button></div>}</div>
        {selected && <aside className="history-detail surface"><div className={'detail-art ' + (selected.request.mode === 'swap' ? 'th-b' : 'th-a')}>{selected.thumbnail ? <img src={selected.thumbnail} alt={selected.request.video.name}/> : <Icon name="film" size={40}/>}<span className="badge mono">{tr('Source preview', 'Prévia do guia', 'Vista previa de la guía')}</span></div><div className="detail-body"><h2>{selected.request.project}</h2><p className="detail-prompt">{selected.request.editor_prompt}</p><div className="detail-facts">{[[t.mode, modeName(selected.request.mode)], [t.duration, `${selected.request.video.duration.toFixed(1)}s`], [t.quality, selected.request.quality], [t.created, dateLabel(selected.created)]].map(([label, value]) => <div key={label}><span className="eyebrow muted">{label}</span><strong>{value}</strong></div>)}</div><div className="feedback-panel"><div className="label-row"><strong>{tr('Rate this direction', 'Avalie esta direção', 'Valora esta dirección')}</strong><small className="muted">{selected.rating ? t.rl[selected.rating - 1] : t.noRating}</small></div><div className="rating-buttons" role="group" aria-label={tr('Direction rating', 'Avaliação da direção', 'Valoración de la dirección')}>{[1, 2, 3, 4, 5].map(n => <button key={n} aria-label={`${n} / 5`} aria-pressed={selected.rating === n} className={selected.rating >= n ? 'filled' : ''} onClick={() => patchHistory(selected.id, {rating: selected.rating === n ? 0 : n})}>{selected.rating >= n ? '★' : '☆'}</button>)}</div><div className="feedback-tags">{FEEDBACK.map((tag, i) => <button key={tag} aria-pressed={selected.tags.includes(tag)} className={selected.tags.includes(tag) ? 'chosen' : ''} onClick={() => patchHistory(selected.id, {tags: selected.tags.includes(tag) ? selected.tags.filter(x => x !== tag) : [...selected.tags, tag]})}>{feedbackLabels[i]}</button>)}</div></div><div className="detail-actions"><button className="primary" onClick={() => downloadJSON(selected.request, 'kagemage-request.json')}><Icon name="download" size={15}/>{t.export}</button><button className="quiet-button" onClick={() => setModal('share')}><Icon name="share" size={15}/>{tr('Share preset', 'Compartilhar template', 'Compartir plantilla')}</button><button className="quiet-button reuse-button" onClick={() => reuse(selected)}>{t.reuse}</button><button className="icon-btn delete-button" aria-label={t.del} onClick={() => setModal('delete')}><Icon name="trash" size={17}/></button></div></div></aside>}
      </div>
    </main>}

    {view === 'community' && <main className="community-page"><span className="eyebrow accent">{t.community}</span><h1>{t.commTitle}</h1><p className="community-intro">{tr('A place for shared scenes, reusable directions and new possibilities.', 'Um espaço para compartilhar cenas, reutilizar direções e criar novas possibilidades.', 'Un lugar para compartir escenas, reutilizar direcciones y crear nuevas posibilidades.')}</p><div className="community-empty surface"><div className="community-orbits"><Icon name="share" size={36}/></div><span className="eyebrow accent">{tr('Coming next', 'Próximo capítulo', 'Próximo capítulo')}</span><h2>{tr('Good ideas are better together.', 'Boas ideias ficam melhores juntas.', 'Las buenas ideas mejoran juntas.')}</h2><p>{tr('Public publishing is not connected yet. You can already save directions, export presets and send the JSON file to another creator.', 'A publicação pública ainda não está conectada. Você já pode salvar direções, exportar templates e enviar o JSON para outro criador.', 'La publicación pública aún no está conectada. Ya puedes guardar direcciones, exportar plantillas y enviar el JSON a otro creador.')}</p><button className="primary" onClick={() => {setView('studio'); requestAnimationFrame(() => document.querySelector('.templates-section')?.scrollIntoView({behavior: 'smooth'}));}}>{tr('Explore templates', 'Explorar templates', 'Explorar plantillas')}<Icon name="arrow" size={16}/></button></div></main>}

    <footer className="app-footer"><span className="mono">Kagemage <Icon name="spark" size={12}/> {tr('An open canvas for moving ideas.', 'Uma tela aberta para ideias em movimento.', 'Un lienzo abierto para ideas en movimiento.')}</span><span>{tr('Made for creators. Built on Comfy.', 'Feito para criadores. Construído com Comfy.', 'Hecho para creadores. Construido con Comfy.')}</span></footer>
    {notice && <div className="notification" role="status" aria-live="polite"><span>{notice}</span><button className="icon-btn" aria-label={tr('Dismiss notification', 'Fechar notificação', 'Cerrar notificación')} onClick={() => setNotice('')}><Icon name="close" size={16}/></button></div>}
    <dialog className="action-modal" ref={dialog} onCancel={e => {e.preventDefault(); setModal(null);}} aria-labelledby="action-title"><button className="modal-close icon-btn" aria-label={t.cancel} onClick={() => setModal(null)}><Icon name="close" size={18}/></button><span className="modal-emblem"><Icon name={modal === 'delete' ? 'trash' : 'share'} size={26}/></span><h2 id="action-title">{modal === 'delete' ? tr('Delete this direction?', 'Excluir esta direção?', '¿Eliminar esta dirección?') : tr('Share a direction', 'Compartilhe uma direção', 'Comparte una dirección')}</h2><p>{modal === 'delete' ? tr('This removes its local history entry. Your original media files are unchanged.', 'Isso remove a entrada do histórico local. Seus arquivos originais permanecem intactos.', 'Esto elimina la entrada del historial local. Tus archivos originales no cambian.') : tr('Export the prompt and settings as a JSON preset. Media, ratings and local file names are not included.', 'Exporte o prompt e os ajustes como um template JSON. Mídia, avaliações e nomes de arquivos locais não são incluídos.', 'Exporta el prompt y los ajustes como plantilla JSON. No incluye archivos, valoraciones ni nombres de archivos locales.')}</p><div className="modal-actions"><button className="quiet-button" onClick={() => setModal(null)}>{t.cancel}</button><button className="primary" onClick={() => {if (!selected) return; if (modal === 'delete') {setHistory(h => h.filter(x => x.id !== selected.id)); setSelectedId(null);} else {const r = selected.request; downloadJSON({schema_version: 1, kind: 'kagemage_prompt_preset', title: r.project, mode: r.mode, quality: r.quality, prompt: r.editor_prompt, processing: r.processing, audio_conditioning: r.audio_conditioning, output_audio: r.output_audio, reference_slots: r.pictures.map(p => p.slot)}, 'kagemage-preset.json');} setModal(null);}}>{modal === 'delete' ? t.del : tr('Download preset', 'Baixar template', 'Descargar plantilla')}</button></div></dialog>
  </div>;
}
