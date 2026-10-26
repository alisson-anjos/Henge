'use client';
import {useEffect, useRef, useState} from 'react';
import type {Language} from '../lib/design-copy';
import type {Picture} from '../lib/media';

type Image = {blob: Blob; url: string};
const load = (src: string) => new Promise<HTMLImageElement>((resolve, reject) => {const image = new window.Image(); image.onload = () => resolve(image); image.onerror = reject; image.src = src;});

/** The guide's first selected frame, edited with FIBO 2 or replaced by an uploaded image, then cropped and resized to
 * the frame's exact size so it can be propagated (Motion Transfer · first-frame propagate). */
export default function FirstFrameModal({videoUrl, start, pictures, lang, onUse, onClose}: {videoUrl: string; start: number; pictures: Picture[]; lang: Language; onUse: (file: File) => void; onClose: () => void}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const dialog = useRef<HTMLDialogElement>(null), upload = useRef<HTMLInputElement>(null);
  const [frame, setFrame] = useState<Image & {width: number; height: number} | null>(null);
  const [result, setResult] = useState<Image | null>(null);
  const [fiboReady, setFiboReady] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [useRefs, setUseRefs] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    dialog.current?.showModal();
    fetch('/api/backend/health').then(r => r.json()).then(h => setFiboReady(!!h.fibo_ready)).catch(() => {});
    const video = document.createElement('video');
    video.muted = true; video.preload = 'auto'; video.src = videoUrl;
    video.onloadedmetadata = () => {video.currentTime = Math.min(start + .001, Math.max(0, video.duration - .05));};
    video.onseeked = () => {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth; canvas.height = video.videoHeight;
      canvas.getContext('2d')?.drawImage(video, 0, 0);
      canvas.toBlob(blob => {if (blob) setFrame({blob, url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height});}, 'image/png');
    };
    video.onerror = () => setError(tr('Could not read the guide video.', 'Não foi possível ler o vídeo guia.', 'No se pudo leer el vídeo guía.'));
    return () => {video.removeAttribute('src'); video.load();};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl, start]);
  useEffect(() => () => {if (frame) URL.revokeObjectURL(frame.url);}, [frame]);
  useEffect(() => () => {if (result) URL.revokeObjectURL(result.url);}, [result]);

  async function edit() {
    if (!frame || !instruction.trim()) return;
    setBusy(true); setError('');
    try {
      const body = new FormData();
      body.set('frame', frame.blob, 'frame.png'); body.set('instruction', instruction.trim());
      if (useRefs) pictures.forEach(p => body.append(`picture_${String(p.slot).padStart(2, '0')}`, p.file, p.file.name));
      const response = await fetch('/api/backend/frame-edit', {method: 'POST', body});
      if (!response.ok) {const reply = await response.json().catch(() => ({})); throw Error(reply.detail || reply.error || `HTTP ${response.status}`);}
      const blob = await response.blob();
      setResult({blob, url: URL.createObjectURL(blob)});
    } catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
  }
  async function use() {
    if (!frame || !result) return;
    // Cover-crop to the frame's aspect and size: the propagated frame must line up with frame 0 of the guide.
    const image = await load(result.url);
    const canvas = document.createElement('canvas'); canvas.width = frame.width; canvas.height = frame.height;
    const scale = Math.max(frame.width / image.naturalWidth, frame.height / image.naturalHeight);
    const w = image.naturalWidth * scale, h = image.naturalHeight * scale;
    canvas.getContext('2d')?.drawImage(image, (frame.width - w) / 2, (frame.height - h) / 2, w, h);
    canvas.toBlob(blob => {if (blob) onUse(new File([blob], 'first_frame.png', {type: 'image/png'}));}, 'image/png');
  }

  return <dialog ref={dialog} className="trim-modal first-frame-modal" aria-labelledby="first-frame-heading" onCancel={e => {e.preventDefault(); onClose();}}>
    <header className="trim-header"><div><span className="eyebrow">{tr('FIRST FRAME', 'PRIMEIRO QUADRO', 'PRIMER FOTOGRAMA')}</span><h2 id="first-frame-heading">{tr('Edit the start, propagate it', 'Edite o início e propague', 'Edita el inicio y propágalo')}</h2>
      <p>{tr('The edited frame becomes a picture of the edit. Use the "First-frame propagate" model in Motion Transfer.', 'O quadro editado vira uma Picture da edição. Use o modelo "First-frame propagate" no Motion Transfer.', 'El fotograma editado se convierte en una imagen de la edición. Usa el modelo "First-frame propagate" en Motion Transfer.')}</p></div>
      <button type="button" className="trim-close" aria-label={tr('Close', 'Fechar', 'Cerrar')} onClick={onClose}>×</button></header>
    <div className="first-frame-panes">
      <figure><figcaption className="eyebrow muted">{tr('Guide frame', 'Quadro do guia', 'Fotograma de la guía')}{frame ? ` · ${frame.width}×${frame.height}` : ''}</figcaption>{frame ? <img src={frame.url} alt=""/> : <div className="first-frame-empty">{tr('Reading the frame…', 'Lendo o quadro…', 'Leyendo el fotograma…')}</div>}</figure>
      <figure><figcaption className="eyebrow muted">{tr('Edited', 'Editado', 'Editado')}</figcaption>{result ? <img src={result.url} alt=""/> : <div className="first-frame-empty">{busy ? tr('FIBO is editing… (about 1–3 min)', 'O FIBO está editando… (cerca de 1–3 min)', 'FIBO está editando… (unos 1–3 min)') : tr('Edit with FIBO or upload an image', 'Edite com FIBO ou envie uma imagem', 'Edita con FIBO o sube una imagen')}</div>}</figure>
    </div>
    <div className="first-frame-controls">
      {fiboReady ? <>
        <label>{tr('What should change in this frame?', 'O que deve mudar neste quadro?', '¿Qué debe cambiar en este fotograma?')}<textarea value={instruction} onChange={e => setInstruction(e.target.value)} placeholder={tr('Set his hands on fire', 'Coloque fogo nas mãos dele', 'Pon fuego en sus manos')}/></label>
        {pictures.length > 0 && <label className="prompt-assist-row"><input type="checkbox" checked={useRefs} onChange={e => setUseRefs(e.target.checked)}/><span><strong>{tr('Send my pictures to FIBO as references', 'Enviar minhas Pictures ao FIBO como referência', 'Enviar mis imágenes a FIBO como referencia')}</strong></span></label>}
      </> : <small className="muted">{tr('FIBO is not installed on this ComfyUI; upload an edited frame instead.', 'O FIBO não está instalado neste ComfyUI; envie um quadro já editado.', 'FIBO no está instalado en este ComfyUI; sube un fotograma editado.')}</small>}
      {error && <p className="validation" role="alert">{error}</p>}
      <input hidden ref={upload} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => {const file = e.target.files?.[0]; if (file) setResult({blob: file, url: URL.createObjectURL(file)}); e.target.value = '';}}/>
      <div className="modal-actions">
        <button className="quiet-button" disabled={!frame} onClick={() => upload.current?.click()}>{tr('Upload edited image', 'Enviar imagem editada', 'Subir imagen editada')}</button>
        {fiboReady && <button className="quiet-button" disabled={!frame || !instruction.trim() || busy} onClick={edit}>{busy ? tr('Editing…', 'Editando…', 'Editando…') : tr('Edit with FIBO', 'Editar com FIBO', 'Editar con FIBO')}</button>}
        <button className="primary" disabled={!frame || !result || busy} onClick={use}>{tr('Use as first frame', 'Usar como primeiro quadro', 'Usar como primer fotograma')}</button>
      </div>
    </div>
  </dialog>;
}
