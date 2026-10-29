'use client';

import {useEffect, useRef, useState, type ReactNode} from 'react';
import type {Language} from '../lib/design-copy';

/** Comparisons are rendered on demand before the response starts streaming. */
export default function ComparisonDownload({href, file, lang, className, role, children}: {
  href: string; file: string; lang: Language; className?: string; role?: 'menuitem'; children: ReactNode;
}) {
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const request = useRef<AbortController | null>(null);
  const tr = (en: string, pt: string, es: string) => lang === 'pt' ? pt : lang === 'es' ? es : en;
  useEffect(() => () => {request.current?.abort();}, [href]);

  async function download() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setFailed(false);
    setStatus(tr('Preparing comparison…', 'Preparando comparativo…', 'Preparando comparación…'));
    try {
      const response = await fetch(href, {signal: controller.signal});
      if (!response.ok) throw new Error('Download failed');
      const total = response.headers.get('content-encoding') ? 0 : Number(response.headers.get('content-length'));
      const label = tr('Downloading', 'Baixando', 'Descargando');
      setStatus(`${label}…`);
      let blob: Blob;
      if (response.body) {
        const reader = response.body.getReader();
        const parts: ArrayBuffer[] = [];
        let received = 0;
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          parts.push(value.slice().buffer);
          received += value.byteLength;
          setStatus(total > 0 ? `${label} ${Math.min(100, Math.floor(received / total * 100))}%` : `${label} ${(received / 1024 / 1024).toFixed(1)} MB`);
        }
        blob = new Blob(parts, {type: 'video/mp4'});
      } else blob = await response.blob();
      if (!blob.size) throw new Error('Empty download');
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = file;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setStatus(tr('Sent to browser downloads', 'Enviado para os downloads do navegador', 'Enviado a las descargas del navegador'));
    } catch {
      if (!controller.signal.aborted) {
        setFailed(true);
        setStatus(tr('Download failed. Click to retry.', 'Falha no download. Clique para tentar novamente.', 'Error de descarga. Haz clic para reintentar.'));
      }
    } finally {
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <a href={href} download={file} role={role} className={className} aria-disabled={busy} aria-busy={busy} onClick={event => {event.preventDefault(); void download();}}>
    {children}<span className={'comparison-download-status' + (failed ? ' failed' : '')} role="status" aria-live="polite">{busy && <span className="comparison-download-spinner" aria-hidden="true"/>}{status}</span>
  </a>;
}
