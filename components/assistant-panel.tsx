'use client';
import {useEffect, useRef, useState} from 'react';
import Markdown from '../lib/markdown';
import type {Language} from '../lib/design-copy';
import Select from './select';

/** One studio action the assistant asked for, run here so the user sees the screen change. */
export type StudioCall = {id: string; name: string; input: Record<string, unknown>};
export type StudioResult = {text: string; images?: string[]; is_error?: boolean};
export type StudioController = {state: () => Record<string, unknown>; run: (call: StudioCall) => Promise<StudioResult>; ingest: (files: File[]) => Promise<StudioResult>; remember?: (files: File[]) => void};

type Result = {id: string; name: string; text: string; images?: string[]; is_error?: boolean};
type Message =
  | {role: 'user'; text: string; images?: string[]}
  | {role: 'assistant'; text: string; tool_calls?: StudioCall[]; native?: unknown; native_provider?: string}
  | {role: 'tool'; results: Result[]};
type Config = {provider: 'anthropic' | 'openai' | 'local'; model: string; base_url: string; effort: string; has_key: boolean; key_hint: string; marking?: 'sam' | 'vision'; planner?: 'local' | 'assistant'};
type JobMention = {id: string; project?: string; mode?: string; status: string; created: number};
// An image is a generation reference (loaded as a Picture) or only explains something to the assistant (a marked
// screenshot, a sketch): those stay in the chat and never reach the studio.
type PendingAttachment = {id: string; name: string; kind: 'image' | 'video'; images: string[]; detail: string; file: File; role: 'reference' | 'explain'};
type PendingApproval = {question: string; approve: string; decline: string; resolve: (approved: boolean) => void};

const PRESETS: Record<string, {provider: Config['provider']; model: string; base_url: string}> = {
  local: {provider: 'local', model: 'henge-vlm', base_url: ''},
  claude: {provider: 'anthropic', model: 'claude-opus-5-5', base_url: ''},
  openai: {provider: 'openai', model: 'gpt-5.1', base_url: 'https://api.openai.com/v1'},
  lmstudio: {provider: 'openai', model: 'qwen3-vl-8b-instruct', base_url: 'http://127.0.0.1:1234/v1'},
  ollama: {provider: 'openai', model: 'qwen2.5vl', base_url: 'http://127.0.0.1:11434/v1'},
};

const label = (name: string, input: Record<string, unknown>) => {
  const v = (k: string) => input[k] as string | number | undefined;
  switch (name) {
    case 'point_video': return `point_video · ${v('start')}–${v('end')}s · ${v('query')}`;
    case 'suggest_cuts': return `suggest_cuts · max ${v('max_seconds') ?? '?'}s`;
    case 'ask_video': return `ask_video · ${String(v('question') ?? '').slice(0, 60)}`;
    case 'match_people': return `match_people · ${Array.isArray(input.people) ? input.people.length : 0} people`;
    case 'find_people': return `find_people · ${v('time')}s`;
    case 'view_frame': return `view_frame · ${v('time')}s`;
    case 'mark_subject': {const slots = input.picture_slots; const list = Array.isArray(slots) ? slots.join(', ') : slots ?? (input.subject ? `subject ${input.subject}` : ''); return `mark_subject · ${input.person !== undefined ? '#' + v('person') : `(${v('x')}, ${v('y')})`} @ ${v('time')}s → ${Array.isArray(slots) || slots != null ? 'Picture ' : ''}${list}`;}
    case 'set_mode': return `set_mode · ${v('mode')}`;
    case 'set_guide': return `set_guide · ${v('representation')}${input.mark_opacity !== undefined ? ` ${v('mark_opacity')}` : ''}`;
    case 'set_quality': return `set_quality · ${v('quality')}`;
    case 'wait_for_job': return `wait_for_job · ${v('until')}`;
    case 'view_job_video': return `view_job_video · ${v('which')}`;
    default: return name;
  }
};

/** Chat with an LLM that operates the studio. The conversation lives here; each step goes to the bridge, which calls
 * the model and runs job tools, and returns the studio actions to run on this screen. */
