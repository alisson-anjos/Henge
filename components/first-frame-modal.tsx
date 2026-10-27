'use client';
import {useEffect, useRef, useState} from 'react';
import type {Language} from '../lib/design-copy';
import type {Picture} from '../lib/media';

type Image = {blob: Blob; url: string};
const load = (src: string) => new Promise<HTMLImageElement>((resolve, reject) => {const image = new window.Image(); image.onload = () => resolve(image); image.onerror = reject; image.src = src;});
type Edit = {id: string; created: number; instruction: string; url: string};

/** Cover-crop an image to exactly width x height: a propagated first frame must line up with frame 0 of the guide. */
export async function coverFit(src: string, width: number, height: number): Promise<File> {
  const image = await load(src);
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
  const scale = Math.max(width / image.naturalWidth, height / image.naturalHeight);
  const w = image.naturalWidth * scale, h = image.naturalHeight * scale;
  canvas.getContext('2d')?.drawImage(image, (width - w) / 2, (height - h) / 2, w, h);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(new File([blob], 'first_frame.png', {type: 'image/png'})) : reject(Error('Could not encode the frame')), 'image/png'));
}

/** The guide's first selected frame, edited with FLUX.2 [klein] (or FIBO 2) or replaced by an uploaded image. Paint a
 * mask to edit only that area; Replace, Remove, Add or a free instruction. The result is cropped and resized to the frame's
 * exact size so it can be propagated (Motion Transfer · first-frame propagate). */
