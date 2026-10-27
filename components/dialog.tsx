'use client';
import {useEffect, useRef, useState} from 'react';

/** In-page confirmation dialogs instead of window.confirm/alert. Call `await confirmDialog({...})` anywhere; the
 * single <DialogHost/> mounted by the studio shows it. Enter confirms, Escape or a click outside cancels. */
export type DialogOptions = {title: string; message?: string; confirm: string; cancel?: string; tone?: 'default' | 'danger'};
type Pending = DialogOptions & {resolve: (ok: boolean) => void};

let show: ((d: Pending) => void) | null = null;

export function confirmDialog(options: DialogOptions): Promise<boolean> {
  return new Promise(resolve => show ? show({...options, resolve}) : resolve(window.confirm(options.title)));
}

/** A message with a single OK button. */
export const alertDialog = (title: string, message?: string, ok = 'OK') => confirmDialog({title, message, confirm: ok}).then(() => undefined);

export function DialogHost() {
  const [dialog, setDialog] = useState<Pending | null>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<Element | null>(null);
  useEffect(() => {show = d => {returnFocus.current = document.activeElement; setDialog(d);}; return () => {show = null;};}, []);
  const close = (ok: boolean) => {
    dialog?.resolve(ok); setDialog(null);
    if (returnFocus.current instanceof HTMLElement) returnFocus.current.focus();
  };
  useEffect(() => {
    if (!dialog) return;
    confirmButton.current?.focus();
    const keys = (e: KeyboardEvent) => {if (e.key === 'Escape') {e.preventDefault(); close(false);}};
    document.addEventListener('keydown', keys); return () => document.removeEventListener('keydown', keys);
  });
  if (!dialog) return null;
  return <div className="dialog-backdrop" onMouseDown={e => {if (e.target === e.currentTarget) close(false);}}>
    <div className={'dialog surface' + (dialog.tone === 'danger' ? ' danger' : '')} role="alertdialog" aria-modal="true" aria-labelledby="dialog-title" aria-describedby={dialog.message ? 'dialog-message' : undefined}>
      <span className="dialog-icon" aria-hidden="true">{dialog.tone === 'danger' ? '!' : '?'}</span>
      <div className="dialog-body">
        <h2 id="dialog-title">{dialog.title}</h2>
        {dialog.message && <p id="dialog-message">{dialog.message}</p>}
        <div className="dialog-actions">
          {dialog.cancel && <button type="button" className="quiet-button" onClick={() => close(false)}>{dialog.cancel}</button>}
          <button type="button" ref={confirmButton} className={dialog.tone === 'danger' ? 'danger-button' : 'primary'} onClick={() => close(true)}>{dialog.confirm}</button>
        </div>
      </div>
    </div>
  </div>;
}
