'use client';
import {useEffect, useState} from 'react';
import type {Language} from '../lib/design-copy';

type State = {enabled: boolean; source: 'env' | 'ui' | null; user: string};

/** Lock button in the top bar: turn the optional UI login on, change it or turn it off. Saved on the server
 * (access.json in the bridge data folder); HENGE_PASSWORD in the environment overrides it. */
export default function AccessSettings({lang}: {lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const [state, setState] = useState<State | null>(null);
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState('henge');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {fetch('/api/access').then(r => r.ok ? r.json() : null).then((s: State | null) => {setState(s); if (s?.user) setUser(s.user);}).catch(() => {});}, []);

  async function save(disable: boolean) {
    setError('');
    try {
      const r = await fetch('/api/access', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({user, password, disable})});
      const reply = await r.json(); if (!r.ok) throw Error(reply.error || `HTTP ${r.status}`);
      setState(reply); setPassword(''); setOpen(false);
      // Ask for the new login right away instead of on some later request.
      if (!disable) window.location.reload();
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
  }

  if (!state) return null;
  return <div className="access-settings">
    <button type="button" className="source-link ghost" aria-expanded={open} title={tr('Login for this studio', 'Login deste estúdio', 'Acceso a este estudio')} onClick={() => setOpen(o => !o)}>
      {state.enabled ? '🔒' : '🔓'}<span>{state.enabled ? tr('Protected', 'Protegido', 'Protegido') : tr('Open', 'Aberto', 'Abierto')}</span></button>
    {open && <div className="access-popover surface">
      {state.source === 'env'
        ? <p className="muted">{tr(`Login required (user "${state.user}"). The password comes from HENGE_PASSWORD on the server; change it there.`, `Login obrigatório (usuário "${state.user}"). A senha vem de HENGE_PASSWORD no servidor; troque por lá.`, `Acceso obligatorio (usuario "${state.user}"). La contraseña viene de HENGE_PASSWORD en el servidor; cámbiala allí.`)}</p>
        : <>
          <p className="muted">{state.enabled
            ? tr('Anyone opening this studio must log in. Change the login or turn it off.', 'Quem abrir este estúdio precisa fazer login. Troque o login ou desligue.', 'Quien abra este estudio debe iniciar sesión. Cambia el acceso o desactívalo.')
            : tr('Anyone with this address can use the studio and your GPU. Set a user and password to require a login.', 'Qualquer um com este endereço pode usar o estúdio e sua GPU. Defina usuário e senha para exigir login.', 'Cualquiera con esta dirección puede usar el estudio y tu GPU. Define usuario y contraseña para exigir acceso.')}</p>
          <label>{tr('User', 'Usuário', 'Usuario')}<input value={user} autoComplete="username" onChange={e => setUser(e.target.value)}/></label>
          <label>{tr('Password (8+ characters)', 'Senha (8+ caracteres)', 'Contraseña (8+ caracteres)')}<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)}/></label>
          {error && <small className="validation" role="alert">{error}</small>}
          <div className="plan-actions">
            {state.enabled && <button type="button" className="quiet-button" onClick={() => save(true)}>{tr('Turn off', 'Desligar', 'Desactivar')}</button>}
            <button type="button" className="primary" disabled={password.length < 8 || !user} onClick={() => save(false)}>{state.enabled ? tr('Change login', 'Trocar login', 'Cambiar acceso') : tr('Require login', 'Exigir login', 'Exigir acceso')}</button>
          </div>
        </>}
    </div>}
  </div>;
}