export default function FirstFrameModal({videoUrl, start, image, pictures, lang, onUse, onClose}: {videoUrl?: string; start?: number; image?: File; pictures: Picture[]; lang: Language; onUse: (file: File, edit: {id: string; width: number; height: number} | null) => void; onClose: () => void}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const dialog = useRef<HTMLDialogElement>(null), upload = useRef<HTMLInputElement>(null);
  const [frame, setFrame] = useState<Image & {width: number; height: number} | null>(null);
  const [result, setResult] = useState<Image & {edit?: string} | null>(null);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [editor, setEditor] = useState<'klein3' | 'klein' | 'fibo' | null>(null);
  const editorName = ({klein3: 'FLUX.3 Klein', klein: 'FLUX.2 Klein', fibo: 'FIBO'} as const)[editor ?? 'fibo'];
  const [op, setOp] = useState<'replace' | 'remove' | 'add' | 'free'>('replace');
  const [what, setWhat] = useState('');
  const paint = useRef<HTMLCanvasElement>(null), drawing = useRef(false);
  const [brush, setBrush] = useState(48);
  const [erase, setErase] = useState(false);
  const [painted, setPainted] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [useRefs, setUseRefs] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    dialog.current?.showModal();
    // ComfyUI can take a while to list its nodes (very large models folder): ask again until the editor is known.
    let tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    const ask = () => fetch('/api/backend/health').then(r => r.json()).then(h => {const e = h.frame_editor ?? (h.fibo_ready ? 'fibo' : null); setEditor(e); if (!e && ++tries < 12) timer = setTimeout(ask, 10000);}).catch(() => {});
    ask();
    fetch('/api/backend/frame-edits').then(r => r.json()).then(rows => {if (Array.isArray(rows)) setEdits(rows);}).catch(() => {});
    if (image) {
      // A reference picture: edit it at its own size.
      load(URL.createObjectURL(image)).then(im => setFrame({blob: image, url: URL.createObjectURL(image), width: im.naturalWidth, height: im.naturalHeight})).catch(() => setError(tr('Could not read the picture.', 'Não foi possível ler a imagem.', 'No se pudo leer la imagen.')));
      return () => clearTimeout(timer);
    }
    const video = document.createElement('video');
    video.muted = true; video.preload = 'auto'; video.src = videoUrl ?? '';
    video.onloadedmetadata = () => {video.currentTime = Math.min((start ?? 0) + .001, Math.max(0, video.duration - .05));};
    video.onseeked = () => {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth; canvas.height = video.videoHeight;
      canvas.getContext('2d')?.drawImage(video, 0, 0);
      canvas.toBlob(blob => {if (blob) setFrame({blob, url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height});}, 'image/png');
    };
    video.onerror = () => setError(tr('Could not read the guide video.', 'Não foi possível ler o vídeo guia.', 'No se pudo leer el vídeo guía.'));
    return () => {clearTimeout(timer); video.removeAttribute('src'); video.load();};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl, start, image]);
  useEffect(() => () => {if (frame) URL.revokeObjectURL(frame.url);}, [frame]);
  useEffect(() => () => {if (result) URL.revokeObjectURL(result.url);}, [result]);

  async function edit() {
    if (!frame || !ready) return;
    setBusy(true); setError('');
    try {
      const body = new FormData();
      body.set('frame', frame.blob, 'frame.png'); body.set('instruction', instruction.trim()); body.set('op', op); body.set('what', what.trim());
      if (painted && paint.current) {const mask = await new Promise<Blob | null>(r => paint.current!.toBlob(r, 'image/png')); if (mask) body.set('mask', mask, 'mask.png');}
      if (useRefs) pictures.forEach(p => body.append(`picture_${String(p.slot).padStart(2, '0')}`, p.file, p.file.name));
      const response = await fetch('/api/backend/frame-edit', {method: 'POST', body});
      if (!response.ok) {const reply = await response.json().catch(() => ({})); throw Error(reply.detail || reply.error || `HTTP ${response.status}`);}
      const blob = await response.blob(), edit = response.headers.get('x-henge-edit') || undefined;
      setResult({blob, url: URL.createObjectURL(blob), edit});
      if (edit) setEdits(current => [{id: edit, created: Date.now() / 1000, instruction: instruction.trim() || what.trim(), url: `/api/backend/frame-edits/${edit}`}, ...current]);
    } catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
  }
  async function pick(edit: Edit) {
    try {const blob = await (await fetch(edit.url)).blob(); setResult({blob, url: URL.createObjectURL(blob), edit: edit.id}); setInstruction(edit.instruction);}
    catch {setError(tr('Could not load that edit.', 'Não foi possível carregar essa edição.', 'No se pudo cargar esa edición.'));}
  }
  async function use() {
    if (!frame || !result) return;
    onUse(await coverFit(result.url, frame.width, frame.height), result.edit ? {id: result.edit, width: frame.width, height: frame.height} : null);
  }

  // The painted mask: white where the edit may change the frame; drawn at the frame's own resolution.
  useEffect(() => {const c = paint.current; if (c && frame) {c.width = frame.width; c.height = frame.height; setPainted(false);}}, [frame]);
  function stroke(e: React.PointerEvent<HTMLCanvasElement>) {
    const c = paint.current; if (!c || !drawing.current) return;
    const r = c.getBoundingClientRect(), x = (e.clientX - r.left) * c.width / r.width, y = (e.clientY - r.top) * c.height / r.height;
    const g = c.getContext('2d'); if (!g) return;
    g.globalCompositeOperation = erase ? 'destination-out' : 'source-over'; g.fillStyle = 'white';
    g.beginPath(); g.arc(x, y, brush * c.width / r.width / 2, 0, Math.PI * 2); g.fill(); if (!erase) setPainted(true);
  }
  function clearMask() {const c = paint.current; c?.getContext('2d')?.clearRect(0, 0, c.width, c.height); setPainted(false);}
  const ready = op === 'remove' ? !!(what.trim() || painted) : op === 'replace' ? !!((what.trim() || painted) && instruction.trim()) : !!instruction.trim();
  // Both panes take the guide frame's shape (a 16:9 frame no longer sits beside a tall 9:16 box).
  const shape = frame ? {aspectRatio: `${frame.width} / ${frame.height}`, maxWidth: `min(100%, calc(var(--ff-h) * ${(frame.width / frame.height).toFixed(4)}))`} : undefined;
  const ops: [typeof op, string][] = [['replace', tr('Replace', 'Substituir', 'Reemplazar')], ['remove', tr('Remove', 'Remover', 'Quitar')], ['add', tr('Add', 'Adicionar', 'Añadir')], ['free', tr('Describe', 'Descrever', 'Describir')]];

  return <dialog ref={dialog} className={`trim-modal first-frame-modal${frame && frame.width > frame.height ? ' landscape' : ''}`} aria-labelledby="first-frame-heading" onCancel={e => {e.preventDefault(); onClose();}}>
    <header className="trim-header"><div><span className="eyebrow">{image ? tr('PICTURE', 'IMAGEM', 'IMAGEN') : tr('FIRST FRAME', 'PRIMEIRO QUADRO', 'PRIMER FOTOGRAMA')}</span><h2 id="first-frame-heading">{image ? tr('Edit this picture', 'Edite esta imagem', 'Edita esta imagen') : tr('Edit the start, propagate it', 'Edite o início e propague', 'Edita el inicio y propágalo')}</h2>
      <p>{image ? tr('Replace, remove or add something, or paint the area to change; the result replaces the picture.', 'Substitua, remova ou adicione algo, ou pinte a área a mudar; o resultado substitui a imagem.', 'Reemplaza, quita o añade algo, o pinta el área a cambiar; el resultado sustituye la imagen.') : tr('The edited frame becomes a picture of the edit. Use the "First-frame propagate" model in Motion Transfer.', 'O quadro editado vira uma Picture da edição. Use o modelo "First-frame propagate" no Motion Transfer.', 'El fotograma editado se convierte en una imagen de la edición. Usa el modelo "First-frame propagate" en Motion Transfer.')}</p></div>
      <button type="button" className="trim-close" aria-label={tr('Close', 'Fechar', 'Cerrar')} onClick={onClose}>×</button></header>
    <div className="first-frame-body">
    <div className="first-frame-panes">
      <figure><figcaption className="eyebrow muted">{image ? tr('Picture', 'Imagem', 'Imagen') : tr('Guide frame', 'Quadro do guia', 'Fotograma de la guía')}{frame ? ` · ${frame.width}×${frame.height}` : ''}</figcaption>{frame ? <div className="first-frame-paint" style={shape}><img src={frame.url} alt=""/>{editor && <canvas ref={paint} aria-label={tr('Paint the area to edit', 'Pinte a área a editar', 'Pinta el área a editar')} onPointerDown={e => {drawing.current = true; e.currentTarget.setPointerCapture(e.pointerId); stroke(e);}} onPointerMove={stroke} onPointerUp={() => {drawing.current = false;}}/>}</div> : <div className="first-frame-empty">{tr('Reading the frame…', 'Lendo o quadro…', 'Leyendo el fotograma…')}</div>}</figure>
      <figure><figcaption className="eyebrow muted">{tr('Edited', 'Editado', 'Editado')}</figcaption>{result ? <img src={result.url} alt="" style={shape}/> : <div className="first-frame-empty" style={shape}>{busy ? tr(`${editorName} is editing… (about 1 min)`, `${editorName} está editando… (cerca de 1 min)`, `${editorName} está editando… (alrededor de 1 min)`) : editor ? tr(`Edit with ${editorName} or upload an image`, `Edite com ${editorName} ou envie uma imagem`, `Edita con ${editorName} o sube una imagen`) : tr('Upload an edited image', 'Envie uma imagem editada', 'Sube una imagen editada')}</div>}</figure>
    </div>
    <div className="first-frame-controls">
      {editor ? <>
        <div className="edit-ops" role="group" aria-label={tr('Edit', 'Edição', 'Edición')}>{ops.map(([k, label]) => <button key={k} type="button" aria-pressed={op === k} className={op === k ? 'chosen' : ''} onClick={() => setOp(k)}>{label}</button>)}</div>
        <div className="paint-tools"><span className="muted">{tr('Paint over the frame to edit only that area (optional).', 'Pinte sobre o quadro para editar só essa área (opcional).', 'Pinta sobre el fotograma para editar solo esa área (opcional).')}</span>
          <label>{tr('Brush', 'Pincel', 'Pincel')}<input type="range" min="8" max="160" value={brush} onChange={e => setBrush(Number(e.target.value))}/></label>
          <button type="button" className="quiet-button" aria-pressed={erase} onClick={() => setErase(v => !v)}>{erase ? tr('Eraser on', 'Borracha ligada', 'Borrador activo') : tr('Eraser', 'Borracha', 'Borrador')}</button>
          <button type="button" className="quiet-button" disabled={!painted} onClick={clearMask}>{tr('Clear', 'Limpar', 'Borrar')}</button></div>
        {(op === 'replace' || op === 'remove') && <label>{op === 'remove' ? tr('What should go away?', 'O que deve sumir?', '¿Qué debe desaparecer?') : tr('What do you replace?', 'O que você vai substituir?', '¿Qué reemplazas?')}<input value={what} onChange={e => setWhat(e.target.value)} placeholder={tr('the black hoodie', 'o moletom preto', 'la sudadera negra')}/></label>}
        {op !== 'remove' && <label>{op === 'replace' ? tr('With what?', 'Pelo quê?', '¿Por qué?') : op === 'add' ? tr('What do you add, and where?', 'O que adicionar, e onde?', '¿Qué añades y dónde?') : tr('What should change in this frame?', 'O que deve mudar neste quadro?', '¿Qué debe cambiar en este fotograma?')}<textarea value={instruction} onChange={e => setInstruction(e.target.value)} placeholder={op === 'add' ? tr('a small dragon on his shoulder', 'um pequeno dragão no ombro dele', 'un pequeño dragón en su hombro') : op === 'replace' ? tr('a red leather jacket', 'uma jaqueta de couro vermelha', 'una chaqueta de cuero roja') : tr('Set his hands on fire', 'Coloque fogo nas mãos dele', 'Pon fuego en sus manos')}/></label>}
        {pictures.length > 0 && <label className="prompt-assist-row"><input type="checkbox" checked={useRefs} onChange={e => setUseRefs(e.target.checked)}/><span><strong>{tr(`Send my pictures to ${editorName} as references`, `Enviar minhas Pictures ao ${editorName} como referência`, `Enviar mis imágenes a ${editorName} como referencia`)}</strong></span></label>}
      </> : <small className="muted">{tr('No image editor (FLUX.2 Klein or FIBO) is installed on this ComfyUI; upload an edited frame instead.', 'Nenhum editor de imagem (FLUX.2 Klein ou FIBO) está instalado neste ComfyUI; envie um quadro já editado.', 'No hay editor de imagen (FLUX.2 Klein o FIBO) en este ComfyUI; sube un fotograma editado.')}</small>}
      {edits.length > 0 && <div className="recent-edits"><span className="eyebrow muted">{tr('Recent edits', 'Edições recentes', 'Ediciones recientes')}</span><div>{edits.map(e => <button key={e.id} title={e.instruction} aria-pressed={result?.edit === e.id} onClick={() => pick(e)}><img src={e.url} alt={e.instruction} loading="lazy"/></button>)}</div></div>}
      {error && <p className="validation" role="alert">{error}</p>}
    </div>
    </div>
      <input hidden ref={upload} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => {const file = e.target.files?.[0]; if (file) setResult({blob: file, url: URL.createObjectURL(file)}); e.target.value = '';}}/>
    <div className="modal-actions first-frame-footer">
        <button className="quiet-button" disabled={!frame} onClick={() => upload.current?.click()}>{tr('Upload edited image', 'Enviar imagem editada', 'Subir imagen editada')}</button>
        {editor && <button className="quiet-button" disabled={!frame || !ready || busy} onClick={edit}>{busy ? tr('Editing…', 'Editando…', 'Editando…') : tr(`Edit with ${editorName}`, `Editar com ${editorName}`, `Editar con ${editorName}`)}</button>}
        <button className="primary" disabled={!frame || !result || busy} onClick={use}>{image ? tr('Use this picture', 'Usar esta imagem', 'Usar esta imagen') : tr('Use as first frame', 'Usar como primeiro quadro', 'Usar como primer fotograma')}</button>
    </div>
  </dialog>;
}
