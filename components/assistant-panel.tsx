'use client';
import {useEffect, useRef, useState} from 'react';
import type {Language} from '../lib/design-copy';

/** One studio action the assistant asked for, run here so the user sees the screen change. */
export type StudioCall = {id: string; name: string; input: Record<string, unknown>};
export type StudioResult = {text: string; images?: string[]; is_error?: boolean};
export type StudioController = {state: () => Record<string, unknown>; run: (call: StudioCall) => Promise<StudioResult>};

type Result = {id: string; name: string; text: string; images?: string[]; is_error?: boolean};
type Message =
  | {role: 'user'; text: string; images?: string[]}
  | {role: 'assistant'; text: string; tool_calls?: StudioCall[]; native?: unknown; native_provider?: string}
  | {role: 'tool'; results: Result[]};
type Config = {provider: 'anthropic' | 'openai'; model: string; base_url: string; effort: string; has_key: boolean; key_hint: string};

const PRESETS: Record<string, {provider: Config['provider']; model: string; base_url: string}> = {
  claude: {provider: 'anthropic', model: 'claude-opus-5-5', base_url: ''},
  openai: {provider: 'openai', model: 'gpt-5.1', base_url: 'https://api.openai.com/v1'},
  lmstudio: {provider: 'openai', model: 'qwen3-vl-8b-instruct', base_url: 'http://127.0.0.1:1234/v1'},
  ollama: {provider: 'openai', model: 'qwen2.5vl', base_url: 'http://127.0.0.1:11434/v1'},
};

