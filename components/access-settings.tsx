'use client';
import {useEffect, useRef, useState} from 'react';
import type {Language} from '../lib/design-copy';

export type State = {enabled: boolean; source: 'env' | 'ui' | null; user: string};

const Lock = ({open}: {open: boolean}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
  <rect x="4" y="11" width="16" height="10" rx="2.5"/><path d={open ? 'M8 11V7a4 4 0 0 1 7.5-2' : 'M8 11V7a4 4 0 0 1 8 0v4'}/></svg>;

/** Lock button in the top bar: turn the optional UI login on, change it or turn it off. Saved on the server
 * (access.json in the bridge data folder); HENGE_PASSWORD in the environment overrides it. */
/** The login form itself: used in the top-bar popover, the settings center and the first-run wizard. */
export function AccessForm({lang, state, onSaved, compact}: {lang: Language; state: State; onSaved: (s: State, enabled: boolean) => void; compact?: boolean}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [user, setUser] = useState(state.user || 'henge');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  async function save(disable: boolean) {
    setError('');
    try {
      const r = await fetch('/api/access', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({user, password, disable})});
      const reply = await r.json(); if (!r.ok) throw Error(reply.error || `HTTP ${r.status}`);
      setPassword(''); onSaved(reply, !disable);
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
  }
  return <form className={'access-form' + (compact ? ' compact' : '')} onSubmit={e => {e.preventDefault(); if (password.length >= 8 && user) void save(false);}}>
    <header><span className={'access-icon' + (state.enabled ? ' on' : '')}><Lock open={!state.enabled}/></span>
      <div><strong>{tr('Studio login', 'Login do estúdio', 'Acceso al estudio')}</strong>
        <small>{state.enabled ? tr(`Required · user "${state.user}"`, `Obrigatório · usuário "${state.user}"`, `Obligatorio · usuario "${state.user}"`) : tr('Off · anyone with the address can use it', 'Desligado · qualquer um com o endereço pode usar', 'Desactivado · cualquiera con la dirección puede usarlo')}</small></div></header>
    {state.source === 'env'
      ? <p>{tr('The password comes from HENGE_PASSWORD on the server; change it there.', 'A senha vem de HENGE_PASSWORD no servidor; troque por lá.', 'La contraseña viene de HENGE_PASSWORD en el servidor; cámbiala allí.')}</p>
      : <>
        <p>{state.enabled
          ? tr('Change the user or password, or turn the login off.', 'Troque o usuário ou a senha, ou desligue o login.', 'Cambia el usuario o la contraseña, o desactiva el acceso.')
          : tr('Anyone who reaches this address can use the studio and your GPU. Set a login before sharing it.', 'Qualquer um que acesse este endereço pode usar o estúdio e sua GPU. Defina um login antes de compartilhar.', 'Cualquiera que llegue a esta dirección puede usar el estudio y tu GPU. Define un acceso antes de compartirlo.')}</p>
        <label className="field"><span>{tr('User', 'Usuário', 'Usuario')}</span><input value={user} autoComplete="username" onChange={e => setUser(e.target.value)}/></label>
        <label className="field"><span>{tr('Password', 'Senha', 'Contraseña')}</span>
          <span className="field-row"><input type={show ? 'text' : 'password'} autoComplete="new-password" value={password} placeholder={tr('8+ characters', '8+ caracteres', '8+ caracteres')} onChange={e => setPassword(e.target.value)}/>
            <button type="button" className="field-toggle" onClick={() => setShow(v => !v)}>{show ? tr('Hide', 'Ocultar', 'Ocultar') : tr('Show', 'Mostrar', 'Mostrar')}</button></span></label>
        {error && <small className="validation" role="alert">{error}</small>}
        <div className="access-actions">
          {state.enabled && <button type="button" className="quiet-button" onClick={() => save(true)}>{tr('Turn off', 'Desligar', 'Desactivar')}</button>}
          <button type="submit" className="primary" disabled={password.length < 8 || !user}>{state.enabled ? tr('Save login', 'Salvar login', 'Guardar acceso') : tr('Require login', 'Exigir login', 'Exigir acceso')}</button>
        </div>
      </>}
  </form>;
}

export function useAccessState() {
  const [state, setState] = useState<State | null>(null);
  useEffect(() => {fetch('/api/access').then(r => r.ok ? r.json() : null).then(setState).catch(() => {});}, []);
  return [state, setState] as const;
}

/** Lock button in the top bar: turn the optional UI login on, change it or turn it off. Saved on the server
 * (access.json in the bridge data folder); HENGE_PASSWORD in the environment overrides it. */
export default function AccessSettings({lang}: {lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [state, setState] = useAccessState();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {if (!box.current?.contains(e.target as Node)) setOpen(false);};
    const esc = (e: KeyboardEvent) => {if (e.key === 'Escape') setOpen(false);};
    document.addEventListener('mousedown', away); document.addEventListener('keydown', esc);
    return () => {document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc);};
  }, [open]);
  if (!state) return null;
  return <div className="access-settings" ref={box}>
    <button type="button" className={'source-link ghost access-button' + (state.enabled ? ' on' : '')} aria-expanded={open} title={tr('Login for this studio', 'Login deste estúdio', 'Acceso a este estudio')} onClick={() => setOpen(o => !o)}>
      <Lock open={!state.enabled}/><span>{state.enabled ? tr('Protected', 'Protegido', 'Protegido') : tr('Open', 'Aberto', 'Abierto')}</span></button>
    {open && <div className="access-popover"><AccessForm lang={lang} state={state} onSaved={(s, enabled) => {setState(s); setOpen(false); if (enabled) window.location.reload();}}/></div>}
  </div>;
}
