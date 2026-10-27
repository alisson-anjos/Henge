'use client';
import {useEffect, useRef, useState, type CSSProperties} from 'react';
import type {Language} from '../lib/design-copy';

export const THEMES = ['system', 'dark', 'light', 'midnight', 'oled', 'paper'] as const;
export type Theme = typeof THEMES[number];
export const THEME_KEY = 'henge-theme';

// Preview colors of each theme: page, card, text, accent.
const SWATCH: Record<Exclude<Theme, 'system'>, [string, string, string, string]> = {
  dark: ['#08080c', '#15151e', '#edebf5', '#d6ff4b'], light: ['#f0f0f4', '#ffffff', '#1d1d27', '#4d7c0f'],
  midnight: ['#060a14', '#101a30', '#e3e9ff', '#d6ff4b'], oled: ['#000000', '#0b0b0e', '#edebf5', '#d6ff4b'],
  paper: ['#f4f1eb', '#fffdf8', '#2d2619', '#4d7c0f'],
};
const resolve = (t: Theme) => t === 'system' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : t;

function Preview({theme}: {theme: Theme}) {
  if (theme === 'system') return <span className="theme-preview split"><Preview theme="dark"/><Preview theme="light"/></span>;
  const [bg, card, text, accent] = SWATCH[theme];
  return <span className="theme-preview" style={{'--p-bg': bg, '--p-card': card, '--p-text': text, '--p-accent': accent} as CSSProperties}><i/><b/><em/></span>;
}

/** Theme picker in the top bar: a button that opens a panel of live-looking previews. 'Auto' follows the OS. The head
 * script in app/layout.tsx applies the saved choice before the first paint. */
export default function ThemeSwitcher({lang}: {lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const names: Record<Theme, string> = {system: tr('Auto', 'Auto', 'Auto'), dark: tr('Dark', 'Escuro', 'Oscuro'), light: tr('Light', 'Claro', 'Claro'),
    midnight: 'Midnight', oled: 'OLED', paper: tr('Paper', 'Papel', 'Papel')};
  const [theme, setTheme] = useState<Theme>('system');
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {try {const t = localStorage.getItem(THEME_KEY) as Theme | null; if (t && THEMES.includes(t)) setTheme(t);} catch {/* private mode */}}, []);
  useEffect(() => {
    const apply = () => {document.documentElement.dataset.theme = resolve(theme);};
    apply();
    if (theme !== 'system') return;
    const media = matchMedia('(prefers-color-scheme: light)'); media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [theme]);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {if (!box.current?.contains(e.target as Node)) setOpen(false);};
    const esc = (e: KeyboardEvent) => {if (e.key === 'Escape') setOpen(false);};
    document.addEventListener('mousedown', away); document.addEventListener('keydown', esc);
    return () => {document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc);};
  }, [open]);
  const choose = (t: Theme) => {setTheme(t); setOpen(false); try {localStorage.setItem(THEME_KEY, t);} catch {/* private mode */}};

  return <div className="theme-switcher" ref={box}>
    <button type="button" className="source-link ghost" aria-haspopup="true" aria-expanded={open} aria-label={tr('Theme', 'Tema', 'Tema')} onClick={() => setOpen(o => !o)}>
      <Preview theme={theme}/><span className="theme-name">{names[theme]}</span>
    </button>
    {open && <div className="theme-popover" role="menu" aria-label={tr('Theme', 'Tema', 'Tema')}>
      {THEMES.map(t => <button key={t} type="button" role="menuitemradio" aria-checked={theme === t} className={theme === t ? 'chosen' : ''} onClick={() => choose(t)}>
        <Preview theme={t}/><span>{names[t]}</span>
      </button>)}
    </div>}
  </div>;
}
