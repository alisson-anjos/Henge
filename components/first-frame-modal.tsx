'use client';
import {frameEditorName} from '../lib/frame-editor';
import {useEffect, useRef, useState} from 'react';
import type {Language} from '../lib/design-copy';
import type {Picture} from '../lib/media';
import {paintMagenta, segmentFrame, segmentMask, type Segments} from '../lib/segments';

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

/** The guide's first selected frame, edited with FLUX.3 / FLUX.2 [klein] or replaced by an uploaded image. Paint a
 * mask to edit only that area; Replace, Remove, Add or a free instruction. The result is cropped and resized to the frame's
 * exact size so it can be propagated (Motion Transfer · first-frame propagate). `swap` (Character Swap) opens the Swap
 * character edit instead: the performer in the frame becomes the chosen character Picture, keeping pose and scene. */
export default function FirstFrameModal({videoUrl, start, end, image, edited, pictures, swap = false, lang, onUse, onClose}: {videoUrl?: string; start?: number; end?: number; image?: File; edited?: File; pictures: Picture[]; swap?: boolean; lang: Language; onUse: (file: File, edit: {id: string; width: number; height: number} | null, at?: number) => void; onClose: () => void}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const dialog = useRef<HTMLDialogElement>(null), upload = useRef<HTMLInputElement>(null);
  const [frame, setFrame] = useState<Image & {width: number; height: number} | null>(null);
  const [result, setResult] = useState<Image & {edit?: string} | null>(null);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [editor, setEditor] = useState<string | null>(null);
  // Editors this ComfyUI can run, in the order the backend prefers them. The modal lets you pick one per edit.
  const [editors, setEditors] = useState<string[]>([]);
  const editorName = frameEditorName(editor, tr('Image editor', 'Editor de imagem', 'Editor de imagen'));
  const [op, setOp] = useState<'swap' | 'replace' | 'remove' | 'add' | 'free'>(swap ? 'swap' : 'replace');
  const [what, setWhat] = useState('');
  const paint = useRef<HTMLCanvasElement>(null), drawing = useRef(false);
  const [brush, setBrush] = useState(48);
  const [erase, setErase] = useState(false);
  const [painted, setPainted] = useState(false);
  const [instruction, setInstruction] = useState('');
  // References for the edit (every editor reads several images): any of the studio's Pictures, plus images uploaded only for
  // this edit. They reach the editor as image 2, image 3... in this order.
  const [refSlots, setRefSlots] = useState<number[]>(swap && pictures.length ? [pictures[0].slot] : []);
  const [extraRefs, setExtraRefs] = useState<{file: File; url: string}[]>([]);
  const refUpload = useRef<HTMLInputElement>(null);
  const editRefs = [...pictures.filter(p => refSlots.includes(p.slot)).map(p => ({key: `p${p.slot}`, file: p.file, url: p.url, label: `Picture ${p.slot}`})),
    ...extraRefs.map((r, i) => ({key: `x${i}`, file: r.file, url: r.url, label: r.file.name}))].slice(0, 12);
  const [busy, setBusy] = useState(false);
  // The prompt name of a chosen reference: image 1 is the frame, references follow as image 2, image 3...
  const imageNumber = (key: string) => {const i = editRefs.findIndex(r => r.key === key); return i < 0 ? 0 : i + 2;};
  // Swap character: SAM 3.1 segments the characters of the chosen frame (button, run again after changing frames);
  // hover highlights one, click marks it magenta, and that marked frame goes to the editor.
  const [segments, setSegments] = useState<Segments | null>(null);
  const [segmenting, setSegmenting] = useState(false);
  const [hover, setHover] = useState(0);
  const [picked, setPicked] = useState(0);
  const pickCanvas = useRef<HTMLCanvasElement>(null);
  // The English prompt the editor gets. It follows the choices above (built by the bridge) until the user edits it.
  const [editPrompt, setEditPrompt] = useState('');
  const [promptEdited, setPromptEdited] = useState(false);
  const [error, setError] = useState('');
  // Which guide frame to edit: the start by default; any frame of the interval can be chosen.
  const [at, setAt] = useState(start ?? 0);
  const player = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    dialog.current?.showModal();
    // ComfyUI can take a while to list its nodes (very large models folder): ask again until the editor is known.
    let tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    const ask = () => fetch('/api/backend/health').then(r => r.json()).then(h => {
      const ready = (Array.isArray(h.frame_editors) ? h.frame_editors : []).filter((e: {installed?: boolean}) => e && e.installed).map((e: {id: string}) => String(e.id));
      const chosen = typeof h.frame_editor === 'string' ? h.frame_editor : null;
      // Character Swap prefers BFS Body Swap (trained for person swaps) when this ComfyUI has it.
      setEditors(ready); setEditor(swap && ready.includes('bfs') ? 'bfs' : chosen || ready[0] || null);
      if (!chosen && !ready.length && ++tries < 12) timer = setTimeout(ask, 10000);
    }).catch(() => {});
    ask();
    fetch('/api/backend/frame-edits').then(r => r.json()).then(rows => {if (Array.isArray(rows)) setEdits(rows);}).catch(() => {});
    if (image) {
      // A reference picture: edit it at its own size.
      load(URL.createObjectURL(image)).then(im => setFrame({blob: image, url: URL.createObjectURL(image), width: im.naturalWidth, height: im.naturalHeight})).catch(() => setError(tr('Could not read the picture.', 'Não foi possível ler a imagem.', 'No se pudo leer la imagen.')));
      return () => clearTimeout(timer);
    }
    const video = document.createElement('video'); player.current = video;
    video.muted = true; video.preload = 'auto'; video.src = videoUrl ?? '';
    video.onloadedmetadata = () => {video.currentTime = Math.min((start ?? 0) + .001, Math.max(0, video.duration - .05));};
    // Reopened with an edited first frame: start from that edit (to keep editing it, e.g. swap a second character);
    // picking another time on the slider goes back to the guide's own frames.
    let reopen = !!edited;
    video.onseeked = () => {
      if (reopen && edited) {
        reopen = false;
        load(URL.createObjectURL(edited)).then(im => setFrame({blob: edited, url: im.src, width: im.naturalWidth, height: im.naturalHeight})).catch(() => setError(tr('Could not read the edited frame.', 'Não foi possível ler o quadro editado.', 'No se pudo leer el fotograma editado.')));
        return;
      }
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth; canvas.height = video.videoHeight;
      canvas.getContext('2d')?.drawImage(video, 0, 0);
      canvas.toBlob(blob => {if (blob) setFrame({blob, url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height});}, 'image/png');
    };
    video.onerror = () => setError(tr('Could not read the guide video.', 'Não foi possível ler o vídeo guia.', 'No se pudo leer el vídeo guía.'));
    return () => {clearTimeout(timer); video.removeAttribute('src'); video.load();};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl, start, image, edited]);
  useEffect(() => () => {if (frame) URL.revokeObjectURL(frame.url);}, [frame]);
  // Another frame: its old segments no longer line up, so they are dropped until Segment runs again.
  useEffect(() => {setSegments(null); setHover(0); setPicked(0);}, [frame]);
  async function segment() {
    if (!frame) return;
    setSegmenting(true); setError('');
    try {
      const found = await segmentFrame(frame.blob); const count = found.count;
      setSegments(found); setPicked(0); setHover(0);
      if (!count) setError(tr('No character found in this frame; try another frame, or describe or paint who to replace.', 'Nenhum personagem encontrado neste quadro; tente outro quadro, ou descreva ou pinte quem trocar.', 'No se encontró ningún personaje en este fotograma; prueba otro, o describe o pinta a quién reemplazar.'));
    } catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setSegmenting(false);}
  }
  const labelAt = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!segments) return 0;
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left) * segments.width / r.width), y = Math.floor((e.clientY - r.top) * segments.height / r.height);
    return x < 0 || y < 0 || x >= segments.width || y >= segments.height ? 0 : segments.labels[y * segments.width + x];
  };
  // Draw the hovered segment light and the picked one magenta, at the label map's resolution.
  useEffect(() => {
    const c = pickCanvas.current; if (!c || !segments) return;
    c.width = segments.width; c.height = segments.height;
    const g = c.getContext('2d'); if (!g) return;
    const img = g.createImageData(c.width, c.height), d = img.data;
    for (let i = 0; i < segments.labels.length; i++) {
      const n = segments.labels[i]; if (!n) continue;
      if (n === picked) {d[i * 4] = 255; d[i * 4 + 1] = 0; d[i * 4 + 2] = 255; d[i * 4 + 3] = 150;}
      else if (n === hover) {d[i * 4] = 255; d[i * 4 + 1] = 255; d[i * 4 + 2] = 255; d[i * 4 + 3] = 90;}
      else {d[i * 4] = 255; d[i * 4 + 1] = 255; d[i * 4 + 2] = 255; d[i * 4 + 3] = 22;}
    }
    g.putImageData(img, 0, 0);
  }, [segments, hover, picked]);
  /** The frame with the picked character painted magenta (60 %, so its outline and pose stay readable). */
  async function markedFrame(): Promise<Blob> {
    if (!frame || !segments || !picked) return frame!.blob;
    return paintMagenta(frame.url, segments, picked);
  }
  useEffect(() => () => {if (result) URL.revokeObjectURL(result.url);}, [result]);

  const markedPick = op === 'swap' && !!segments && picked > 0;
  // BFS only swaps people: another edit moves to the next editor.
  useEffect(() => {if (op !== 'swap' && editor === 'bfs') setEditor(editors.find(id => id !== 'bfs') || null);}, [op, editor, editors]);
  useEffect(() => {
    if (promptEdited) return;
    const query = new URLSearchParams({op, what: what.trim(), instruction: instruction.trim(), refs: String(editRefs.length), marked: String(markedPick && editor !== 'bfs'), editor: editor || ''});
    const timer = setTimeout(() => fetch(`/api/backend/frame-edit/instruction?${query}`).then(r => r.ok ? r.json() : null).then(reply => {if (reply && typeof reply.instruction === 'string') setEditPrompt(reply.instruction);}).catch(() => {}), 250);
    return () => clearTimeout(timer);
  }, [op, what, instruction, editRefs.length, markedPick, promptEdited, editor]);
  async function edit() {
    if (!frame || !ready) return;
    setBusy(true); setError('');
    try {
      const body = new FormData();
      // BFS reads the clicked person from a crop around their mask; the other editors get them painted magenta.
      const bfs = editor === 'bfs';
      const marked = op === 'swap' && !!segments && picked > 0 && !bfs;
      body.set('frame', marked ? await markedFrame() : frame.blob, 'frame.png');
      if (bfs && op === 'swap' && segments && picked > 0) body.set('mask', await segmentMask(segments, picked, frame.width, frame.height), 'mask.png'); body.set('instruction', instruction.trim()); body.set('op', op); body.set('what', what.trim());
      if (marked) body.set('marked', '1');
      if (promptEdited && editPrompt.trim()) body.set('prompt', editPrompt.trim());
      if (editor) body.set('editor', editor);
      if (op !== 'swap' && painted && paint.current) {const mask = await exportMask(); if (mask) body.set('mask', mask, 'mask.png');}
      editRefs.forEach((r, i) => body.append(`picture_${String(i + 1).padStart(2, '0')}`, r.file, r.file.name));
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
  // Clearing the generation history keeps frame edits (they can be reused later), so the modal needs its own Clear:
  // it deletes the stored edits and the space they take on this ComfyUI.
  async function clearEdits() {
    setError('');
    try {
      const response = await fetch('/api/backend/frame-edits', {method: 'DELETE'});
      if (!response.ok) throw new Error(String(response.status));
      setEdits([]); setResult(current => current ? {...current, edit: undefined} : current);
    } catch { setError(tr('Could not clear the recent edits.', 'Não foi possível limpar as edições recentes.', 'No se pudo limpiar las ediciones recientes.')); }
  }
  async function use() {
    if (!frame || !result) return;
    onUse(await coverFit(result.url, frame.width, frame.height), result.edit ? {id: result.edit, width: frame.width, height: frame.height} : null, image ? undefined : at);
  }
  function chooseFrame(t: number) {
    // Another guide frame: grab it and drop an edit made on the previous one.
    const video = player.current; if (!video) return;
    setAt(t); setResult(null); video.currentTime = Math.min(t + .001, Math.max(0, video.duration - .05));
  }

  // The painted mask: white where the edit may change the frame; drawn at the frame's own resolution.
  useEffect(() => {const c = paint.current; if (c && frame) {c.width = frame.width; c.height = frame.height; setPainted(false);}}, [frame]);
  // The brush is round on screen: the canvas can be shown squeezed (the pane caps its height), so its radius is scaled
  // per axis. Dabs are stamped along the path so a fast stroke leaves no gaps. Painted magenta; the mask sent to the
  // bridge is white (exportMask).
  const lastDab = useRef<{x: number; y: number} | null>(null);
  function stroke(e: React.PointerEvent<HTMLCanvasElement>) {
    const c = paint.current; if (!c || !drawing.current) return;
    const r = c.getBoundingClientRect(), sx = c.width / r.width, sy = c.height / r.height;
    const x = (e.clientX - r.left) * sx, y = (e.clientY - r.top) * sy, rx = brush * sx / 2, ry = brush * sy / 2;
    const g = c.getContext('2d'); if (!g) return;
    g.globalCompositeOperation = erase ? 'destination-out' : 'source-over'; g.fillStyle = '#ff00ff';
    const from = lastDab.current ?? {x, y}, steps = Math.max(1, Math.ceil(Math.hypot((x - from.x) / rx, (y - from.y) / ry) * 3));
    for (let k = 1; k <= steps; k++) {const t = k / steps; g.beginPath(); g.ellipse(from.x + (x - from.x) * t, from.y + (y - from.y) * t, rx, ry, 0, 0, Math.PI * 2); g.fill();}
    lastDab.current = {x, y}; if (!erase) setPainted(true);
  }
  /** The painted area as the bridge reads it: white where painted, transparent elsewhere. */
  async function exportMask(): Promise<Blob | null> {
    const c = paint.current; if (!c) return null;
    const out = document.createElement('canvas'); out.width = c.width; out.height = c.height;
    const g = out.getContext('2d'), src = c.getContext('2d'); if (!g || !src) return null;
    const data = src.getImageData(0, 0, c.width, c.height), d = data.data;
    for (let i = 0; i < d.length; i += 4) {const a = d[i + 3]; d[i] = d[i + 1] = d[i + 2] = a ? 255 : 0;}
    g.putImageData(data, 0, 0);
    return new Promise(resolve => out.toBlob(resolve, 'image/png'));
  }
  function clearMask() {const c = paint.current; c?.getContext('2d')?.clearRect(0, 0, c.width, c.height); setPainted(false);}
  const ready = promptEdited && !!editPrompt.trim() ? true : op === 'swap' ? editRefs.length > 0 || !!instruction.trim() : op === 'remove' ? !!(what.trim() || painted) : op === 'replace' ? !!((what.trim() || painted) && instruction.trim()) : !!instruction.trim();
  // Why the edit button is still off: a disabled button with no reason looks stuck.
  const missing = ready ? '' : op === 'swap' ? tr('Choose the character picture, or describe the character.', 'Escolha a imagem do personagem, ou descreva o personagem.', 'Elige la imagen del personaje, o describe al personaje.') : op === 'remove' ? tr('Say what should go away, or paint it.', 'Diga o que deve sumir, ou pinte a área.', 'Di qué debe desaparecer, o píntalo.')
    : op === 'replace' && !(what.trim() || painted) ? tr('Say what you replace (or paint it) and with what.', 'Diga o que vai substituir (ou pinte a área) e pelo quê.', 'Di qué reemplazas (o píntalo) y por qué.')
    : op === 'replace' ? tr('Say what to replace it with.', 'Diga pelo que substituir.', 'Di por qué reemplazarlo.')
    : op === 'add' ? tr('Say what to add, and where.', 'Diga o que adicionar, e onde.', 'Di qué añadir y dónde.') : tr('Describe the change.', 'Descreva a mudança.', 'Describe el cambio.');
  // Both panes take the guide frame's shape (a 16:9 frame no longer sits beside a tall 9:16 box).
  const shape = frame ? {aspectRatio: `${frame.width} / ${frame.height}`, maxWidth: `min(100%, calc(var(--ff-h) * ${(frame.width / frame.height).toFixed(4)}))`} : undefined;
  // Character Swap: swapping the performer is the edit; a free instruction stays for anything else.
  const ops: [typeof op, string][] = swap ? [['swap', tr('Swap character', 'Trocar personagem', 'Cambiar personaje')], ['free', tr('Describe', 'Descrever', 'Describir')]] : [['replace', tr('Replace', 'Substituir', 'Reemplazar')], ['remove', tr('Remove', 'Remover', 'Quitar')], ['add', tr('Add', 'Adicionar', 'Añadir')], ['free', tr('Describe', 'Descrever', 'Describir')]];

  return <dialog ref={dialog} className={`trim-modal first-frame-modal${frame && frame.width > frame.height ? ' landscape' : ''}`} aria-labelledby="first-frame-heading" onCancel={e => {e.preventDefault(); onClose();}}>
    <header className="trim-header"><div><span className="eyebrow">{image ? tr('PICTURE', 'IMAGEM', 'IMAGEN') : tr('FRAME', 'QUADRO', 'FOTOGRAMA')}</span><h2 id="first-frame-heading">{image ? tr('Edit this picture', 'Edite esta imagem', 'Edita esta imagen') : swap ? tr('Swap the character into a frame', 'Coloque o personagem em um quadro', 'Pon al personaje en un fotograma') : tr('Edit a frame, propagate it', 'Edite um quadro e propague', 'Edita un fotograma y propágalo')}</h2>
      <p>{!image && swap ? tr('Segment, click who to replace, edit. The result becomes the first frame of the swap.', 'Segmente, clique em quem trocar e edite. O resultado vira o primeiro quadro do swap.', 'Segmenta, haz clic en quién reemplazar y edita. El resultado será el primer fotograma del swap.') : image ? tr('Replace, remove or add something, or paint the area to change; the result replaces the picture.', 'Substitua, remova ou adicione algo, ou pinte a área a mudar; o resultado substitui a imagem.', 'Reemplaza, quita o añade algo, o pinta el área a cambiar; el resultado sustituye la imagen.') : tr('The edited frame becomes a picture of the edit. Use the "First-frame propagate" model in Motion Transfer.', 'O quadro editado vira uma Picture da edição. Use o modelo "First-frame propagate" no Motion Transfer.', 'El fotograma editado se convierte en una imagen de la edición. Usa el modelo "First-frame propagate" en Motion Transfer.')}</p></div>
      <button type="button" className="trim-close" aria-label={tr('Close', 'Fechar', 'Cerrar')} onClick={onClose}>×</button></header>
    <div className="first-frame-body">
    <div className="first-frame-panes">
      <figure><figcaption className="eyebrow muted">{image ? tr('Picture', 'Imagem', 'Imagen') : tr('Guide frame', 'Quadro do guia', 'Fotograma de la guía')}{frame ? ` · ${frame.width}×${frame.height}` : ''}</figcaption>{frame ? <div className="first-frame-paint" style={shape}><img src={frame.url} alt=""/>{editor && op === 'swap' && segments && <canvas ref={pickCanvas} className="segment-pick" aria-label={tr('Click the character to replace', 'Clique no personagem a trocar', 'Haz clic en el personaje a reemplazar')} onPointerMove={e => setHover(labelAt(e))} onPointerLeave={() => setHover(0)} onClick={e => {const n = labelAt(e); setPicked(p => n && n !== p ? n : 0);}}/>}{editor && op !== 'swap' && <canvas ref={paint} aria-label={tr('Paint the area to edit', 'Pinte a área a editar', 'Pinta el área a editar')} onPointerDown={e => {drawing.current = true; lastDab.current = null; e.currentTarget.setPointerCapture(e.pointerId); stroke(e);}} onPointerMove={stroke} onPointerUp={() => {drawing.current = false; lastDab.current = null;}}/>}</div> : <div className="first-frame-empty">{tr('Reading the frame…', 'Lendo o quadro…', 'Leyendo el fotograma…')}</div>}</figure>
      <figure><figcaption className="eyebrow muted">{tr('Edited', 'Editado', 'Editado')}</figcaption>{result ? <img src={result.url} alt="" style={shape}/> : <div className="first-frame-empty" style={shape}>{busy ? tr(`${editorName} is editing… (about 1 min)`, `${editorName} está editando… (cerca de 1 min)`, `${editorName} está editando… (alrededor de 1 min)`) : editor ? tr(`Edit with ${editorName} or upload an image`, `Edite com ${editorName} ou envie uma imagem`, `Edita con ${editorName} o sube una imagen`) : tr('Upload an edited image', 'Envie uma imagem editada', 'Sube una imagen editada')}</div>}</figure>
    </div>
    <div className="first-frame-form">
    {!image && end !== undefined && end - (start ?? 0) > .1 && <label className="frame-chooser"><span className="eyebrow muted">{tr('Frame to edit', 'Quadro a editar', 'Fotograma a editar')} <b className="mono">{(at - (start ?? 0)).toFixed(2)} s</b></span>
      <input type="range" min={start ?? 0} max={Math.max(start ?? 0, end - 1 / 24)} step={1 / 24} value={at} onChange={e => chooseFrame(Number(e.target.value))}/>
      <small>{tr('Pick the frame where the subject is clearest. Generation starts at the frame you edit.', 'Escolha o quadro em que o assunto aparece melhor. A geração começa no quadro que você editar.', 'Elige el fotograma donde el sujeto se ve mejor. La generación empieza en el fotograma que edites.')}</small></label>}
    <div className="first-frame-controls">
      {editor ? <>
        {editors.filter(id => id !== 'bfs' || op === 'swap').length > 1 && <div className="edit-editors"><span className="eyebrow muted">{tr('Image editor', 'Editor de imagem', 'Editor de imagen')}</span>
          <div>{editors.filter(id => id !== 'bfs' || op === 'swap').map(id => <button key={id} type="button" aria-pressed={editor === id} className={editor === id ? 'chosen' : ''} onClick={() => setEditor(id)}>{frameEditorName(id, id)}</button>)}</div>
          <small className="muted">{tr('FIBO 2.0 edits the frame it is given, so pose, camera and composition stay; Qwen-Image 2.1 follows instructions best. Both respect the painted area.', 'O FIBO 2.0 edita o quadro que recebe, então pose, câmera e composição continuam; o Qwen-Image 2.1 segue instruções melhor. Os dois respeitam a área pintada.', 'FIBO 2.0 edita el fotograma que recibe, así que pose, cámara y composición se mantienen; Qwen-Image 2.1 sigue mejor las instrucciones. Los dos respetan el área pintada.')}</small></div>}
        <div className="edit-ops" role="group" aria-label={tr('Edit', 'Edição', 'Edición')}>{ops.map(([k, label]) => <button key={k} type="button" aria-pressed={op === k} className={op === k ? 'chosen' : ''} onClick={() => setOp(k)}>{label}</button>)}</div>
        {op !== 'swap' && <div className="paint-tools"><span className="muted">{tr('Paint over the frame to edit only that area (optional).', 'Pinte sobre o quadro para editar só essa área (opcional).', 'Pinta sobre el fotograma para editar solo esa área (opcional).')}</span>
          <label>{tr('Brush', 'Pincel', 'Pincel')}<input type="range" min="8" max="160" value={brush} onChange={e => setBrush(Number(e.target.value))}/></label>
          <button type="button" className="quiet-button" aria-pressed={erase} onClick={() => setErase(v => !v)}>{erase ? tr('Eraser on', 'Borracha ligada', 'Borrador activo') : tr('Eraser', 'Borracha', 'Borrador')}</button>
          <button type="button" className="quiet-button" disabled={!painted} onClick={clearMask}>{tr('Clear', 'Limpar', 'Borrar')}</button></div>}
        {op === 'swap' && <><div className="segment-tools"><button type="button" className="quiet-button" disabled={!frame || segmenting} onClick={segment}>{segmenting ? tr('Segmenting… (SAM 3.1)', 'Segmentando… (SAM 3.1)', 'Segmentando… (SAM 3.1)') : segments ? tr('Segment this frame again', 'Segmentar este quadro de novo', 'Segmentar este fotograma de nuevo') : tr('Segment the characters (SAM 3.1)', 'Segmentar os personagens (SAM 3.1)', 'Segmentar los personajes (SAM 3.1)')}</button>
          <span className="muted">{segments ? (picked ? tr(`Character ${picked} is marked magenta.`, `Personagem ${picked} marcado em magenta.`, `Personaje ${picked} marcado en magenta.`) : tr(`${segments.count} found · hover and click the one to replace.`, `${segments.count} encontrado(s) · passe o mouse e clique em quem trocar.`, `${segments.count} encontrado(s) · pasa el ratón y haz clic en quien reemplazar.`)) : tr('Changed the frame? Segment it again.', 'Mudou o quadro? Segmente de novo.', '¿Cambiaste el fotograma? Segméntalo de nuevo.')}</span></div>
          {!picked && <label>{tr('Who do you replace? (if not picked)', 'Quem você vai trocar? (se não clicou)', '¿A quién reemplazas? (si no hiciste clic)')}<input value={what} onChange={e => setWhat(e.target.value)} placeholder={tr('the man in the red jacket', 'o homem de jaqueta vermelha', 'el hombre de la chaqueta roja')}/></label>}
          <label>{editRefs.length ? tr('Anything else? (optional)', 'Mais alguma coisa? (opcional)', '¿Algo más? (opcional)') : tr('Describe the new character', 'Descreva o novo personagem', 'Describe al nuevo personaje')}<textarea value={instruction} onChange={e => setInstruction(e.target.value)} placeholder={tr('keep the microphone in his hand', 'manter o microfone na mão dele', 'mantener el micrófono en su mano')}/></label></>}
        {(op === 'replace' || op === 'remove') && <label>{op === 'remove' ? tr('What should go away?', 'O que deve sumir?', '¿Qué debe desaparecer?') : tr('What do you replace?', 'O que você vai substituir?', '¿Qué reemplazas?')}<input value={what} onChange={e => setWhat(e.target.value)} placeholder={tr('the black hoodie', 'o moletom preto', 'la sudadera negra')}/></label>}
        {op !== 'remove' && op !== 'swap' && <label>{op === 'replace' ? tr('With what?', 'Pelo quê?', '¿Por qué?') : op === 'add' ? tr('What do you add, and where?', 'O que adicionar, e onde?', '¿Qué añades y dónde?') : tr('What should change in this frame?', 'O que deve mudar neste quadro?', '¿Qué debe cambiar en este fotograma?')}<textarea value={instruction} onChange={e => setInstruction(e.target.value)} placeholder={op === 'add' ? tr('a small dragon on his shoulder', 'um pequeno dragão no ombro dele', 'un pequeño dragón en su hombro') : op === 'replace' ? tr('a red leather jacket', 'uma jaqueta de couro vermelha', 'una chaqueta de cuero roja') : tr('Set his hands on fire', 'Coloque fogo nas mãos dele', 'Pon fuego en sus manos')}/></label>}
        <label className="edit-prompt"><span>{tr('Prompt sent to the editor (English)', 'Prompt enviado ao editor (em inglês)', 'Prompt enviado al editor (en inglés)')}{promptEdited && <button type="button" className="text-link" onClick={() => setPromptEdited(false)}>{tr('Reset to default', 'Voltar ao padrão', 'Volver al predeterminado')}</button>}</span>
          <textarea rows={5} value={editPrompt} onChange={e => {setEditPrompt(e.target.value); setPromptEdited(true);}}/>
          <small className="muted">{promptEdited ? tr('Your wording is sent as is; the fields above no longer change it.', 'O seu texto é enviado como está; os campos acima não mudam mais ele.', 'Tu texto se envía tal cual; los campos de arriba ya no lo cambian.') : tr('Built from the choices above; edit it to write your own.', 'Montado a partir das escolhas acima; edite para escrever o seu.', 'Se arma con las opciones de arriba; edítalo para escribir el tuyo.')}</small></label>
        <div className="edit-refs"><span className="eyebrow muted">{op === 'swap' ? tr('Character picture (image 2 is the character; none = use the description)', 'Imagem do personagem (a image 2 é o personagem; nenhuma = usa a descrição)', 'Imagen del personaje (la image 2 es el personaje; ninguna = usa la descripción)') : tr(`References for ${editorName} (optional)`, `Referências para o ${editorName} (opcional)`, `Referencias para ${editorName} (opcional)`)}</span>
          {/* Each chosen reference shows the name it has in the prompt (image 2, image 3...: image 1 is the frame). */}
          <div className="edit-ref-list">{pictures.map(p => {const n = imageNumber(`p${p.slot}`); return <button type="button" key={p.slot} aria-pressed={refSlots.includes(p.slot)} className={refSlots.includes(p.slot) ? 'chosen' : ''} title={n ? `Picture ${p.slot} = image ${n}` : `Picture ${p.slot}`} onClick={() => setRefSlots(cur => cur.includes(p.slot) ? cur.filter(x => x !== p.slot) : [...cur, p.slot])}><img src={p.url} alt={`Picture ${p.slot}`}/>{n ? <b className="edit-ref-index">image {n}</b> : null}<span>P{p.slot}</span></button>;})}
            {extraRefs.map((r, i) => <div key={r.url} className="edit-ref-chip chosen" title={`${r.file.name} = image ${imageNumber(`x${i}`)}`}><img src={r.url} alt={r.file.name}/><b className="edit-ref-index">image {imageNumber(`x${i}`)}</b>
              <button type="button" className="edit-ref-remove" aria-label={tr('Remove this reference', 'Remover esta referência', 'Quitar esta referencia')} title={tr('Remove this reference', 'Remover esta referência', 'Quitar esta referencia')} onClick={() => setExtraRefs(cur => {URL.revokeObjectURL(r.url); return cur.filter((_, k) => k !== i);})}>×</button></div>)}
            {editRefs.length < 12 && <button type="button" className="edit-ref-add" onClick={() => refUpload.current?.click()}>+<span>{tr('Upload', 'Enviar', 'Subir')}</span></button>}</div>
          {editRefs.length > 0 && <small className="muted">{tr('Mention them in the edit as ', 'Cite-as na edição como ', 'Menciónalas en la edición como ')}{editRefs.map((r, i) => `image ${i + 2} (${r.label})`).join(', ')}{tr(', e.g. "his jacket from image 2".', ', p.ex. "a jaqueta da image 2".', ', p.ej. "su chaqueta de la image 2".')}</small>}
          <input hidden ref={refUpload} type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={e => {const files = Array.from(e.target.files ?? []); setExtraRefs(cur => [...cur, ...files.map(file => ({file, url: URL.createObjectURL(file)}))]); e.target.value = '';}}/></div>
      </> : <small className="muted">{tr('No image editor (FIBO 2.0, Qwen-Image 2.1 or FLUX Klein) is installed on this ComfyUI; upload an edited frame instead.', 'Nenhum editor de imagem (FIBO 2.0, Qwen-Image 2.1 ou FLUX Klein) está instalado neste ComfyUI; envie um quadro já editado.', 'No hay editor de imagen (FIBO 2.0, Qwen-Image 2.1 o FLUX Klein) en este ComfyUI; sube un fotograma editado.')}</small>}
      {edits.length > 0 && <div className="recent-edits"><div className="recent-edits-head"><span className="eyebrow muted">{tr('Recent edits', 'Edições recentes', 'Ediciones recientes')}</span><button type="button" className="text-link" title={tr('Delete the stored frame edits', 'Apague as edições de quadro armazenadas', 'Elimina las ediciones de fotograma guardadas')} onClick={clearEdits}>{tr('Clear', 'Limpar', 'Limpiar')}</button></div><div>{edits.map(e => <button key={e.id} title={e.instruction} aria-pressed={result?.edit === e.id} onClick={() => pick(e)}><img src={e.url} alt={e.instruction} loading="lazy"/></button>)}</div></div>}
      {error && <p className="validation" role="alert">{error}</p>}
    </div>
    </div>
    </div>
      <input hidden ref={upload} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => {const file = e.target.files?.[0]; if (file) setResult({blob: file, url: URL.createObjectURL(file)}); e.target.value = '';}}/>
    <div className="modal-actions first-frame-footer">
        {editor && frame && missing && !busy && <small className="muted first-frame-hint">{missing}</small>}
        <button className="quiet-button" disabled={!frame} onClick={() => upload.current?.click()}>{tr('Upload edited image', 'Enviar imagem editada', 'Subir imagen editada')}</button>
        {editor && <button className="quiet-button" disabled={!frame || !ready || busy} title={missing || undefined} onClick={edit}>{busy ? tr('Editing…', 'Editando…', 'Editando…') : tr(`Edit with ${editorName}`, `Editar com ${editorName}`, `Editar con ${editorName}`)}</button>}
        <button className="primary" disabled={!frame || !result || busy} onClick={use}>{image ? tr('Use this picture', 'Usar esta imagem', 'Usar esta imagen') : tr('Use as first frame', 'Usar como primeiro quadro', 'Usar como primer fotograma')}</button>
    </div>
  </dialog>;
}