const label = (name: string, input: Record<string, unknown>) => {
  const v = (k: string) => input[k] as string | number | undefined;
  switch (name) {
    case 'find_people': return `find_people · ${v('time')}s`;
    case 'view_frame': return `view_frame · ${v('time')}s`;
    case 'mark_subject': return `mark_subject · #${v('person')} → Picture ${(input.picture_slots as number[] || []).join(', ')}`;
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
export default function AssistantPanel({controller, lang}: {controller: StudioController; lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {try {setExpanded(localStorage.getItem('henge-assistant-expanded') === '1');} catch {/* private mode */}}, []);
  const toggleExpanded = () => setExpanded(v => {try {localStorage.setItem('henge-assistant-expanded', v ? '0' : '1');} catch {/* private mode */} return !v;});
  const [settings, setSettings] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [draft, setDraft] = useState<Partial<Config> & {api_key?: string}>({});
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const stop = useRef(false);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {if (open && !config) fetch('/api/backend/assistant/config').then(r => r.json()).then((c: Config) => {setConfig(c); setDraft(c); if (!c.has_key && c.provider === 'anthropic') setSettings(true);}).catch(() => setError(tr('The bridge is offline.', 'O bridge está offline.', 'El bridge está desconectado.')));}, [open]);
  useEffect(() => {list.current?.scrollTo({top: list.current.scrollHeight, behavior: 'smooth'});}, [messages, busy]);

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

  async function send() {
    const text = input.trim(); if (!text || busy) return;
    setInput(''); setError(''); stop.current = false;
    let history: Message[] = [...messages, {role: 'user', text: `${text}\n\n[studio state] ${JSON.stringify(controller.state())}`}];
    setMessages(history);
    try {
      for (let round = 0; round < 40 && !stop.current; round++) {
        setBusy(tr('Thinking…', 'Pensando…', 'Pensando…'));
        const reply = await step(history);
        history = reply.messages; setMessages(history);
        if (reply.done || !reply.studio_calls.length) break;
        const results: Result[] = [...reply.job_results];
        for (const call of reply.studio_calls) {
          if (stop.current) {results.push({id: call.id, name: call.name, text: 'Stopped by the user.', is_error: true}); continue;}
          setBusy(label(call.name, call.input));
          try {results.push({id: call.id, name: call.name, ...(await controller.run(call))});}
          catch (e) {results.push({id: call.id, name: call.name, text: e instanceof Error ? e.message : String(e), is_error: true});}
        }
        history = [...history, {role: 'tool', results}]; setMessages(history);
      }
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy('');}
  }

  const presetOf = (c: Partial<Config>) => Object.entries(PRESETS).find(([, p]) => p.provider === c.provider && (p.provider === 'anthropic' || p.base_url === c.base_url))?.[0] || 'custom';
  return <>
    <button type="button" className="assistant-fab" aria-expanded={open} onClick={() => setOpen(o => !o)}>{open ? '×' : '✦'}<span>{tr('Assistant', 'Assistente', 'Asistente')}</span></button>
    {open && <aside className={'assistant-panel surface' + (expanded ? ' expanded' : '')} aria-label={tr('Studio assistant', 'Assistente do estúdio', 'Asistente del estudio')}>
      <header><strong>{tr('Studio assistant', 'Assistente do estúdio', 'Asistente del estudio')}</strong>
        <small className="muted mono">{config ? `${config.model}` : ''}</small>
        <span><button type="button" className="quiet-button" onClick={() => {setMessages([]); setError('');}} disabled={!!busy}>{tr('New chat', 'Nova conversa', 'Nueva conversación')}</button>
          <button type="button" className="quiet-button" aria-pressed={expanded} title={expanded ? tr('Smaller', 'Diminuir', 'Reducir') : tr('Expand', 'Expandir', 'Ampliar')} aria-label={expanded ? tr('Smaller', 'Diminuir', 'Reducir') : tr('Expand', 'Expandir', 'Ampliar')} onClick={toggleExpanded}>{expanded ? '⤡' : '⤢'}</button>
          <button type="button" className="quiet-button" aria-pressed={settings} onClick={() => setSettings(s => !s)}>⚙</button></span></header>
      {settings && config && <div className="assistant-settings">
        <label>{tr('Model provider', 'Provedor do modelo', 'Proveedor del modelo')}<select value={presetOf(draft)} onChange={e => {const p = PRESETS[e.target.value]; if (p) setDraft(d => ({...d, ...p}));}}>
          <option value="claude">Claude (Anthropic API)</option><option value="openai">OpenAI (GPT)</option><option value="lmstudio">LM Studio ({tr('local', 'local', 'local')})</option><option value="ollama">Ollama ({tr('local', 'local', 'local')})</option><option value="custom">{tr('Other OpenAI-compatible API', 'Outra API compatível com OpenAI', 'Otra API compatible con OpenAI')}</option></select></label>
        {presetOf(draft) === 'custom' && <label>{tr('Type', 'Tipo', 'Tipo')}<select value={draft.provider} onChange={e => setDraft(d => ({...d, provider: e.target.value as Config['provider']}))}><option value="openai">OpenAI-compatible</option><option value="anthropic">Anthropic</option></select></label>}
        <label>{tr('Model', 'Modelo', 'Modelo')}<input value={draft.model || ''} onChange={e => setDraft(d => ({...d, model: e.target.value}))}/></label>
        {draft.provider === 'openai' && <label>Base URL<input value={draft.base_url || ''} placeholder="https://api.openai.com/v1" onChange={e => setDraft(d => ({...d, base_url: e.target.value}))}/></label>}
        <label>{tr('API key', 'Chave da API', 'Clave de la API')}<input type="password" autoComplete="off" value={draft.api_key || ''} placeholder={config.has_key ? `${tr('saved', 'salva', 'guardada')} ${config.key_hint}` : draft.provider === 'openai' ? tr('not needed for local servers', 'não precisa para servidores locais', 'no hace falta en servidores locales') : 'sk-ant-…'} onChange={e => setDraft(d => ({...d, api_key: e.target.value}))}/></label>
        {draft.provider === 'anthropic' && <label>{tr('Effort', 'Esforço', 'Esfuerzo')}<select value={draft.effort ?? 'medium'} onChange={e => setDraft(d => ({...d, effort: e.target.value}))}>{['low', 'medium', 'high'].map(v => <option key={v} value={v}>{v}</option>)}<option value="">{tr('model default', 'padrão do modelo', 'predeterminado')}</option></select></label>}
        <small className="muted">{tr('The key stays on the bridge (assistant.json in its data folder); the browser never receives it. The model needs vision and tool calling.', 'A chave fica no bridge (assistant.json na pasta de dados); o navegador nunca a recebe. O modelo precisa de visão e de chamada de ferramentas.', 'La clave queda en el bridge (assistant.json en su carpeta de datos); el navegador nunca la recibe. El modelo necesita visión y llamadas a herramientas.')}</small>
        <div className="plan-actions"><button type="button" className="primary" onClick={saveSettings}>{tr('Save', 'Salvar', 'Guardar')}</button></div>
      </div>}
      <div className="assistant-messages" ref={list}>
        {!messages.length && <p className="muted">{tr('Attach the video and the pictures, then say what you want, e.g. "the fighter on the left becomes Picture 1 and the other one Picture 2". The assistant marks the people, picks the options, shows you the plan and generates.', 'Anexe o vídeo e as imagens e diga o que quer, por exemplo "o lutador da esquerda vira a Picture 1 e o outro a Picture 2". O assistente marca as pessoas, escolhe as opções, mostra o plano e gera.', 'Adjunta el vídeo y las imágenes y di lo que quieres, por ejemplo "el luchador de la izquierda será la Picture 1 y el otro la Picture 2". El asistente marca a las personas, elige las opciones, te muestra el plan y genera.')}</p>}
        {messages.map((m, i) => m.role === 'user' ? <div key={i} className="assistant-msg user">{m.text.split('\n\n[studio state]')[0]}</div>
          : m.role === 'assistant' ? <div key={i} className="assistant-msg">{m.text && <p>{m.text}</p>}{m.tool_calls?.map(c => <small key={c.id} className="assistant-tool mono">⚙ {label(c.name, c.input)}</small>)}</div>
          : <div key={i} className="assistant-results">{m.results.map(r => <div key={r.id}>{r.is_error && <small className="validation">{r.text}</small>}{r.images?.map((src, j) => <img key={j} src={src} alt={r.name}/>)}</div>)}</div>)}
        {busy && <small className="assistant-busy mono">{busy}</small>}
        {error && <p className="validation" role="alert">{error}</p>}
      </div>
      <form className="assistant-input" onSubmit={e => {e.preventDefault(); void send();}}>
        <textarea value={input} rows={2} placeholder={tr('What do you want to make?', 'O que você quer fazer?', '¿Qué quieres hacer?')} onChange={e => setInput(e.target.value)} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey) {e.preventDefault(); void send();}}}/>
        {busy ? <button type="button" className="quiet-button" onClick={() => {stop.current = true;}}>{tr('Stop', 'Parar', 'Detener')}</button> : <button type="submit" className="primary" disabled={!input.trim()}>{tr('Send', 'Enviar', 'Enviar')}</button>}
      </form>
    </aside>}
  </>;
}
