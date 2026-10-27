'use client';
import {useEffect, useState, type ReactNode} from 'react';
import type {Language} from '../lib/design-copy';
import {AccessForm, useAccessState} from './access-settings';

/** Settings center (top-bar gear) and the first-run wizard: the same panels, as tabs or as skippable steps.
 * Connection: where graphs run (a ComfyUI URL, the Comfy API through the Comfy SDK, or RunPod Serverless), saved on
 * the bridge (connection.json); environment variables still win and show here as read-only. */
export const SETUP_KEY = 'henge-setup-done';
type Tab = 'connection' | 'assistant' | 'access';
type Provider = 'comfyui' | 'comfy_sdk' | 'runpod';
type Connection = {provider: Provider; comfy_url: string; runpod_endpoint_id: string; sdk_target: 'proxy' | 'url' | 'cloud'; sdk_url: string;
  has_runpod_api_key: boolean; runpod_api_key_hint: string; has_sdk_api_key: boolean; sdk_api_key_hint: string; locked: string[]; active: Provider};
type Draft = Partial<Connection> & {runpod_api_key?: string; sdk_api_key?: string};
type Test = {ok: boolean; message: string} | null;

const ENV: Record<string, string> = {provider: 'HENGE_BACKEND', runpod_endpoint_id: 'RUNPOD_ENDPOINT_ID', runpod_api_key: 'RUNPOD_API_KEY',
  sdk_target: 'HENGE_COMFY_SDK_TARGET', sdk_url: 'HENGE_COMFY_SDK_URL', sdk_api_key: 'COMFY_API_KEY'};

