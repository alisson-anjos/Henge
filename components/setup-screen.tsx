'use client';
import {useEffect, useState} from 'react';
import type {Language} from '../lib/design-copy';

type Requirement = {id: string; label: string; file: string; groups: string[]; state: 'installed' | 'downloading' | 'pending' | 'failed' | 'missing'; total?: number; downloaded?: number; error?: string};
type Setup = {ready: boolean; downloading: boolean; base_ready: boolean; free_gb?: number | null; persistent_volume?: boolean | null};
type Health = {online: boolean; setup?: Setup; requirements?: Requirement[]; models?: Record<string, {label: string; available?: boolean}>};

const gb = (bytes?: number) => bytes ? (bytes / 1e9).toFixed(bytes < 1e9 ? 2 : 1) + ' GB' : '';

/** Full-screen checklist shown until every model is installed and ComfyUI is online. */
export default function SetupScreen({lang}: {lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [health, setHealth] = useState<Health | null>(null);
  const [reachable, setReachable] = useState(true);
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    let disposed = false, timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await fetch('/api/backend/health', {cache: 'no-store'});
        if (!response.ok) throw Error();
        const state: Health = await response.json();
        if (!disposed) {setHealth(state); setReachable(true);}
      } catch {if (!disposed) setReachable(false);}
      if (!disposed) timer = setTimeout(poll, 2000);
    }
    poll(); return () => {disposed = true; clearTimeout(timer);};
  }, []);

  // Nothing until the first answer (no flash when ready); older bridges without a
  // checklist or a finished setup never block the UI.
  if (!health && reachable) return null;
  if (health && reachable && (!health.setup || health.setup.ready)) return null;
  const setup = health?.setup, rows = health?.requirements || [];
  const usable = Object.entries(health?.models || {}).filter(([, m]) => m.available).map(([, m]) => m.label);
  const finishedWithErrors = !!setup && !setup.downloading && rows.some(r => r.state !== 'installed');
  if (dismissed && usable.length) return null;

  const installed = rows.filter(r => r.state === 'installed').length;
  const total = rows.reduce((sum, r) => sum + (r.total || 0), 0);
  const done = rows.reduce((sum, r) => sum + (r.state === 'installed' ? r.total || 0 : r.downloaded || 0), 0);
  const label = (r: Requirement) => ({installed: tr('Ready', 'Pronto', 'Listo'), downloading: tr('Downloading', 'Baixando', 'Descargando'), pending: tr('Waiting', 'Na fila', 'En cola'), failed: tr('Failed', 'Falhou', 'Falló'), missing: tr('Missing', 'Ausente', 'Falta')})[r.state];

  return <div className="setup-screen" role="dialog" aria-modal="true" aria-labelledby="setup-title">
    <div className="setup-card surface">
      <span className="eyebrow accent">{tr('Preparing your studio', 'Preparando o estúdio', 'Preparando el estudio')}</span>
      <h2 id="setup-title">{finishedWithErrors ? tr('Some models are missing', 'Alguns modelos estão faltando', 'Faltan algunos modelos') : tr('Downloading models', 'Baixando os modelos', 'Descargando los modelos')}</h2>
      <p className="muted">{finishedWithErrors
        ? tr('The modes that need them stay unavailable. Fix the errors below and restart the pod; installed files are kept.', 'Os modos que dependem deles ficam indisponíveis. Corrija os erros abaixo e reinicie o pod; o que já foi baixado é mantido.', 'Los modos que los necesitan quedan desactivados. Corrige los errores y reinicia el pod; lo descargado se conserva.')
        : tr('This happens once. The page opens by itself when everything is ready.', 'Isso acontece só na primeira vez. A página abre sozinha quando tudo estiver pronto.', 'Esto ocurre una sola vez. La página se abrirá sola cuando todo esté listo.')}</p>
      {total > 0 && <div className="setup-progress"><progress max={total} value={done}/><span className="mono">{installed}/{rows.length} · {gb(done)} / {gb(total)}</span></div>}
      <ul className="setup-list">
        <li className={health?.online ? 'installed' : 'pending'}><span className="setup-dot" aria-hidden="true"/><div><strong>ComfyUI</strong><small>{health?.online ? tr('Online', 'Online', 'En línea') : reachable ? tr('Starting…', 'Iniciando…', 'Iniciando…') : tr('Waiting for the backend…', 'Aguardando o backend…', 'Esperando el backend…')}</small></div></li>
        {rows.map(r => <li key={r.file} className={r.state}>
          <span className="setup-dot" aria-hidden="true"/>
          <div><strong>{r.label}</strong><small className="setup-file">{r.file}</small>{r.error && <small className="setup-error">{r.error}</small>}
            {r.state === 'downloading' && r.total ? <progress max={r.total} value={r.downloaded || 0}/> : null}</div>
          <span className="setup-state mono">{label(r)}{r.state === 'downloading' && r.total ? ` ${Math.floor(100 * (r.downloaded || 0) / r.total)}%` : r.total ? ` · ${gb(r.total)}` : ''}</span>
        </li>)}
      </ul>
      {setup?.persistent_volume === false && <p className="setup-error">{tr('No volume is mounted at /workspace: models are stored on the container disk and are lost when the pod is reset.', 'Nenhum volume montado em /workspace: os modelos ficam no disco do container e se perdem ao recriar o pod.', 'No hay un volumen montado en /workspace: los modelos quedan en el disco del contenedor y se pierden al recrear el pod.')}{setup.free_gb != null ? ` (${setup.free_gb} GB ${tr('free', 'livres', 'libres')})` : ''}</p>}
      {finishedWithErrors && usable.length > 0 && <button className="primary" onClick={() => setDismissed(true)}>{tr('Continue with', 'Continuar com', 'Continuar con')} {usable.join(', ')}</button>}
    </div>
  </div>;
}
