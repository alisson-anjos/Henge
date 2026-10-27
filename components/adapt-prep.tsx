'use client';
import {useEffect, useState} from 'react';
import type {Language} from '../lib/design-copy';

type State = {enabled: boolean; figure?: boolean; instruction?: string; default_instruction?: string; ready?: boolean; preview_url?: string | null};

/** Approval screen: the adapted reference this job will use. A reference already prepared from the same pictures is
 * reused; it can be regenerated, with the instruction edited. */
export default function AdaptPrep({jobId, lang}: {jobId: string; lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [state, setState] = useState<State | null>(null);
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setState(null); setError('');
    fetch(`/api/backend/jobs/${jobId}/adapted-reference`).then(async r => {const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`); setState(reply); setInstruction(reply.instruction || '');}).catch(e => setError(String(e.message || e)));
  }, [jobId]);

  async function generate() {
    setBusy(true); setError('');
    try {
      const r = await fetch(`/api/backend/jobs/${jobId}/adapted-reference`, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({instruction})});
      const reply = await r.json(); if (!r.ok) throw Error(reply.detail || `HTTP ${r.status}`);
      setState(reply); setInstruction(reply.instruction || '');
    } catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
  }

  if (error && !state) return <small className="muted">{error}</small>;
  if (!state?.enabled) return null;
  const edited = instruction.trim() !== (state.instruction || '').trim();
  return <div className="adapt-prep">
    <div className="label-row"><strong>{state.figure ? tr('Humanoid figure', 'Figura humanoide', 'Figura humanoide') : tr('Adapted reference', 'Referência adaptada', 'Referencia adaptada')}</strong>
      <small className="muted">{state.ready ? tr('Ready · reused, not generated again', 'Pronta · reaproveitada, não será gerada de novo', 'Lista · reutilizada, no se genera de nuevo') : tr('Generated before the video if you approve', 'Gerada antes do vídeo ao aprovar', 'Se genera antes del vídeo al aprobar')}</small></div>
    {state.ready && state.preview_url ? <img src={state.preview_url} alt={tr('Adapted reference', 'Referência adaptada', 'Referencia adaptada')}/> : <div className="adapt-prep-empty">{busy ? tr('Generating… (about 1–3 min)', 'Gerando… (cerca de 1–3 min)', 'Generando… (unos 1–3 min)') : tr('Not generated yet', 'Ainda não gerada', 'Aún no generada')}</div>}
    <label>{tr('Edit instruction', 'Instrução de edição', 'Instrucción de edición')}<textarea value={instruction} disabled={busy} onChange={e => setInstruction(e.target.value)}/></label>
    {error && <p className="validation" role="alert">{error}</p>}
    <div className="plan-actions">
      <button className="quiet-button" disabled={busy || !instruction.trim()} onClick={generate}>{busy ? tr('Generating…', 'Gerando…', 'Generando…') : state.ready && !edited ? tr('Regenerate', 'Regenerar', 'Regenerar') : tr('Generate now', 'Gerar agora', 'Generar ahora')}</button>
      {state.default_instruction && instruction.trim() !== state.default_instruction.trim() && <button className="quiet-button" disabled={busy} onClick={() => setInstruction(state.default_instruction || '')}>{tr('Default instruction', 'Instrução padrão', 'Instrucción predeterminada')}</button>}
    </div>
  </div>;
}