export default function SettingsCenter({lang, wizard, initialTab = 'connection', onClose}: {lang: Language; wizard?: boolean; initialTab?: Tab; onClose: () => void}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const steps: ('welcome' | Tab | 'done')[] = ['welcome', 'connection', 'assistant', 'access', 'done'];
  const [step, setStep] = useState(0);
  const [tab, setTab] = useState<Tab>(initialTab);
  const current = wizard ? steps[step] : tab;
  const finish = () => {try {localStorage.setItem(SETUP_KEY, '1');} catch {/* private mode */} onClose();};
  useEffect(() => {const esc = (e: KeyboardEvent) => {if (e.key === 'Escape') wizard ? finish() : onClose();}; addEventListener('keydown', esc); return () => removeEventListener('keydown', esc);});

  const tabs: [Tab, string][] = [['connection', tr('Connection', 'Conexão', 'Conexión')], ['assistant', tr('Assistant', 'Assistente', 'Asistente')], ['access', tr('Login', 'Login', 'Acceso')]];
  const body: Record<string, ReactNode> = {
    welcome: <div className="setup-welcome">
      <span className="brandmark" aria-hidden="true">✳</span>
      <h2>{tr('Welcome to Henge', 'Bem-vindo ao Henge', 'Bienvenido a Henge')}</h2>
      <p>{tr('Three quick steps: where videos are generated, the studio assistant, and an optional login. Every step can be skipped and changed later in Settings.', 'Três passos rápidos: onde os vídeos são gerados, o assistente do estúdio e um login opcional. Dá para pular qualquer passo e mudar depois em Configurações.', 'Tres pasos rápidos: dónde se generan los vídeos, el asistente del estudio y un acceso opcional. Puedes saltar cualquier paso y cambiarlo luego en Configuración.')}</p>
    </div>,
    connection: <ConnectionPanel lang={lang}/>,
    assistant: <div className="settings-note">
      <h3>{tr('Studio assistant (optional)', 'Assistente do estúdio (opcional)', 'Asistente del estudio (opcional)')}</h3>
      <p>{tr('A chat that operates the studio for you: it marks people, picks options and starts generations. It uses Claude, OpenAI or a local model (LM Studio, Ollama). The key stays on the bridge.', 'Um chat que opera o estúdio por você: marca pessoas, escolhe opções e inicia gerações. Usa Claude, OpenAI ou um modelo local (LM Studio, Ollama). A chave fica no bridge.', 'Un chat que maneja el estudio por ti: marca personas, elige opciones e inicia generaciones. Usa Claude, OpenAI o un modelo local (LM Studio, Ollama). La clave queda en el bridge.')}</p>
      <button type="button" className="primary" onClick={() => {dispatchEvent(new CustomEvent('henge:assistant-settings')); wizard ? setStep(s => s + 1) : onClose();}}>{tr('Open assistant settings', 'Abrir ajustes do assistente', 'Abrir ajustes del asistente')}</button>
    </div>,
    access: <AccessPanel lang={lang}/>,
    done: <div className="setup-welcome">
      <span className="brandmark" aria-hidden="true">✓</span>
      <h2>{tr('All set', 'Tudo pronto', 'Todo listo')}</h2>
      <p>{tr('Add a guide video and pictures to start. You can reopen these steps any time from the gear in the top bar.', 'Adicione um vídeo guia e imagens para começar. Você pode reabrir estes passos quando quiser pela engrenagem no topo.', 'Añade un vídeo guía e imágenes para empezar. Puedes reabrir estos pasos cuando quieras desde el engranaje de arriba.')}</p>
    </div>,
  };

  return <div className="dialog-backdrop settings-backdrop" onMouseDown={e => {if (e.target === e.currentTarget) wizard ? undefined : onClose();}}>
    <section className="settings-center" role="dialog" aria-modal="true" aria-label={wizard ? tr('Set up Henge', 'Configurar o Henge', 'Configurar Henge') : tr('Settings', 'Configurações', 'Configuración')}>
      <header className="settings-head">
        <strong>{wizard ? tr('Set up Henge', 'Configurar o Henge', 'Configurar Henge') : tr('Settings', 'Configurações', 'Configuración')}</strong>
        {wizard ? <ol className="setup-steps" aria-label={tr('Steps', 'Passos', 'Pasos')}>{steps.map((s, i) => <li key={s} className={i === step ? 'current' : i < step ? 'done' : ''}/>)}</ol>
          : <nav className="settings-tabs">{tabs.map(([id, label]) => <button key={id} type="button" aria-pressed={tab === id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}</nav>}
        <button type="button" className="icon-btn settings-close" aria-label={tr('Close', 'Fechar', 'Cerrar')} onClick={wizard ? finish : onClose}>×</button>
      </header>
      <div className="settings-body">{body[current]}</div>
      {wizard && <footer className="settings-foot">
        {step > 0 && step < steps.length - 1 && <button type="button" className="quiet-button" onClick={() => setStep(s => s - 1)}>{tr('Back', 'Voltar', 'Atrás')}</button>}
        <span/>
        {step < steps.length - 1 && <button type="button" className="quiet-button" onClick={step === 0 ? finish : () => setStep(s => s + 1)}>{step === 0 ? tr('Skip setup', 'Pular configuração', 'Saltar configuración') : tr('Skip', 'Pular', 'Saltar')}</button>}
        <button type="button" className="primary" onClick={step === steps.length - 1 ? finish : () => setStep(s => s + 1)}>{step === 0 ? tr('Start', 'Começar', 'Empezar') : step === steps.length - 1 ? tr('Open the studio', 'Abrir o estúdio', 'Abrir el estudio') : tr('Next', 'Próximo', 'Siguiente')}</button>
      </footer>}
    </section>
  </div>;
}

function AccessPanel({lang}: {lang: Language}) {
  const [state, setState] = useAccessState();
  if (!state) return null;
  return <AccessForm lang={lang} state={state} onSaved={(s, enabled) => {setState(s); if (enabled) window.location.reload();}}/>;
}

function ConnectionPanel({lang}: {lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [saved, setSaved] = useState<Connection | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [test, setTest] = useState<Test>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    fetch('/api/backend/connection').then(async r => {if (!r.ok) throw Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`); return r.json();})
      .then((c: Connection) => {setSaved(c); setDraft(c);})
      .catch(e => setError(tr(`The bridge does not answer (${e.message}). Start it, then reopen this panel.`, `O bridge não responde (${e.message}). Inicie-o e reabra este painel.`, `El bridge no responde (${e.message}). Inícialo y vuelve a abrir este panel.`)));
  }, []);
  if (error) return <p className="job-callout error">{error}</p>;
  if (!saved) return <p className="muted"><span className="spinner"/>{tr('Loading…', 'Carregando…', 'Cargando…')}</p>;
  const locked = (k: string) => saved.locked.includes(k);
  const set = (patch: Draft) => {setDraft(d => ({...d, ...patch})); setTest(null);};
  const provider = draft.provider || 'comfyui';
  const send = async (path: string) => {
    setBusy(path); setTest(null);
    try {
      const r = await fetch('/api/backend/' + path, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(draft)});
      const reply = await r.json();
      if (!r.ok) {setTest({ok: false, message: reply.detail || `HTTP ${r.status}`}); return;}
      if (path === 'connection') {setSaved(reply); setDraft(reply); setTest({ok: true, message: reply.message + ' · ' + tr('saved and in use', 'salvo e em uso', 'guardado y en uso')}); dispatchEvent(new CustomEvent('henge:connection-changed'));}
      else setTest(reply);
    } catch (e) {setTest({ok: false, message: e instanceof Error ? e.message : String(e)});}
    finally {setBusy('');}
  };
  const field = (k: keyof Draft, label: string, props: {placeholder?: string; secret?: boolean; hint?: string} = {}) => <label className="field">
    <span>{label}{locked(k as string) && <em className="env-lock"> · {tr('set by', 'definido por', 'definido por')} {ENV[k as string]}</em>}</span>
    <input type={props.secret ? 'password' : 'text'} autoComplete="off" disabled={locked(k as string)} value={(draft[k] as string) || ''} placeholder={props.placeholder} onChange={e => set({[k]: e.target.value})}/>
    {props.hint && <small className="muted">{props.hint}</small>}
  </label>;
  const cards: {id: Provider; title: string; who: string}[] = [
    {id: 'comfyui', title: 'ComfyUI', who: tr('Your ComfyUI with the Henge nodes, on this machine or another one.', 'Seu ComfyUI com os nós do Henge, nesta máquina ou em outra.', 'Tu ComfyUI con los nodos de Henge, en esta máquina u otra.')},
    {id: 'comfy_sdk', title: 'Comfy API · SDK', who: tr('The official Comfy API v2 through comfy-sdk: Henge starts comfy-api-proxy in front of your ComfyUI, or uses an API URL or Comfy Cloud.', 'A Comfy API v2 oficial pelo comfy-sdk: o Henge inicia o comfy-api-proxy na frente do seu ComfyUI, ou usa uma URL de API ou o Comfy Cloud.', 'La Comfy API v2 oficial con comfy-sdk: Henge inicia comfy-api-proxy delante de tu ComfyUI, o usa una URL de API o Comfy Cloud.')},
    {id: 'runpod', title: 'RunPod Serverless', who: tr('No local GPU: a serverless endpoint that scales to zero and bills per second.', 'Sem GPU local: um endpoint serverless que desliga sozinho e cobra por segundo.', 'Sin GPU local: un endpoint serverless que se apaga solo y cobra por segundo.')},
  ];
  return <div className="connection-panel">
    <p className="muted">{tr('Where Henge runs its ComfyUI workflows. In use now:', 'Onde o Henge roda os workflows do ComfyUI. Em uso agora:', 'Dónde Henge ejecuta los workflows de ComfyUI. En uso ahora:')} <strong>{cards.find(c => c.id === saved.active)?.title}</strong></p>
    <div className="provider-cards" role="radiogroup">
      {cards.map(c => <button key={c.id} type="button" role="radio" aria-checked={provider === c.id} disabled={locked('provider') && provider !== c.id} className={'provider-card' + (provider === c.id ? ' chosen' : '')} onClick={() => set({provider: c.id})}>
        <strong>{c.title}{saved.active === c.id && <span className="job-chip on">{tr('in use', 'em uso', 'en uso')}</span>}</strong><small>{c.who}</small></button>)}
    </div>
    {locked('provider') && <small className="muted env-lock">{tr('The provider is set by HENGE_BACKEND on the server.', 'O provedor é definido por HENGE_BACKEND no servidor.', 'El proveedor lo define HENGE_BACKEND en el servidor.')}</small>}
    <div className="provider-fields">
      {provider === 'comfyui' && field('comfy_url', tr('ComfyUI address', 'Endereço do ComfyUI', 'Dirección de ComfyUI'), {placeholder: 'http://127.0.0.1:8188', hint: tr('Install the Henge nodes in its custom_nodes (see the README).', 'Instale os nós do Henge na pasta custom_nodes dele (veja o README).', 'Instala los nodos de Henge en su custom_nodes (ver el README).')})}
      {provider === 'comfy_sdk' && <>
        <div className="segmented" role="radiogroup">{([['proxy', tr('My ComfyUI (Henge starts the proxy)', 'Meu ComfyUI (o Henge inicia o proxy)', 'Mi ComfyUI (Henge inicia el proxy)')], ['url', tr('Comfy API URL', 'URL da Comfy API', 'URL de Comfy API')], ['cloud', 'Comfy Cloud']] as const).map(([id, label]) =>
          <button key={id} type="button" role="radio" aria-checked={(draft.sdk_target || 'proxy') === id} disabled={locked('sdk_target')} className={(draft.sdk_target || 'proxy') === id ? 'chosen' : ''} onClick={() => set({sdk_target: id})}>{label}</button>)}</div>
        {(draft.sdk_target || 'proxy') === 'proxy' && field('comfy_url', tr('ComfyUI address', 'Endereço do ComfyUI', 'Dirección de ComfyUI'), {placeholder: 'http://127.0.0.1:8188', hint: tr('Henge runs comfy-api-proxy on 127.0.0.1:8199 and talks to it with the Comfy SDK.', 'O Henge roda o comfy-api-proxy em 127.0.0.1:8199 e fala com ele pelo Comfy SDK.', 'Henge ejecuta comfy-api-proxy en 127.0.0.1:8199 y le habla con el Comfy SDK.')})}
        {draft.sdk_target === 'url' && <>{field('sdk_url', tr('Comfy API URL', 'URL da Comfy API', 'URL de Comfy API'), {placeholder: 'https://my-comfy-api.example.com'})}{field('sdk_api_key', tr('Token (optional)', 'Token (opcional)', 'Token (opcional)'), {secret: true, placeholder: saved.has_sdk_api_key ? `${tr('saved', 'salvo', 'guardado')} ${saved.sdk_api_key_hint}` : ''})}</>}
        {draft.sdk_target === 'cloud' && <>{field('sdk_api_key', tr('Comfy Cloud API key', 'Chave da API do Comfy Cloud', 'Clave de API de Comfy Cloud'), {secret: true, placeholder: saved.has_sdk_api_key ? `${tr('saved', 'salvo', 'guardado')} ${saved.sdk_api_key_hint}` : 'comfyui-…'})}
          <small className="job-callout warn">{tr('Comfy Cloud must have the Henge custom nodes and models; until then use your own ComfyUI.', 'O Comfy Cloud precisa ter os nós e modelos do Henge; até lá use seu próprio ComfyUI.', 'Comfy Cloud necesita los nodos y modelos de Henge; mientras tanto usa tu propio ComfyUI.')}</small></>}
      </>}
      {provider === 'runpod' && <>
        {field('runpod_endpoint_id', tr('Endpoint ID', 'ID do endpoint', 'ID del endpoint'), {placeholder: 'abc123xyz', hint: tr('Create it from the Henge serverless template (docs/SERVERLESS.md).', 'Crie a partir do template serverless do Henge (docs/SERVERLESS.md).', 'Créalo desde la plantilla serverless de Henge (docs/SERVERLESS.md).')})}
        {field('runpod_api_key', tr('RunPod API key', 'Chave da API do RunPod', 'Clave de API de RunPod'), {secret: true, placeholder: saved.has_runpod_api_key ? `${tr('saved', 'salva', 'guardada')} ${saved.runpod_api_key_hint}` : 'rpa_…'})}
      </>}
    </div>
    {test && <p className={'job-callout ' + (test.ok ? 'ok' : 'error')} role="status">{test.ok ? '✓ ' : ''}{test.message}</p>}
    <div className="access-actions">
      <button type="button" className="quiet-button" disabled={!!busy} onClick={() => send('connection/test')}>{busy === 'connection/test' ? <><span className="spinner"/>{tr('Testing…', 'Testando…', 'Probando…')}</> : tr('Test connection', 'Testar conexão', 'Probar conexión')}</button>
      <button type="button" className="primary" disabled={!!busy} onClick={() => send('connection')}>{busy === 'connection' ? <><span className="spinner"/>{tr('Saving…', 'Salvando…', 'Guardando…')}</> : tr('Save and use', 'Salvar e usar', 'Guardar y usar')}</button>
    </div>
    <small className="muted">{tr('Keys are stored on the bridge (connection.json in its data folder) and never sent back to the browser. Environment variables override what is saved here.', 'As chaves ficam no bridge (connection.json na pasta de dados) e nunca voltam para o navegador. Variáveis de ambiente têm prioridade sobre o que é salvo aqui.', 'Las claves quedan en el bridge (connection.json en su carpeta de datos) y nunca vuelven al navegador. Las variables de entorno tienen prioridad sobre lo guardado aquí.')}</small>
  </div>;
}