export default function AssistantPanel({controller, lang, jobId}: {controller: StudioController; lang: Language; jobId?: string | null}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {try {setExpanded(localStorage.getItem('henge-assistant-expanded') === '1');} catch {/* private mode */}}, []);
  const toggleExpanded = () => setExpanded(v => {try {localStorage.setItem('henge-assistant-expanded', v ? '0' : '1');} catch {/* private mode */} return !v;});
  const [settings, setSettings] = useState(false);
  // The settings center / first-run wizard asks the assistant to show its own settings.
  useEffect(() => {const show = () => {setOpen(true); setSettings(true);}; addEventListener('henge:assistant-settings', show); return () => removeEventListener('henge:assistant-settings', show);}, []);
  const [config, setConfig] = useState<Config | null>(null);
  const [draft, setDraft] = useState<Partial<Config> & {api_key?: string}>({});
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [recentJobs, setRecentJobs] = useState<JobMention[]>([]);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const [approval, setApproval] = useState<PendingApproval | null>(null);
  const attachmentInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const stop = useRef(false);
  // Conversations live on the bridge (a reload or restart keeps them) and follow the jobs they started.
  const newId = () => crypto.randomUUID().replace(/-/g, '');
  const [chatId, setChatId] = useState<string>('');
  const chatJobs = useRef<string[]>([]);
  async function loadChat(id: string) {
    const r = await fetch(`/api/backend/assistant/chats/${id}`); if (!r.ok) return false;
    const chat = await r.json(); setChatId(id); setMessages(chat.messages || []); chatJobs.current = chat.jobs || [];
    try {localStorage.setItem('henge-assistant-chat', id);} catch {/* private mode */}
    return true;
  }
  function persist(history: Message[]) {
    if (!chatId || !history.length) return;
    fetch(`/api/backend/assistant/chats/${chatId}`, {method: 'PUT', headers: {'content-type': 'application/json'}, body: JSON.stringify({messages: history, jobs: chatJobs.current})}).catch(() => {});
  }
  function newChat() {
    const id = newId(); setChatId(id); setMessages([]); chatJobs.current = []; setError('');
    try {localStorage.setItem('henge-assistant-chat', id);} catch {/* private mode */}
  }
  useEffect(() => {
    let stored = ''; try {stored = localStorage.getItem('henge-assistant-chat') || '';} catch {/* private mode */}
    if (stored) loadChat(stored).then(ok => {if (!ok) newChat();}); else newChat();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Opening a job (Recent, History, panel) brings back the conversation that started it.
  useEffect(() => {
    if (!jobId || busy || chatJobs.current.includes(jobId)) return;
    fetch(`/api/backend/assistant/chats?job=${jobId}`).then(r => r.ok ? r.json() : []).then((rows: {id: string}[]) => {if (rows[0] && rows[0].id !== chatId) loadChat(rows[0].id);}).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {if (open && !config) fetch('/api/backend/assistant/config').then(r => r.json()).then((c: Config) => {setConfig(c); setDraft(c); if (!c.has_key && c.provider === 'anthropic') setSettings(true);}).catch(() => setError(tr('The bridge is offline.', 'O bridge está offline.', 'El bridge está desconectado.')));}, [open]);
  useEffect(() => {if (open) fetch('/api/backend/jobs').then(r => r.ok ? r.json() : []).then((rows: JobMention[]) => setRecentJobs(rows.slice(0, 12))).catch(() => {});}, [open]);
  useEffect(() => {list.current?.scrollTo({top: list.current.scrollHeight, behavior: 'smooth'});}, [messages, busy]);

  // The models the chosen provider offers, listed by the bridge with the saved (or just typed) key.
  const [models, setModels] = useState<{id: string; name: string}[] | null>(null);
  const [modelsError, setModelsError] = useState('');
  const [typeModel, setTypeModel] = useState(false);
  async function loadModels() {
    setModels(null); setModelsError('');
    try {
      const r = await fetch('/api/backend/assistant/models', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({provider: draft.provider, base_url: draft.base_url ?? '', api_key: draft.api_key || ''})});
      const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`);
      setModels(reply);
    } catch (e) {setModels([]); setModelsError(e instanceof Error ? e.message : String(e));}
  }
  useEffect(() => {
    if (!settings || !draft.provider) return;
    const t = setTimeout(loadModels, 400); return () => clearTimeout(t);
  }, [settings, draft.provider, draft.base_url]);

  async function saveSettings() {
    setError('');
    try {
      const r = await fetch('/api/backend/assistant/config', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(draft)});
      const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`);
      setConfig(reply); setDraft(reply); setSettings(false);
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
  }

  async function step(history: Message[]): Promise<{messages: Message[]; studio_calls: StudioCall[]; job_results: Result[]; done: boolean}> {
    // A restart of the UI or the bridge drops the request (503/502, or a network error): wait and send it again.
    for (let attempt = 0; ; attempt++) {
      try {
        const r = await fetch('/api/backend/assistant/step', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({messages: history})});
        if ([502, 503, 504].includes(r.status) && attempt < 3) throw Error(`HTTP ${r.status}`);
        const reply = await r.json(); if (!r.ok) throw Object.assign(Error(reply.detail || `HTTP ${r.status}`), {final: true});
        return reply;
      } catch (e) {
        if ((e as {final?: boolean}).final || attempt >= 3 || stop.current) throw e;
        setBusy(tr('Connection dropped, trying again…', 'A conexão caiu, tentando de novo…', 'Se cortó la conexión, reintentando…'));
        await new Promise(resolve => setTimeout(resolve, 4000 * (attempt + 1)));
      }
    }
  }

  const canvasFrame = (source: CanvasImageSource, width: number, height: number) => {
    const scale = Math.min(1, 1280 / Math.max(width, height)), canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width * scale)); canvas.height = Math.max(1, Math.round(height * scale));
    canvas.getContext('2d')!.drawImage(source, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', .82);
  };
  async function prepareAttachment(file: File): Promise<PendingAttachment> {
    const id = crypto.randomUUID();
    if (file.type.startsWith('image/')) {
      const bitmap = await createImageBitmap(file);
      try {return {id, name: file.name, kind: 'image', images: [canvasFrame(bitmap, bitmap.width, bitmap.height)], detail: `${bitmap.width}x${bitmap.height}`, file, role: 'reference'};}
      finally {bitmap.close();}
    }
    if (!file.type.startsWith('video/')) throw Error(tr('Use an image or video file.', 'Use um arquivo de imagem ou vídeo.', 'Usa un archivo de imagen o vídeo.'));
    const url = URL.createObjectURL(file), video = document.createElement('video'); video.preload = 'metadata'; video.muted = true; video.src = url;
    try {
      await new Promise<void>((resolve, reject) => {video.onloadedmetadata = () => resolve(); video.onerror = () => reject(Error(tr('Could not read this video.', 'Não foi possível ler este vídeo.', 'No se pudo leer este vídeo.')));});
      const duration = video.duration, times = [.08, .35, .65, .92].map(f => Math.min(Math.max(0, duration * f), Math.max(0, duration - .05))), images: string[] = [];
      for (const time of times) {video.currentTime = time; await new Promise<void>((resolve, reject) => {video.onseeked = () => resolve(); video.onerror = () => reject(Error('Video seek failed'));}); images.push(canvasFrame(video, video.videoWidth, video.videoHeight));}
      return {id, name: file.name, kind: 'video', images, detail: `${duration.toFixed(1)}s · ${video.videoWidth}x${video.videoHeight} · ${images.length} frames`, file, role: 'reference'};
    } finally {URL.revokeObjectURL(url); video.removeAttribute('src'); video.load();}
  }
  async function addAttachments(files: FileList | File[]) {
    const incoming = Array.from(files).slice(0, Math.max(0, 6 - attachments.length)); if (!incoming.length) return;
    setBusy(tr('Preparing attachments…', 'Preparando anexos…', 'Preparando adjuntos…')); setError('');
    try {const prepared = await Promise.all(incoming.map(prepareAttachment)); setAttachments(current => [...current, ...prepared].slice(0, 6));}
    catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(''); if (attachmentInput.current) attachmentInput.current.value = '';}
  }

  // Messages typed while the assistant works wait here and are added to the conversation before its next step.
  type Pending = {text: string; images: string[]; note: string};
  const pendingRef = useRef<Pending[]>([]);
  const [pending, setPendingState] = useState<Pending[]>([]);
  const setPending = (p: Pending[]) => {pendingRef.current = p; setPendingState(p);};
  const controllerRef = useRef(controller); controllerRef.current = controller;
  const toMessage = (p: Pending, queued = false): Message => ({role: 'user', images: p.images,
    text: `${p.text}${p.note}\n\n[studio state] ${JSON.stringify(controllerRef.current.state())}${queued ? '\n[sent while you were still working on the previous request]' : ''}`});
  const drain = (history: Message[]) => {
    const queued = pendingRef.current; if (!queued.length) return history;
    setPending([]); return [...history, ...queued.map(p => toMessage(p, true))];
  };

  async function send() {
    const text = input.trim(); if (!text && !attachments.length) return;
    const attached = attachments; setInput(''); setAttachments([]); setError('');
    // Only generation references reach the studio, when the message is sent (removing one before that loads nothing).
    const loaded = attached.filter(a => a.role === 'reference'), explain = attached.filter(a => a.role === 'explain');
    if (loaded.length) {try {await controller.ingest(loaded.map(a => a.file));} catch (e) {setError(e instanceof Error ? e.message : String(e));}}
    // Explanation images stay out of the studio, but match_people can use them as photos of the people to find.
    if (explain.length) controller.remember?.(explain.filter(a => a.kind === 'image').map(a => a.file));
    const attachmentNote = (loaded.length ? `\n\n[attachments already loaded into the studio in this order] ${loaded.map((a, i) => `${i + 1}. ${a.kind}: ${a.name} (${a.detail})`).join('; ')}` : '')
      + (explain.length ? `\n\n[explanation images, for you only: NOT loaded into the studio and never a reference Picture; read them as the user's instructions, e.g. people numbered or circled on a frame] ${explain.map(a => `${a.name} (${a.detail})`).join('; ')}` : '');
    const item: Pending = {text: text || tr('Look at these attachments.', 'Veja estes anexos.', 'Mira estos adjuntos.'), images: attached.flatMap(a => a.images), note: attachmentNote};
    if (busy) {setPending([...pendingRef.current, item]); return;}
    stop.current = false;
    let history: Message[] = [...messages, ...pendingRef.current.map(p => toMessage(p)), toMessage(item)]; setPending([]);
    setMessages(history); persist(history);
    try {
      for (let round = 0; round < 40 && !stop.current; round++) {
        setBusy(config?.provider === 'local' || (config && !config.has_key && config.provider !== 'openai')
          ? tr('Thinking (built-in model on your backend; on serverless the first step can take a few minutes)…', 'Pensando (modelo embutido no seu backend; no serverless o 1º passo pode levar alguns minutos)…', 'Pensando (modelo integrado en tu backend; en serverless el primer paso puede tardar unos minutos)…')
          : tr('Thinking…', 'Pensando…', 'Pensando…'));
        const drained = drain(history); if (drained !== history) {history = drained; setMessages(history); persist(history);}
        const reply = await step(history);
        history = reply.messages; setMessages(history); persist(history);
        // A message that arrived during the last step still gets an answer.
        if (reply.done || !reply.studio_calls.length) {if (pendingRef.current.length && !stop.current) continue; break;}
        const results: Result[] = [...reply.job_results];
        for (const call of reply.studio_calls) {
          if (stop.current) {results.push({id: call.id, name: call.name, text: 'Stopped by the user.', is_error: true}); continue;}
          setBusy(call.name === 'ask_video' || call.name === 'suggest_cuts'
            ? tr('Molmo2 is watching the video on this computer…', 'O Molmo2 está assistindo ao vídeo neste computador…', 'Molmo2 está viendo el vídeo en este equipo…')
            : call.name === 'match_people'
            ? tr('Finding the people with Molmo2 on this computer (about a minute per shot)…', 'Procurando as pessoas com o Molmo2 neste computador (cerca de 1 minuto por shot)…', 'Buscando a las personas con Molmo2 en este equipo (cerca de 1 minuto por plano)…')
            : label(call.name, call.input));
          try {
            const result = call.name === 'confirm_cancel_job'
              ? await new Promise<StudioResult>(resolve => setApproval({question: String(call.input.question), approve: String(call.input.approve_label || tr('Yes, cancel', 'Sim, cancelar', 'Sí, cancelar')), decline: String(call.input.decline_label || tr('No, keep running', 'Não, continuar', 'No, continuar')), resolve: approved => resolve({text: JSON.stringify({approved, job_id: String(call.input.job_id)})})}))
              : await controller.run(call); results.push({id: call.id, name: call.name, ...result});
            const started = call.name === 'generate' && result.text.match(/[a-f0-9]{32}/)?.[0];
            if (started && !chatJobs.current.includes(started)) chatJobs.current = [...chatJobs.current, started];
          }
          catch (e) {results.push({id: call.id, name: call.name, text: e instanceof Error ? e.message : String(e), is_error: true});}
        }
        history = [...history, {role: 'tool', results}]; setMessages(history); persist(history);
      }
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy('');}
  }

  const presetOf = (c: Partial<Config>) => Object.entries(PRESETS).find(([, p]) => p.provider === c.provider && (p.provider !== 'openai' || p.base_url === c.base_url))?.[0] || 'custom';
  const mention = input.match(/#([a-f0-9]*)$/i);
  const mentionJobs = mention ? recentJobs.filter(j => !mention[1] || j.id.startsWith(mention[1].toLowerCase())).slice(0, 8) : [];
  const insertJob = (id: string) => setInput(value => value.replace(/#[a-f0-9]*$/i, `#${id.slice(0, 8)} `));
  return <>
    <button type="button" className="assistant-fab" aria-expanded={open} onClick={() => setOpen(o => !o)}>{open ? '×' : '✦'}<span>{tr('Assistant', 'Assistente', 'Asistente')}</span></button>
    {open && <aside className={'assistant-panel surface' + (expanded ? ' expanded' : '') + (dragging ? ' dragging' : '')} aria-label={tr('Studio assistant', 'Assistente do estúdio', 'Asistente del estudio')} onDragEnter={e => {e.preventDefault(); setDragging(true);}} onDragOver={e => e.preventDefault()} onDragLeave={e => {if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);}} onDrop={e => {e.preventDefault(); setDragging(false); void addAttachments(e.dataTransfer.files);}}>
      {dragging && <div className="assistant-drop-overlay">{tr('Drop images or videos here', 'Solte imagens ou vídeos aqui', 'Suelta imágenes o vídeos aquí')}</div>}
      <header><strong>{tr('Studio assistant', 'Assistente do estúdio', 'Asistente del estudio')}</strong>
        <small className="muted mono">{jobId ? `#${jobId.slice(0, 8)}${config ? ` · ${config.model}` : ''}` : config ? `${config.model}` : ''}</small>
        <span><button type="button" className="quiet-button" onClick={newChat} disabled={!!busy}>{tr('New chat', 'Nova conversa', 'Nueva conversación')}</button>
          <button type="button" className="quiet-button" aria-pressed={expanded} title={expanded ? tr('Smaller', 'Diminuir', 'Reducir') : tr('Expand', 'Expandir', 'Ampliar')} aria-label={expanded ? tr('Smaller', 'Diminuir', 'Reducir') : tr('Expand', 'Expandir', 'Ampliar')} onClick={toggleExpanded}>{expanded ? '⤡' : '⤢'}</button>
          <button type="button" className="quiet-button" aria-pressed={settings} onClick={() => setSettings(s => !s)}>⚙</button></span></header>
      {settings && config && <div className="assistant-settings">
        <label>{tr('Model provider', 'Provedor do modelo', 'Proveedor del modelo')}<Select value={presetOf(draft)} onChange={e => {const p = PRESETS[e.target.value]; if (p) setDraft(d => ({...d, ...p}));}}>
          <option value="local">{tr('Henge VLM (built-in, no key)', 'Henge VLM (embutido, sem chave)', 'Henge VLM (integrado, sin clave)')}</option><option value="claude">Claude (Anthropic API)</option><option value="openai">OpenAI (GPT)</option><option value="lmstudio">LM Studio ({tr('local', 'local', 'local')})</option><option value="ollama">Ollama ({tr('local', 'local', 'local')})</option><option value="custom">{tr('Other OpenAI-compatible API', 'Outra API compatível com OpenAI', 'Otra API compatible con OpenAI')}</option></Select></label>
        {presetOf(draft) === 'custom' && <label>{tr('Type', 'Tipo', 'Tipo')}<Select value={draft.provider} onChange={e => setDraft(d => ({...d, provider: e.target.value as Config['provider']}))}><option value="openai">OpenAI-compatible</option><option value="anthropic">Anthropic</option></Select></label>}
        <label>{tr('Model', 'Modelo', 'Modelo')}
          {models?.length && !typeModel
            ? <Select value={draft.model || ''} onChange={e => e.target.value === '__type' ? setTypeModel(true) : setDraft(d => ({...d, model: e.target.value}))}>
                {draft.model && !models.some(m => m.id === draft.model) && <option value={draft.model}>{draft.model} ({tr('not listed', 'não listado', 'no listado')})</option>}
                {models.map(m => <option key={m.id} value={m.id}>{m.name !== m.id ? `${m.name} · ${m.id}` : m.id}</option>)}
                <option value="__type">{tr('Other… (type the id)', 'Outro… (digitar o id)', 'Otro… (escribir el id)')}</option></Select>
            : <input value={draft.model || ''} onChange={e => setDraft(d => ({...d, model: e.target.value}))}/>}
          {models === null && <small className="muted">{tr('Loading models…', 'Carregando modelos…', 'Cargando modelos…')}</small>}
          {modelsError && <small className="muted">{tr('Could not list the models', 'Não deu para listar os modelos', 'No se pudieron listar los modelos')}: {modelsError} <button type="button" className="quiet-button" onClick={loadModels}>↻</button></small>}
          {typeModel && !!models?.length && <button type="button" className="quiet-button" onClick={() => setTypeModel(false)}>{tr('Pick from the list', 'Escolher da lista', 'Elegir de la lista')}</button>}
        </label>
        {draft.provider === 'openai' && <label>Base URL<input value={draft.base_url || ''} placeholder="https://api.openai.com/v1" onChange={e => setDraft(d => ({...d, base_url: e.target.value}))}/></label>}
        {draft.provider === 'local' ? <small className="muted">{tr('Runs the same Qwen 3.5 9B the planner uses, on your ComfyUI or serverless backend: no key, no account. Slower and simpler than Claude or GPT; good for routine marking and generating.', 'Roda o mesmo Qwen 3.5 9B do planner, no seu ComfyUI ou no serverless: sem chave e sem conta. Mais lento e mais simples que Claude ou GPT; serve para marcar e gerar no dia a dia.', 'Usa el mismo Qwen 3.5 9B del planner, en tu ComfyUI o en el serverless: sin clave ni cuenta. Más lento y simple que Claude o GPT; sirve para marcar y generar.')}</small> : <label>{tr('API key', 'Chave da API', 'Clave de la API')}<input type="password" autoComplete="off" value={draft.api_key || ''} placeholder={config.has_key ? `${tr('saved', 'salva', 'guardada')} ${config.key_hint}` : draft.provider === 'openai' ? tr('not needed for local servers', 'não precisa para servidores locais', 'no hace falta en servidores locales') : 'sk-ant-…'} onChange={e => setDraft(d => ({...d, api_key: e.target.value}))} onBlur={() => {if (draft.api_key) void loadModels();}}/></label>}
        {draft.provider === 'anthropic' && <label>{tr('Effort', 'Esforço', 'Esfuerzo')}<Select value={draft.effort ?? 'medium'} onChange={e => setDraft(d => ({...d, effort: e.target.value}))}>{['low', 'medium', 'high'].map(v => <option key={v} value={v}>{v}</option>)}<option value="">{tr('model default', 'padrão do modelo', 'predeterminado')}</option></Select></label>}
        <label>{tr('Who writes the automatic prompts and analyses', 'Quem escreve os prompts automáticos e as análises', 'Quién escribe los prompts automáticos y los análisis')}<Select value={draft.planner ?? 'local'} onChange={e => setDraft(d => ({...d, planner: e.target.value as 'local' | 'assistant'}))}><option value="local">{tr('The local planner (Qwen in ComfyUI, free)', 'O planner local (Qwen no ComfyUI, grátis)', 'El planificador local (Qwen en ComfyUI, gratis)')}</option><option value="assistant">{tr('This assistant model', 'Este modelo do assistente', 'Este modelo del asistente')}</option></Select><small className="muted">{tr('Picture descriptions, the guide analysis, the plan and the final H3 prompt. With the assistant model they are usually better and free the GPU, but each generation spends a few API requests.', 'Descrição das Pictures, análise do guia, o plano e o prompt final do H3. Com o modelo do assistente costumam sair melhores e liberam a GPU, mas cada geração gasta algumas chamadas da API.', 'Descripción de las Pictures, análisis de la guía, el plan y el prompt final de H3. Con el modelo del asistente suelen salir mejor y liberan la GPU, pero cada generación gasta algunas llamadas a la API.')}</small></label>
        <label>{tr('Who marks the people', 'Quem marca as pessoas', 'Quién marca a las personas')}<Select value={draft.marking ?? 'sam'} onChange={e => setDraft(d => ({...d, marking: e.target.value as 'sam' | 'vision'}))}><option value="sam">{tr('SAM 3.1 detects and numbers them', 'O SAM 3.1 detecta e numera', 'SAM 3.1 las detecta y numera')}</option><option value="vision">{tr('The assistant, with its own vision', 'O assistente, com a própria visão', 'El asistente, con su propia visión')}</option></Select><small className="muted">{tr('With the assistant, it points at each person (checking the dot on the frame); SAM 3.1 still cuts out and tracks them in every frame when generating.', 'Com o assistente, ele aponta cada pessoa (conferindo o ponto no quadro); o SAM 3.1 continua recortando e seguindo cada uma em todos os quadros na geração.', 'Con el asistente, señala a cada persona (comprobando el punto en el fotograma); SAM 3.1 sigue recortándolas y siguiéndolas en todos los fotogramas al generar.')}</small></label>
        <small className="muted">{tr('The key stays on the bridge (assistant.json in its data folder); the browser never receives it. The model needs vision and tool calling.', 'A chave fica no bridge (assistant.json na pasta de dados); o navegador nunca a recebe. O modelo precisa de visão e de chamada de ferramentas.', 'La clave queda en el bridge (assistant.json en su carpeta de datos); el navegador nunca la recibe. El modelo necesita visión y llamadas a herramientas.')}</small>
        <div className="plan-actions"><button type="button" className="primary" onClick={saveSettings}>{tr('Save', 'Salvar', 'Guardar')}</button></div>
      </div>}
      <div className="assistant-messages" ref={list}>
        {!messages.length && <p className="muted">{tr('Attach the video and the pictures, then say what you want, e.g. "the fighter on the left becomes Picture 1 and the other one Picture 2". The assistant marks the people, picks the options, shows you the plan and generates.', 'Anexe o vídeo e as imagens e diga o que quer, por exemplo "o lutador da esquerda vira a Picture 1 e o outro a Picture 2". O assistente marca as pessoas, escolhe as opções, mostra o plano e gera.', 'Adjunta el vídeo y las imágenes y di lo que quieres, por ejemplo "el luchador de la izquierda será la Picture 1 y el otro la Picture 2". El asistente marca a las personas, elige las opciones, te muestra el plan y genera.')}</p>}
        {messages.map((m, i) => m.role === 'user' ? <div key={i} className="assistant-msg user">{m.text.split('\n\n[studio state]')[0]}</div>
          : m.role === 'assistant' ? <div key={i} className="assistant-msg">{m.text && <Markdown text={m.text}/>}{m.tool_calls?.map(c => <small key={c.id} className="assistant-tool mono">⚙ {label(c.name, c.input)}</small>)}</div>
          : <div key={i} className="assistant-results">{m.results.map(r => <div key={r.id}>{r.is_error && <small className="validation">{r.text}</small>}{r.images?.map((src, j) => <img key={j} src={src} alt={r.name}/>)}</div>)}</div>)}
        {pending.map((p, i) => <div key={'queued' + i} className="assistant-msg user queued">{p.text}<small className="muted">{tr('waiting · read at the next step', 'na fila · lida no próximo passo', 'en cola · se lee en el siguiente paso')}</small></div>)}
        {approval && <div className="assistant-approval"><p>{approval.question}</p><div><button type="button" className="quiet-button" onClick={() => {approval.resolve(false); setApproval(null);}}>{approval.decline}</button><button type="button" className="primary" onClick={() => {approval.resolve(true); setApproval(null);}}>{approval.approve}</button></div></div>}
        {busy && <small className="assistant-busy mono"><span className="spinner" aria-hidden="true"/>{busy}</small>}
        {error && <p className="validation" role="alert">{error}</p>}
      </div>
      <form className="assistant-input" onSubmit={e => {e.preventDefault(); if (mentionJobs[0]) insertJob(mentionJobs[0].id); else void send();}}>
        {mentionJobs.length > 0 && <div className="assistant-job-mentions" role="listbox" aria-label={tr('Recent generations', 'Gerações recentes', 'Generaciones recientes')}>{mentionJobs.map(j => <button key={j.id} type="button" role="option" onClick={() => insertJob(j.id)}><span className="mono">#{j.id.slice(0, 8)}</span><strong>{j.project || 'Henge'}</strong><small>{j.mode || ''} · {j.status}</small></button>)}</div>}
        {attachments.length > 0 && <div className="assistant-attachments">{attachments.map(a => <div key={a.id}>{a.images[0] && <img src={a.images[0]} alt=""/>}<span><strong>{a.name}</strong><small>{a.detail}</small>{a.kind === 'image' && <button type="button" className={'attachment-role' + (a.role === 'explain' ? ' explain' : '')} aria-pressed={a.role === 'explain'} title={tr('Generation references become Pictures; explanation images (marked screenshots, sketches) only go to the assistant.', 'Referências da geração viram Pictures; imagens de explicação (prints marcados, esboços) vão só para o assistente.', 'Las referencias de la generación se vuelven Pictures; las imágenes de explicación (capturas marcadas, bocetos) solo van al asistente.')} onClick={() => setAttachments(current => current.map(x => x.id === a.id ? {...x, role: x.role === 'explain' ? 'reference' : 'explain'} : x))}>{a.role === 'explain' ? tr('Only to explain', 'Só para explicar', 'Solo para explicar') : tr('Generation reference', 'Referência da geração', 'Referencia de la generación')}</button>}</span><button type="button" aria-label={tr('Remove attachment', 'Remover anexo', 'Quitar adjunto')} onClick={() => setAttachments(current => current.filter(x => x.id !== a.id))}>×</button></div>)}</div>}
        <input ref={attachmentInput} type="file" hidden multiple accept="image/*,video/*" onChange={e => {if (e.target.files) void addAttachments(e.target.files);}}/>
        <button type="button" className="assistant-attach quiet-button" aria-label={tr('Attach images or videos', 'Anexar imagens ou vídeos', 'Adjuntar imágenes o vídeos')} title={tr('Attach images or videos', 'Anexar imagens ou vídeos', 'Adjuntar imágenes o vídeos')} disabled={!!busy || attachments.length >= 6} onClick={() => attachmentInput.current?.click()}>＋</button>
        <textarea value={input} rows={2} placeholder={tr('What do you want to make?', 'O que você quer fazer?', '¿Qué quieres hacer?')} onChange={e => setInput(e.target.value)} onKeyDown={e => {if (e.key === 'Escape' && mention) {e.preventDefault(); setInput(input.slice(0, mention.index));} else if (e.key === 'Enter' && !e.shiftKey) {e.preventDefault(); if (mentionJobs[0]) insertJob(mentionJobs[0].id); else void send();}}}/>
        {busy && <button type="button" className="quiet-button" onClick={() => {stop.current = true; if (approval) {approval.resolve(false); setApproval(null);}}}>{tr('Stop', 'Parar', 'Detener')}</button>}<button type="submit" className="primary" disabled={!input.trim() && !attachments.length}>{busy ? tr('Queue', 'Enfileirar', 'Encolar') : tr('Send', 'Enviar', 'Enviar')}</button>
      </form>
    </aside>}
  </>;
}
