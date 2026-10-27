'use client';
import {Children, Fragment, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode} from 'react';
import {createPortal} from 'react-dom';

/** Drop-in replacement for <select>: same props (value, onChange with e.target.value, <option> children, disabled,
 * aria-label), but the open list is drawn by the page (themed, rounded, keyboard-friendly) instead of the OS. */
type Option = {value: string; label: ReactNode; text: string; disabled: boolean};
type Props = {value?: string | number; onChange?: (e: {target: {value: string}}) => void; children?: ReactNode; disabled?: boolean;
  className?: string; title?: string; 'aria-label'?: string};

const textOf = (node: ReactNode): string => typeof node === 'string' || typeof node === 'number' ? String(node)
  : Array.isArray(node) ? node.map(textOf).join('') : isValidElement(node) ? textOf((node.props as {children?: ReactNode}).children) : '';

function optionsOf(children: ReactNode): Option[] {
  const out: Option[] = [];
  Children.forEach(children, child => {
    if (!isValidElement(child)) return;
    const props = child.props as {value?: string | number; children?: ReactNode; disabled?: boolean; hidden?: boolean};
    if (child.type === Fragment) {out.push(...optionsOf(props.children)); return;}
    if (child.type === 'option' && !props.hidden) {
      const text = textOf(props.children);
      out.push({value: String(props.value ?? text), label: props.children, text, disabled: !!props.disabled});
    }
  });
  return out;
}

export default function Select({value, onChange, children, disabled, className, title, 'aria-label': ariaLabel}: Props) {
  const options = optionsOf(children);
  const current = String(value ?? '');
  const selected = options.find(o => o.value === current) ?? options[0];
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [place, setPlace] = useState<{left: number; top?: number; bottom?: number; width: number; maxHeight: number; accent: string} | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const typed = useRef({text: '', at: 0});
  const id = useId();

  const position = () => {
    const b = button.current; if (!b) return;
    const r = b.getBoundingClientRect(), below = innerHeight - r.bottom - 12, above = r.top - 12;
    const up = below < 220 && above > below;
    setPlace({left: Math.min(r.left, innerWidth - Math.max(r.width, 180) - 8), width: Math.max(r.width, 180), maxHeight: Math.min(320, up ? above : below),
      ...(up ? {bottom: innerHeight - r.top + 6} : {top: r.bottom + 6}), accent: getComputedStyle(b).getPropertyValue('--accent')});
  };
  const show = () => {if (disabled || !options.length) return; position(); setActive(Math.max(0, options.indexOf(selected))); setOpen(true);};
  const choose = (o: Option) => {if (o.disabled) return; setOpen(false); button.current?.focus(); if (o.value !== current) onChange?.({target: {value: o.value}});};

  // Keep the active item visible by scrolling the list only (scrollIntoView would also scroll the page, which closes it).
  useLayoutEffect(() => {
    const l = list.current, item = l?.children[active] as HTMLElement | undefined;
    if (!open || !l || !item) return;
    if (item.offsetTop < l.scrollTop) l.scrollTop = item.offsetTop - 5;
    else if (item.offsetTop + item.offsetHeight > l.scrollTop + l.clientHeight) l.scrollTop = item.offsetTop + item.offsetHeight - l.clientHeight + 5;
  }, [open, active]);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {if (!list.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false);};
    // Page scroll or resize: follow the button; close only once it leaves the screen.
    const move = (e: Event) => {
      if (list.current?.contains(e.target as Node)) return;
      const r = button.current?.getBoundingClientRect();
      if (!r || r.bottom < 0 || r.top > innerHeight) setOpen(false); else position();
    };
    document.addEventListener('mousedown', away); addEventListener('scroll', move, true); addEventListener('resize', move);
    return () => {document.removeEventListener('mousedown', away); removeEventListener('scroll', move, true); removeEventListener('resize', move);};
  }, [open]);

  const step = (from: number, dir: number) => {
    for (let i = 1; i <= options.length; i++) {const k = (from + dir * i + options.length) % options.length; if (!options[k].disabled) return k;}
    return from;
  };
  const keys = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {e.preventDefault(); show();}
      return;
    }
    if (e.key === 'ArrowDown') {e.preventDefault(); setActive(a => step(a, 1));}
    else if (e.key === 'ArrowUp') {e.preventDefault(); setActive(a => step(a, -1));}
    else if (e.key === 'Home') {e.preventDefault(); setActive(step(-1, 1));}
    else if (e.key === 'End') {e.preventDefault(); setActive(step(options.length, -1));}
    else if (e.key === 'Enter' || e.key === ' ') {e.preventDefault(); if (options[active]) choose(options[active]);}
    else if (e.key === 'Escape' || e.key === 'Tab') {setOpen(false);}
    else if (e.key.length === 1) {
      const now = Date.now(); typed.current = {text: (now - typed.current.at < 700 ? typed.current.text : '') + e.key.toLowerCase(), at: now};
      const k = options.findIndex(o => !o.disabled && o.text.toLowerCase().startsWith(typed.current.text)); if (k >= 0) setActive(k);
    }
  };

  return <>
    <button type="button" ref={button} className={'select-button' + (className ? ' ' + className : '')} disabled={disabled} title={title}
      aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => open ? setOpen(false) : show()} onKeyDown={keys}>
      <span className="select-value">{selected?.label}</span><span className="select-caret" aria-hidden="true"/>
    </button>
    {open && place && createPortal(
      <ul ref={list} id={id} role="listbox" aria-label={ariaLabel} className="select-list" onKeyDown={keys}
        style={{left: place.left, top: place.top, bottom: place.bottom, minWidth: place.width, maxHeight: place.maxHeight, ...(place.accent ? {'--accent': place.accent} : {})} as React.CSSProperties}>
        {options.map((o, i) => <li key={o.value} role="option" aria-selected={o.value === current} aria-disabled={o.disabled || undefined}
          className={(i === active ? 'active ' : '') + (o.value === current ? 'chosen' : '')} onMouseEnter={() => setActive(i)} onMouseDown={e => e.preventDefault()} onClick={() => choose(o)}>
          <span>{o.label}</span>{o.value === current && <span className="select-check" aria-hidden="true">✓</span>}
        </li>)}
      </ul>, document.body)}
  </>;
}
