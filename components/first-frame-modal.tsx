'use client';
import {frameEditorName} from '../lib/frame-editor';
import {useEffect, useRef, useState} from 'react';
import type {Language} from '../lib/design-copy';
import type {Picture} from '../lib/media';
import Select from './select';
import {captureFrame} from '../lib/frame-capture';
import {paintMagenta, segmentFrame, segmentMask, type Segments} from '../lib/segments';

type Image = {blob: Blob; url: string};
/** BFS Body Swap and BFS Body Swap Selective only replace a clicked person. */
const personSwapOnly = (id: string | null) => id === 'bfs' || id === 'bfs_selective';
/** Editors that read the clicked person from their mask instead of a magenta paint (H3 Image swaps on a crop around them). */
const maskSwap = (id: string | null) => personSwapOnly(id) || id === 'h3image' || id === 'gpt_image';
type Op = 'swap' | 'replace' | 'remove' | 'add' | 'free';
/** Everything the editor holds for one frame of the clip, kept while moving between keyframes and restored on return. */
export type FrameDraft = {time: number; startHere: boolean; op: Op; editor: string | null; refSlots: number[]; extraRefs: {file: File; url: string}[];
  what: string; instruction: string; editPrompt: string; promptEdited: boolean; frame: {blob: Blob; width: number; height: number} | null;
  segments: Segments | null; picked: number; paint: ImageData | null; result: {blob: Blob; edit?: string} | null; batch: boolean};
/** A frame already pinned on the clip: 'first' (the first frame) or 'k<slot>' (a keyframe). */
export type FramePin = {id: string; time: number; url: string};
/** The painted area as the bridge reads it: white where painted, black elsewhere. */
function paintMask(paint: ImageData): Promise<Blob | null> {
  const out = document.createElement('canvas'); out.width = paint.width; out.height = paint.height;
  const g = out.getContext('2d'); if (!g) return Promise.resolve(null);
  const data = new ImageData(new Uint8ClampedArray(paint.data), paint.width, paint.height), d = data.data;
  for (let i = 0; i < d.length; i += 4) {const a = d[i + 3]; d[i] = d[i + 1] = d[i + 2] = a ? 255 : 0; d[i + 3] = 255;}
  g.putImageData(data, 0, 0);
  return new Promise(resolve => out.toBlob(resolve, 'image/png'));
}
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
export default function FirstFrameModal({videoUrl, start, end, initialAt, keyframe: asKeyframe = false, openingAtStart = false, marks, targetId = 'first', drafts, onDraft, onUseMany, onRemove, image, edited, pictures, swap = false, lang, onUse, onClose}: {videoUrl?: string; start?: number; end?: number; initialAt?: number; keyframe?: boolean; openingAtStart?: boolean; marks?: {cuts: number[]; shots: {from: number; end: number}[]; suggested: number[]; pins: FramePin[]};
  targetId?: string; drafts?: Record<string, FrameDraft>; onDraft?: (id: string, draft: FrameDraft | null) => void;
  onUseMany?: (items: {id: string; file: File; at: number; asKeyframe: boolean}[]) => void; onRemove?: (id: string) => void; image?: File; edited?: File; pictures: Picture[]; swap?: boolean; lang: Language; onUse: (file: File, edit: {id: string; width: number; height: number} | null, at?: number, asKeyframe?: boolean, id?: string) => void; onClose: () => void}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const dialog = useRef<HTMLDialogElement>(null), upload = useRef<HTMLInputElement>(null);
  const [frame, setFrame] = useState<Image & {width: number; height: number} | null>(null);
  const [result, setResult] = useState<Image & {edit?: string} | null>(null);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [editor, setEditor] = useState<string | null>(null);
  // Editors this ComfyUI can run, in the order the backend prefers them. The modal lets you pick one per edit.
  const [editors, setEditors] = useState<string[]>([]);
  const [editorsKnown, setEditorsKnown] = useState(false);
  const editorName = frameEditorName(editor, tr('Image editor', 'Editor de imagem', 'Editor de imagen'));
  const [op, setOp] = useState<Op>(swap ? 'swap' : 'replace');
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
  // A keyframe opens on its own time; the first frame on the start of the interval.
  const [at, setAt] = useState(initialAt ?? start ?? 0);
  const player = useRef<HTMLVideoElement | null>(null);
  // Past the start, a frame can open the clip (the interval starts there: the person may not be in frame 0) or be pinned
  // as a keyframe (the start stays). At the start with no first frame yet, it is the first frame.
  const [startHere, setStartHere] = useState(!asKeyframe);
  const atStart = at - (start ?? 0) < 1 / 48;
  // Which frame of the clip is being edited ('first', 'k<slot>' or 't:<time>'), and the editor state of the others.
  const [target, setTarget] = useState(targetId);
  const targetRef = useRef(targetId); targetRef.current = target;
  const draftsRef = useRef<Record<string, FrameDraft>>({...(drafts || {})});
  const [, setDraftTick] = useState(0);
  const [batch, setBatch] = useState(false);
  const [batchState, setBatchState] = useState('');
  // A restored frame brings back its segments, pick and paint (the frame effects below would otherwise clear them).
  const kept = useRef<{blob: Blob; segments: Segments | null; picked: number; paint: ImageData | null} | null>(null);
  const firstLike = (id: string) => id === 'first';
  const keyframe = atStart ? !firstLike(target) && !openingAtStart : !startHere;
  void asKeyframe;

  useEffect(() => {
    dialog.current?.showModal();
    // ComfyUI can take a while to list its nodes (very large models folder): ask again until the editor is known.
    let tries = 0, timer: ReturnType<typeof setTimeout> | undefined;
    const ask = () => fetch('/api/backend/health').then(r => r.json()).then(h => {
      const ready = (Array.isArray(h.frame_editors) ? h.frame_editors : []).filter((e: {installed?: boolean}) => e && e.installed).map((e: {id: string}) => String(e.id));
      const chosen = typeof h.frame_editor === 'string' ? h.frame_editor : null;
      // Character Swap prefers BFS Body Swap Selective (only the clicked person changes), then BFS Body Swap, when installed.
      setEditorsKnown(true); setEditors(ready); setEditor(current => current && ready.includes(current) ? current : swap ? (['bfs_selective', 'bfs', 'h3image'].find(id => ready.includes(id)) || chosen || ready[0] || null) : chosen || ready[0] || null);
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
    // Open on the chosen time (a keyframe opens on its own frame, not on the start of the interval).
    const saved = draftsRef.current[targetId];
    video.onloadedmetadata = () => {if (saved?.frame) return; video.currentTime = seekWanted.current = Math.min((saved?.time ?? initialAt ?? start ?? 0) + .001, Math.max(0, video.duration - .05));};
    if (saved) restore(saved);
    // Reopened with an edited first frame: start from that edit (to keep editing it, e.g. swap a second character);
    // picking another time on the slider goes back to the guide's own frames.
    let reopen = !!edited && !saved;
    video.onseeked = () => {
      // A seek given up (another frame was restored from its draft meanwhile) must not replace the frame on screen.
      // Only the frame last asked for: an earlier seek's answer, or one for a frame given up, is dropped.
      if (!reopen && (seekWanted.current === null || Math.abs(video.currentTime - seekWanted.current) > .02)) return;
      seekWanted.current = null;
      if (reopen && edited) {
        reopen = false; setSeeking(false);
        load(URL.createObjectURL(edited)).then(im => setFrame({blob: edited, url: im.src, width: im.naturalWidth, height: im.naturalHeight})).catch(() => setError(tr('Could not read the edited frame.', 'Não foi possível ler o quadro editado.', 'No se pudo leer el fotograma editado.')));
        return;
      }
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth; canvas.height = video.videoHeight;
      canvas.getContext('2d')?.drawImage(video, 0, 0);
      canvas.toBlob(blob => {setSeeking(false); if (blob) setFrame({blob, url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height});}, 'image/png');
    };
    video.onerror = () => {setSeeking(false); setError(tr('Could not read the guide video.', 'Não foi possível ler o vídeo guia.', 'No se pudo leer el vídeo guía.'));};
    return () => {clearTimeout(timer); video.removeAttribute('src'); video.load();};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl, start, image, edited]);
  useEffect(() => () => {if (frame) URL.revokeObjectURL(frame.url);}, [frame]);
  // Another frame: its old segments no longer line up, so they are dropped until Segment runs again.
  useEffect(() => {
    segmentFor.current = null; setSegmenting(false); setHover(0);
    const k = kept.current;
    if (k && frame && k.blob === frame.blob) {setSegments(k.segments); setPicked(k.picked); return;}
    setSegments(null); setPicked(0);
  }, [frame]);
  // The frame the last segmentation was asked for: a slower answer for a frame the user already left (the timeline, the
  // slider, a jump to a cut) must not be laid over the new frame, or the click and the mask pick a person of another frame.
  const segmentFor = useRef<Blob | null>(null);
  // Whether the next 'seeked' of the guide video is still wanted (a frame restored from its draft cancels a pending seek).
  const seekWanted = useRef<number | null>(null);
  async function segment() {
    if (!frame) return;
    const asked = frame.blob; segmentFor.current = asked;
    setSegmenting(true); setError('');
    try {
      const found = await segmentFrame(asked); const count = found.count;
      if (segmentFor.current !== asked) return;
      setSegments(found); setPicked(0); setHover(0);
      if (!count) setError(tr('No character found in this frame; try another frame, or describe or paint who to replace.', 'Nenhum personagem encontrado neste quadro; tente outro quadro, ou descreva ou pinte quem trocar.', 'No se encontró ningún personaje en este fotograma; prueba otro, o describe o pinta a quién reemplazar.'));
    } catch (e) {if (segmentFor.current === asked) setError(e instanceof Error ? e.message : String(e));} finally {if (segmentFor.current === asked) setSegmenting(false);}
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
  // One line on what the chosen editor does differently.
  const editorHint = editor === 'h3image' ? tr('Runs on the H3 model of your videos (PrunaAI P-H3-Image). Swap uses the Character Swap LoRA on a crop around the person (needs ComfyUI-Molmo2-H3).', 'Roda no modelo H3 dos seus vídeos (PrunaAI P-H3-Image). A troca usa a LoRA de Character Swap num recorte em volta da pessoa (precisa do ComfyUI-Molmo2-H3).', 'Funciona con el modelo H3 de tus vídeos (PrunaAI P-H3-Image). El cambio usa la LoRA de Character Swap en un recorte alrededor de la persona (necesita ComfyUI-Molmo2-H3).')
    : editor === 'bfs_selective' ? tr('Only the person you click changes; everyone else and the background stay as they are.', 'Só a pessoa clicada muda; os outros e o fundo ficam como estão.', 'Solo cambia la persona en la que haces clic; los demás y el fondo quedan igual.')
    : editor === 'bfs' ? tr('Swaps the person you click on a crop around them.', 'Troca a pessoa clicada num recorte em volta dela.', 'Cambia la persona en la que haces clic en un recorte a su alrededor.')
    // General editors redraw the whole frame from the words: for a person swap the identity, the style and the background
    // can drift toward the reference. Say so, and point to the editors made for it.
    : op === 'swap' && editor ? tr('Redraws the whole frame from the prompt: the face, the style and the background can drift (e.g. it keeps the hair or copies the reference background). For a person swap, BFS Body Swap Selective changes only the person you click.', 'Redesenha o quadro inteiro a partir do prompt: o rosto, o estilo e o fundo podem desviar (ex.: mantém o cabelo ou copia o fundo da referência). Para trocar uma pessoa, o BFS Body Swap Selective muda só quem você clicar.', 'Redibuja todo el fotograma a partir del prompt: la cara, el estilo y el fondo pueden desviarse (p.ej. conserva el pelo o copia el fondo de la referencia). Para cambiar a una persona, BFS Body Swap Selective cambia solo a quien hagas clic.') : '';
  // Swap: find the people as soon as a frame is shown (SAM 3.1), so a click is all it takes. A failure is shown once per frame.
  useEffect(() => {
    if (!frame || !editor || op !== 'swap') return;
    if (kept.current?.blob === frame.blob && kept.current.segments) return;
    const timer = setTimeout(segment, 400);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, op, !!editor]);
  // The BFS editors only swap people: another edit moves to the next editor.
  useEffect(() => {if (op !== 'swap' && personSwapOnly(editor)) setEditor(editors.find(id => !personSwapOnly(id)) || null);}, [op, editor, editors]);
  useEffect(() => {
    if (promptEdited) return;
    const query = new URLSearchParams({op, what: what.trim(), instruction: instruction.trim(), refs: String(editRefs.length), marked: String(markedPick && (!maskSwap(editor) || editor === 'gpt_image')), editor: editor || ''});
    const timer = setTimeout(() => fetch(`/api/backend/frame-edit/instruction?${query}`).then(r => r.ok ? r.json() : null).then(reply => {if (reply && typeof reply.instruction === 'string') setEditPrompt(reply.instruction);}).catch(() => {}), 250);
    return () => clearTimeout(timer);
  }, [op, what, instruction, editRefs.length, markedPick, promptEdited, editor]);
  /** The editor state of the frame on screen, as a draft. */
  function snapshot(): FrameDraft {
    const c = paint.current;
    return {time: at, startHere, op, editor, refSlots, extraRefs, what, instruction, editPrompt, promptEdited,
      frame: frame ? {blob: frame.blob, width: frame.width, height: frame.height} : null, segments, picked,
      paint: op !== 'swap' && painted && c && c.width ? c.getContext('2d')?.getImageData(0, 0, c.width, c.height) ?? null : null,
      result: result ? {blob: result.blob, edit: result.edit} : null, batch};
  }
  function keep(id: string, draft = snapshot()) {
    // A frame not pinned yet that was only looked at leaves nothing behind (its ◇ suggestion comes back).
    const untouched = (id.startsWith('t:') || (id === 'first' && !(marks?.pins || []).some(p => p.id === 'first'))) && !draft.result && !draft.picked && !draft.batch && !draft.paint && !draft.instruction.trim() && !draft.what.trim() && !draft.promptEdited;
    if (untouched) {if (draftsRef.current[id]) {delete draftsRef.current[id]; onDraft?.(id, null); setDraftTick(t => t + 1);} return draft;}
    draftsRef.current[id] = draft; onDraft?.(id, draft); setDraftTick(t => t + 1); return draft;
  }
  function restore(d: FrameDraft) {
    setAt(d.time); setStartHere(d.startHere); setOp(d.op); if (d.editor) setEditor(d.editor); setRefSlots(d.refSlots); setExtraRefs(d.extraRefs);
    setWhat(d.what); setInstruction(d.instruction); setEditPrompt(d.editPrompt); setPromptEdited(d.promptEdited); setBatch(d.batch);
    setResult(d.result ? {...d.result, url: URL.createObjectURL(d.result.blob)} : null);
    if (d.frame) {seekWanted.current = null; setSeeking(false); kept.current = {blob: d.frame.blob, segments: d.segments, picked: d.picked, paint: d.paint}; setFrame({...d.frame, url: URL.createObjectURL(d.frame.blob)});}
    else seekTo(d.time);
  }
  /** Move to another frame of the clip: the one on screen keeps its state; the other comes back as it was left, or (new)
   * with the same editor, character and references, since the next keyframe usually swaps the same person. */
  async function switchTo(id: string, time: number, pinned?: string) {
    if (busy) return;
    // A spot next to a frame already in the works is that frame (a click a few pixels off must not start a new one).
    const pinnedIds = new Set((marks?.pins || []).map(p => p.id));
    if (!draftsRef.current[id] && !pinnedIds.has(id)) {
      const near = Object.entries(draftsRef.current).filter(([k]) => !pinnedIds.has(k)).find(([, d]) => Math.abs(d.time - time) < .35)?.[0]
        ?? (marks?.pins || []).find(p => Math.abs(p.time - time) < 1 / 24)?.id;
      if (near) {const pin = marks?.pins.find(p => p.id === near); id = near; time = draftsRef.current[near]?.time ?? pin?.time ?? time; pinned = pin?.url;}
    }
    if (id === target) {if (Math.abs(time - at) > 1 / 48) chooseFrame(time); return;}
    keep(target); setTarget(id); setError('');
    const saved = draftsRef.current[id];
    if (saved) {restore(saved); return;}
    kept.current = null; setWhat(''); setInstruction(''); setPromptEdited(false); setBatch(batch); setStartHere(false); chooseFrame(time);
    if (pinned) {try {const blob = await (await fetch(pinned)).blob(); setResult({blob, url: URL.createObjectURL(blob)});} catch {/* the pin shows again once edited */}}
  }
  const refsOf = (d: Pick<FrameDraft, 'refSlots' | 'extraRefs'>) => [...pictures.filter(p => d.refSlots.includes(p.slot)).map(p => ({file: p.file})), ...d.extraRefs.map(r => ({file: r.file}))].slice(0, 12);
  const readyOf = (d: FrameDraft) => !!d.frame && !!d.editor && (d.promptEdited && !!d.editPrompt.trim() ? true : d.op === 'swap' ? refsOf(d).length > 0 || !!d.instruction.trim()
    : d.op === 'remove' ? !!(d.what.trim() || d.paint) : d.op === 'replace' ? !!((d.what.trim() || d.paint) && d.instruction.trim()) : !!d.instruction.trim());
  /** A draft saved before its guide frame had loaded (a quick upload or move) gets the frame now. */
  async function withFrame(id: string, d: FrameDraft): Promise<FrameDraft> {
    if (d.frame || !videoUrl) return d;
    const f = await captureFrame(videoUrl, d.time), next = {...d, frame: f};
    draftsRef.current[id] = next; onDraft?.(id, next); return next;
  }
  /** Run one frame's edit on the bridge. */
  async function send(d: FrameDraft): Promise<{blob: Blob; edit?: string}> {
    if (!d.frame) throw Error(tr('The frame is not loaded yet.', 'O quadro ainda não carregou.', 'El fotograma aún no cargó.'));
    const body = new FormData();
    // The BFS editors, H3 Image and GPT Image read the clicked person from a mask; the other editors get them painted magenta.
    const viaMask = maskSwap(d.editor), pickedOne = d.op === 'swap' && !!d.segments && d.picked > 0, marked = pickedOne && !viaMask;
    const src = URL.createObjectURL(d.frame.blob);
    try {body.set('frame', marked ? await paintMagenta(src, d.segments!, d.picked) : d.frame.blob, 'frame.png');} finally {URL.revokeObjectURL(src);}
    if (viaMask && pickedOne) body.set('mask', await segmentMask(d.segments!, d.picked, d.frame.width, d.frame.height), 'mask.png');
    body.set('instruction', d.instruction.trim()); body.set('op', d.op); body.set('what', d.what.trim());
    if (marked) body.set('marked', '1');
    if (d.promptEdited && d.editPrompt.trim()) body.set('prompt', d.editPrompt.trim());
    if (d.editor) body.set('editor', d.editor);
    if (d.op !== 'swap' && d.paint) {const mask = await paintMask(d.paint); if (mask) body.set('mask', mask, 'mask.png');}
    refsOf(d).forEach((r, i) => body.append(`picture_${String(i + 1).padStart(2, '0')}`, r.file, r.file.name));
    const response = await fetch('/api/backend/frame-edit', {method: 'POST', body});
    if (!response.ok) {const reply = await response.json().catch(() => ({})); throw Error(reply.detail || reply.error || `HTTP ${response.status}`);}
    const blob = await response.blob(), edit = response.headers.get('x-henge-edit') || undefined;
    if (edit) setEdits(current => [{id: edit, created: Date.now() / 1000, instruction: d.instruction.trim() || d.what.trim(), url: `/api/backend/frame-edits/${edit}`}, ...current]);
    return {blob, edit};
  }
  async function edit() {
    if (!frame || !ready) return;
    setBusy(true); setError('');
    try {const out = await send(snapshot()); setResult({...out, url: URL.createObjectURL(out.blob)});}
    catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}
  }
  // The batch: every frame ticked "Batch" is edited with its own settings (GPT Image three at a time, ComfyUI editors one
  // after another), then they can all be pinned at once.
  const batchIds = () => [...Object.keys(draftsRef.current).filter(id => id !== target && draftsRef.current[id].batch), ...(batch ? [target] : [])];
  async function editBatch() {
    keep(target);
    const ids = batchIds().filter(id => readyOf(draftsRef.current[id]));
    if (!ids.length) {setError(tr('No frame in the batch is ready: each needs its edit (person, character or prompt).', 'Nenhum quadro do lote está pronto: cada um precisa da sua edição (pessoa, personagem ou prompt).', 'Ningún fotograma del lote está listo: cada uno necesita su edición.')); return;}
    setBusy(true); setError(''); let done = 0; const failed: string[] = [];
    const queue = [...ids], width = ids.every(id => draftsRef.current[id].editor === 'gpt_image') ? 3 : 1;
    setBatchState(`0/${ids.length}`);
    const worker = async () => {
      while (queue.length) {
        const id = queue.shift()!;
        try {
          const out = await send(await withFrame(id, draftsRef.current[id]));
          keep(id, {...draftsRef.current[id], result: out});
          if (id === targetRef.current) setResult({...out, url: URL.createObjectURL(out.blob)});
        } catch (e) {failed.push(`${(draftsRef.current[id].time - (start ?? 0)).toFixed(2)} s: ${e instanceof Error ? e.message : e}`);}
        setBatchState(`${++done}/${ids.length}`);
      }
    };
    await Promise.all(Array.from({length: Math.min(width, ids.length)}, worker));
    setBusy(false); setBatchState('');
    if (failed.length) setError(failed.join(' · '));
  }
  const asKeyframeAt = (id: string, d: FrameDraft) => d.time - (start ?? 0) < 1 / 48 ? !firstLike(id) && !openingAtStart : !d.startHere;
  async function pinBatch(only?: string[]) {
    keep(target);
    const ids = (only ?? batchIds()).filter(id => draftsRef.current[id]?.result);
    const items = await Promise.all(ids.map(async id => {
      const d = await withFrame(id, draftsRef.current[id]), url = URL.createObjectURL(d.result!.blob);
      try {return {id, file: await coverFit(url, d.frame!.width, d.frame!.height), at: d.time, asKeyframe: asKeyframeAt(id, d)};} finally {URL.revokeObjectURL(url);}
    }));
    onUseMany?.(items);
  }
  function removeTarget() {
    const id = target;
    onRemove?.(id); delete draftsRef.current[id]; setDraftTick(t => t + 1);
    const rest = (marks?.pins || []).filter(p => p.id !== id);
    if (rest.length) {kept.current = null; setTarget(rest[0].id); const d = draftsRef.current[rest[0].id]; if (d) restore(d); else {setResult(null); chooseFrame(rest[0].time); fetch(rest[0].url).then(r => r.blob()).then(blob => setResult({blob, url: URL.createObjectURL(blob)})).catch(() => {});}}
    else onClose();
  }
  function close() {if (!image) keep(target); onClose();}
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
    if (!image) keep(target);
    onUse(await coverFit(result.url, frame.width, frame.height), result.edit ? {id: result.edit, width: frame.width, height: frame.height} : null, image ? undefined : at, image ? undefined : keyframe, image ? undefined : target);
  }
  // Until the new frame is grabbed, the old one (and its people) must not take a click: the pick would land on the frame
  // being left and then vanish, or mark a person of another frame.
  const [seeking, setSeeking] = useState(false);
  // The frame on screen is dropped too: an edit, an upload or a pin made before the new frame arrives would otherwise be
  // made on the old frame and saved at the new time (a keyframe at 4 s showing the 8.8 s frame).
  function seekTo(t: number) {const video = player.current; if (!video) return; segmentFor.current = null; setSegments(null); setPicked(0); setHover(0); setSeeking(true); setFrame(null); const go = () => {video.currentTime = seekWanted.current = Math.min(t + .001, Math.max(0, video.duration - .05));}; seekWanted.current = -1; if (!video.duration) {video.onloadedmetadata = go; return;} go();}
  function chooseFrame(t: number) {
    // Another guide frame: grab it and drop an edit made on the previous one.
    kept.current = null; setAt(t); setResult(null); seekTo(t);
  }

  // The painted mask: white where the edit may change the frame; drawn at the frame's own resolution.
  useEffect(() => {
    const c = paint.current; if (!c || !frame) return;
    c.width = frame.width; c.height = frame.height; setPainted(false);
    const k = kept.current;
    if (k && k.blob === frame.blob && k.paint && k.paint.width === c.width) {c.getContext('2d')?.putImageData(k.paint, 0, 0); setPainted(true);}
  }, [frame]);
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

  return <dialog ref={dialog} className={`trim-modal first-frame-modal${frame && frame.width > frame.height ? ' landscape' : ''}`} aria-labelledby="first-frame-heading" onCancel={e => {e.preventDefault(); close();}}>
    <header className="trim-header"><div><span className="eyebrow">{image ? tr('PICTURE', 'IMAGEM', 'IMAGEN') : tr('FRAME', 'QUADRO', 'FOTOGRAMA')}</span><h2 id="first-frame-heading">{image ? tr('Edit this picture', 'Edite esta imagem', 'Edita esta imagen') : keyframe ? tr('Pin a keyframe', 'Fixar um keyframe', 'Fijar un keyframe') : swap ? tr('Swap the character into a frame', 'Coloque o personagem em um quadro', 'Pon al personaje en un fotograma') : tr('Edit a frame, propagate it', 'Edite um quadro e propague', 'Edita un fotograma y propágalo')}</h2>
      <p>{keyframe ? tr('Edit the frame as it should look in the result at this time; the clip passes through it.', 'Edite o quadro como ele deve ficar no resultado neste tempo; o vídeo passa por ele.', 'Edita el fotograma como debe verse en el resultado en este tiempo; el vídeo pasa por él.') : !image && swap ? tr('Click who to replace, then edit. The result becomes the first frame of the swap.', 'Clique em quem trocar e edite. O resultado vira o primeiro quadro do swap.', 'Haz clic en quién reemplazar y edita. El resultado será el primer fotograma del swap.') : image ? tr('Replace, remove or add something, or paint the area to change; the result replaces the picture.', 'Substitua, remova ou adicione algo, ou pinte a área a mudar; o resultado substitui a imagem.', 'Reemplaza, quita o añade algo, o pinta el área a cambiar; el resultado sustituye la imagen.') : tr('The edited frame becomes a picture of the edit. Use the "First-frame propagate" model in Motion Transfer.', 'O quadro editado vira uma Picture da edição. Use o modelo "First-frame propagate" no Motion Transfer.', 'El fotograma editado se convierte en una imagen de la edición. Usa el modelo "First-frame propagate" en Motion Transfer.')}</p></div>
      <button type="button" className="trim-close" aria-label={tr('Close', 'Fechar', 'Cerrar')} onClick={close}>×</button></header>
    <div className="first-frame-body">
    <div className="ff-visual">
    <div className="first-frame-panes">
      <figure><figcaption className="eyebrow muted">{image ? tr('Picture', 'Imagem', 'Imagen') : tr('Guide frame', 'Quadro do guia', 'Fotograma de la guía')}{frame ? ` · ${frame.width}×${frame.height}` : ''}</figcaption>{frame ? <div className="first-frame-paint" style={shape}><img src={frame.url} alt=""/>{editor && op === 'swap' && segments && !seeking && <canvas ref={pickCanvas} className="segment-pick" aria-label={tr('Click the character to replace', 'Clique no personagem a trocar', 'Haz clic en el personaje a reemplazar')} onPointerMove={e => setHover(labelAt(e))} onPointerLeave={() => setHover(0)} onClick={e => {const n = labelAt(e); setPicked(p => n && n !== p ? n : 0);}}/>}{editor && op !== 'swap' && <canvas ref={paint} aria-label={tr('Paint the area to edit', 'Pinte a área a editar', 'Pinta el área a editar')} onPointerDown={e => {drawing.current = true; lastDab.current = null; e.currentTarget.setPointerCapture(e.pointerId); stroke(e);}} onPointerMove={stroke} onPointerUp={() => {drawing.current = false; lastDab.current = null;}}/>}</div> : <div className="first-frame-empty">{tr('Reading the frame…', 'Lendo o quadro…', 'Leyendo el fotograma…')}</div>}</figure>
      <figure><figcaption className="eyebrow muted">{tr('Edited', 'Editado', 'Editado')}</figcaption>{result ? <img src={result.url} alt="" style={shape}/> : <div className="first-frame-empty" style={shape}>{busy ? tr(`${editorName} is editing… (about 1 min)`, `${editorName} está editando… (cerca de 1 min)`, `${editorName} está editando… (alrededor de 1 min)`) : editor ? tr(`Edit with ${editorName} or upload an image`, `Edite com ${editorName} ou envie uma imagem`, `Edita con ${editorName} o sube una imagen`) : tr('Upload an edited image', 'Envie uma imagem editada', 'Sube una imagen editada')}</div>}</figure>
    </div>
    {!image && end !== undefined && end - (start ?? 0) > .1 && (() => {
      const s0 = start ?? 0, span = Math.max(.01, end - s0), pos = (t: number) => `${Math.min(100, Math.max(0, (t - s0) / span * 100))}%`;
      const clock = (t: number) => `${(t - s0).toFixed(2)} s`;
      // A cut that already has a frame in the works (not pinned yet) is no longer a suggestion.
      const drafted = Object.entries(draftsRef.current).filter(([id]) => id !== target && !marks?.pins.some(p => p.id === id)).map(([, d]) => d.time).concat(marks?.pins.some(p => p.id === target) ? [] : [at]);
      const suggested = (marks?.suggested || []).filter(t => !drafted.some(d => Math.abs(d - t) < .35));
      const todo = suggested.filter(t => Math.abs(t - at) > 1 / 48);
      const pinnedHere = marks?.pins.some(p => p.id === target);
      const prev = [...todo].reverse().find(t => t < at), next = todo.find(t => t > at);
      return <div className="frame-chooser ff-timeline">
        <div className="ff-timeline-head"><span className="eyebrow muted">{tr('Frame', 'Quadro', 'Fotograma')} <b className="mono">{clock(at)}</b>
          {pinnedHere && onRemove && (() => {const label = target === 'first' ? tr('Remove the first frame', 'Remover o primeiro quadro', 'Quitar el primer fotograma') : tr('Remove this keyframe', 'Remover este keyframe', 'Quitar este keyframe');
            return <button type="button" className="ff-remove" title={label} aria-label={label} onClick={removeTarget}><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg></button>;})()}</span>
          {marks && marks.suggested.length > 0 && <span className="ff-jump"><button type="button" className="quiet-button" disabled={prev === undefined} aria-label={tr('Previous cut without a keyframe', 'Corte anterior sem keyframe', 'Corte anterior sin keyframe')} onClick={() => prev !== undefined && void switchTo(`t:${prev.toFixed(2)}`, prev)}>‹</button>
            <span className="mono">◇ {suggested.length}</span>
            <button type="button" className="quiet-button" disabled={next === undefined} aria-label={tr('Next cut without a keyframe', 'Próximo corte sem keyframe', 'Siguiente corte sin keyframe')} onClick={() => next !== undefined && void switchTo(`t:${next.toFixed(2)}`, next)}>›</button></span>}</div>
        {marks && <div className="kf-timeline" role="group" aria-label={tr('Shots, camera cuts and keyframes', 'Shots, cortes e keyframes', 'Shots, cortes y keyframes')}
          title={tr('Click an empty spot to add a frame there', 'Clique num ponto vazio para adicionar um quadro ali', 'Haz clic en un punto vacío para añadir un fotograma ahí')}
          onClick={e => {if (e.target !== e.currentTarget && !(e.target as HTMLElement).classList.contains('kf-shot')) return; const r = e.currentTarget.getBoundingClientRect(); const t = Math.round((s0 + (e.clientX - r.left) / r.width * span) * 24) / 24; void switchTo(`t:${t.toFixed(2)}`, Math.min(end - 1 / 24, Math.max(s0, t)));}}>
          {marks.shots.map((x, i) => <span key={i} className={'kf-shot' + (i % 2 ? ' alt' : '')} style={{left: pos(x.from), width: `${(x.end - x.from) / span * 100}%`}}/>)}
          {marks.cuts.map(c => <span key={c} className="kf-cut" style={{left: pos(c)}}/>)}
          {marks.pins.map(p => <button key={p.id} type="button" className={'kf-pin' + (p.id === target ? ' current' : '') + ((p.id === target ? batch : draftsRef.current[p.id]?.batch) ? ' in-batch' : '')} style={{left: pos(p.time)}} title={clock(p.time)} aria-pressed={p.id === target} aria-label={tr(`Keyframe at ${clock(p.time)}`, `Keyframe em ${clock(p.time)}`, `Keyframe en ${clock(p.time)}`)} onClick={() => void switchTo(p.id, p.time, p.url)}>◆</button>)}
          {[...Object.entries(draftsRef.current).filter(([id]) => id !== target && !marks.pins.some(p => p.id === id)), ...(marks.pins.some(p => p.id === target) ? [] : [[target, {time: at, result} as FrameDraft] as [string, FrameDraft]])].map(([id, d]) => <button key={id} type="button" className={'kf-pin draft' + (id === target ? ' current' : '') + (d.result ? ' edited' : '') + ((id === target ? batch : d.batch) ? ' in-batch' : '')} style={{left: pos(d.time)}} title={tr(`Not pinned yet: ${clock(d.time)}`, `Ainda não fixado: ${clock(d.time)}`, `Aún sin fijar: ${clock(d.time)}`)} aria-label={tr(`Unpinned frame at ${clock(d.time)}`, `Quadro não fixado em ${clock(d.time)}`, `Fotograma sin fijar en ${clock(d.time)}`)} onClick={() => void switchTo(id, d.time)}>◆</button>)}
          {suggested.map(t => <button key={`s${t}`} type="button" className="kf-pin suggest" style={{left: pos(t)}} title={tr(`Camera cut at ${clock(t)}`, `Corte em ${clock(t)}`, `Corte en ${clock(t)}`)} aria-label={tr('Suggested keyframe', 'Keyframe sugerido', 'Keyframe sugerido')} onClick={() => void switchTo(`t:${t.toFixed(2)}`, t)}>◇</button>)}
          <span className="kf-head" style={{left: pos(at)}}/>
        </div>}
        <input type="range" min={s0} max={Math.max(s0, end - 1 / 24)} step={1 / 24} value={at} onChange={e => chooseFrame(Number(e.target.value))} aria-label={tr('Frame to edit', 'Quadro a editar', 'Fotograma a editar')}/>
        {!atStart && <div className="ff-role" role="group" aria-label={tr('Use this frame to', 'Usar este quadro para', 'Usar este fotograma para')}>
          <button type="button" aria-pressed={!startHere} className={!startHere ? 'chosen' : ''} onClick={() => setStartHere(false)}>◆ {tr('Pin as a keyframe', 'Fixar como keyframe', 'Fijar como keyframe')}</button>
          <button type="button" aria-pressed={startHere} className={startHere ? 'chosen' : ''} onClick={() => setStartHere(true)}>⇤ {tr('Start the clip here', 'Começar o vídeo aqui', 'Empezar el vídeo aquí')}</button></div>}
        <small>{!keyframe && !atStart ? tr(`This frame becomes the first frame; the interval starts at ${clock(at)} (the part before is left out).`, `Este quadro vira o primeiro quadro; o intervalo começa em ${clock(at)} (o trecho antes fica de fora).`, `Este fotograma pasa a ser el primero; el intervalo empieza en ${clock(at)} (lo anterior queda fuera).`) : keyframe ? tr('Bars are shots, orange ticks camera cuts, ◆ your keyframes, ◇ cuts without one. Click an empty spot to add a frame; each keeps its own edit.', 'Barras são shots, traços laranja cortes de câmera, ◆ seus keyframes, ◇ cortes sem keyframe. Clique num ponto vazio para adicionar um quadro; cada um guarda a sua edição.', 'Las barras son shots, las marcas naranjas cortes de cámara, ◆ tus keyframes, ◇ cortes sin keyframe. Haz clic en un punto vacío para añadir un fotograma; cada uno guarda su edición.') : tr('Generation starts at this frame.', 'A geração começa neste quadro.', 'La generación empieza en este fotograma.')}</small>
      </div>;
    })()}
    </div>
    <div className="first-frame-form">
    {editor && <div className="edit-ops" role="group" aria-label={tr('Edit', 'Edição', 'Edición')}>{ops.map(([k, label]) => <button key={k} type="button" aria-pressed={op === k} className={op === k ? 'chosen' : ''} onClick={() => setOp(k)}>{label}</button>)}</div>}
    <div className="first-frame-controls">
      {editor ? <>
        {op === 'swap' ? <div className="ff-step"><span className="eyebrow muted">{tr('Who', 'Quem', 'Quién')}</span>
          <p className={'ff-status' + (picked ? ' done' : '')}>{seeking ? tr('Reading this frame…', 'Lendo este quadro…', 'Leyendo este fotograma…') : segmenting ? tr('Finding the people in this frame…', 'Encontrando as pessoas neste quadro…', 'Buscando a las personas en este fotograma…')
            : picked ? <>{tr(`Person ${picked} selected.`, `Pessoa ${picked} selecionada.`, `Persona ${picked} seleccionada.`)} <button type="button" className="text-link" onClick={() => setPicked(0)}>{tr('Change', 'Trocar', 'Cambiar')}</button></>
            : segments?.count ? tr('Click the person to replace on the frame.', 'Clique na pessoa a trocar no quadro.', 'Haz clic en la persona a reemplazar en el fotograma.')
            : segments ? tr('No one found here: try another frame, or name them under Advanced.', 'Ninguém encontrado: tente outro quadro, ou diga quem em Avançado.', 'No se encontró a nadie: prueba otro fotograma, o indícalo en Avanzado.')
            : <button type="button" className="text-link" disabled={!frame} onClick={segment}>{tr('Find the people in this frame', 'Encontrar as pessoas neste quadro', 'Buscar a las personas en este fotograma')}</button>}</p></div>
        : <div className="ff-step"><span className="eyebrow muted">{tr('Change', 'Mudança', 'Cambio')}</span>
          {(op === 'replace' || op === 'remove') && <input aria-label={op === 'remove' ? tr('What should go away?', 'O que deve sumir?', '¿Qué debe desaparecer?') : tr('What do you replace?', 'O que você vai substituir?', '¿Qué reemplazas?')} value={what} onChange={e => setWhat(e.target.value)} placeholder={op === 'remove' ? tr('What goes away? e.g. the black hoodie', 'O que some? ex.: o moletom preto', '¿Qué desaparece? p.ej. la sudadera negra') : tr('What do you replace? e.g. the black hoodie', 'O que substituir? ex.: o moletom preto', '¿Qué reemplazas? p.ej. la sudadera negra')}/>}
          {op !== 'remove' && <textarea rows={2} aria-label={op === 'replace' ? tr('With what?', 'Pelo quê?', '¿Por qué?') : op === 'add' ? tr('What do you add, and where?', 'O que adicionar, e onde?', '¿Qué añades y dónde?') : tr('What should change in this frame?', 'O que deve mudar neste quadro?', '¿Qué debe cambiar en este fotograma?')} value={instruction} onChange={e => setInstruction(e.target.value)} placeholder={op === 'add' ? tr('What do you add, and where? e.g. a small dragon on his shoulder', 'O que adicionar, e onde? ex.: um pequeno dragão no ombro dele', '¿Qué añades y dónde? p.ej. un pequeño dragón en su hombro') : op === 'replace' ? tr('With what? e.g. a red leather jacket', 'Pelo quê? ex.: uma jaqueta de couro vermelha', '¿Por qué? p.ej. una chaqueta de cuero roja') : tr('What should change? e.g. set his hands on fire', 'O que deve mudar? ex.: coloque fogo nas mãos dele', '¿Qué debe cambiar? p.ej. pon fuego en sus manos')}/>}
          <div className="paint-tools"><span className="muted">{tr('Paint on the frame to limit the area.', 'Pinte no quadro para limitar a área.', 'Pinta en el fotograma para limitar el área.')}</span>
            <label aria-label={tr('Brush', 'Pincel', 'Pincel')}><input type="range" min="8" max="160" value={brush} onChange={e => setBrush(Number(e.target.value))}/></label>
            <button type="button" className="quiet-button" aria-pressed={erase} onClick={() => setErase(v => !v)}>{erase ? tr('Eraser on', 'Borracha ligada', 'Borrador activo') : tr('Eraser', 'Borracha', 'Borrador')}</button>
            <button type="button" className="quiet-button" disabled={!painted} onClick={clearMask}>{tr('Clear', 'Limpar', 'Borrar')}</button></div></div>}
        <div className="ff-step edit-refs"><span className="eyebrow muted">{op === 'swap' ? tr('Character', 'Personagem', 'Personaje') : tr('References (optional)', 'Referências (opcional)', 'Referencias (opcional)')}</span>
          {/* Each chosen reference shows the name it has in the prompt (image 2, image 3...: image 1 is the frame). */}
          <div className="edit-ref-list">{pictures.map(p => {const n = imageNumber(`p${p.slot}`); return <button type="button" key={p.slot} aria-pressed={refSlots.includes(p.slot)} className={refSlots.includes(p.slot) ? 'chosen' : ''} title={n ? `Picture ${p.slot} = image ${n}` : `Picture ${p.slot}`} onClick={() => setRefSlots(cur => cur.includes(p.slot) ? cur.filter(x => x !== p.slot) : [...cur, p.slot])}><img src={p.url} alt={`Picture ${p.slot}`}/>{n ? <b className="edit-ref-index">image {n}</b> : null}<span>P{p.slot}</span></button>;})}
            {extraRefs.map((r, i) => <div key={r.url} className="edit-ref-chip chosen" title={`${r.file.name} = image ${imageNumber(`x${i}`)}`}><img src={r.url} alt={r.file.name}/><b className="edit-ref-index">image {imageNumber(`x${i}`)}</b>
              <button type="button" className="edit-ref-remove" aria-label={tr('Remove this reference', 'Remover esta referência', 'Quitar esta referencia')} title={tr('Remove this reference', 'Remover esta referência', 'Quitar esta referencia')} onClick={() => setExtraRefs(cur => {URL.revokeObjectURL(r.url); return cur.filter((_, k) => k !== i);})}>×</button></div>)}
            {editRefs.length < 12 && <button type="button" className="edit-ref-add" onClick={() => refUpload.current?.click()}>+<span>{tr('Upload', 'Enviar', 'Subir')}</span></button>}</div>
          {op !== 'swap' && editRefs.length > 0 && <small className="muted">{tr('Mention them as ', 'Cite-as como ', 'Menciónalas como ')}{editRefs.map((r, i) => `image ${i + 2}`).join(', ')}{tr(', e.g. "his jacket from image 2".', ', p.ex. "a jaqueta da image 2".', ', p.ej. "su chaqueta de la image 2".')}</small>}
          {op === 'swap' && <input aria-label={tr('Anything else? (optional)', 'Mais alguma coisa? (opcional)', '¿Algo más? (opcional)')} value={instruction} onChange={e => setInstruction(e.target.value)} placeholder={editRefs.length ? tr('Anything else? (optional) e.g. keep the microphone', 'Mais alguma coisa? (opcional) ex.: manter o microfone', '¿Algo más? (opcional) p.ej. mantener el micrófono') : tr('No picture? Describe the new character', 'Sem imagem? Descreva o novo personagem', '¿Sin imagen? Describe al nuevo personaje')}/>}
          <input hidden ref={refUpload} type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={e => {const files = Array.from(e.target.files ?? []); setExtraRefs(cur => [...cur, ...files.map(file => ({file, url: URL.createObjectURL(file)}))]); e.target.value = '';}}/></div>
        {editors.filter(id => !personSwapOnly(id) || op === 'swap').length > 1 ? <div className="ff-step edit-editors"><label className="ff-editor"><span className="eyebrow muted">{tr('Editor', 'Editor', 'Editor')}</span>
          <Select aria-label={tr('Image editor', 'Editor de imagem', 'Editor de imagen')} value={editor} onChange={e => setEditor(e.target.value)}>{editors.filter(id => !personSwapOnly(id) || op === 'swap').map(id => <option key={id} value={id}>{frameEditorName(id, id)}</option>)}</Select></label>
          {editorHint && <small className="edit-hint">{editorHint}</small>}</div> : editorHint && <small className="edit-hint">{editorHint}</small>}
        <details className="ff-advanced" open={promptEdited || undefined}><summary>{tr('Advanced', 'Avançado', 'Avanzado')}</summary>
          {op === 'swap' && <>{!picked && <label>{tr('Who do you replace? (without a click)', 'Quem você vai trocar? (sem clicar)', '¿A quién reemplazas? (sin clic)')}<input value={what} onChange={e => setWhat(e.target.value)} placeholder={tr('the man in the red jacket', 'o homem de jaqueta vermelha', 'el hombre de la chaqueta roja')}/></label>}
            {segments && <button type="button" className="quiet-button" disabled={!frame || segmenting} onClick={segment}>{tr('Find the people again', 'Encontrar as pessoas de novo', 'Buscar a las personas de nuevo')}</button>}</>}
          <label className="edit-prompt"><span>{tr('Prompt sent to the editor (English)', 'Prompt enviado ao editor (em inglês)', 'Prompt enviado al editor (en inglés)')}{promptEdited && <button type="button" className="text-link" onClick={() => setPromptEdited(false)}>{tr('Reset', 'Restaurar', 'Restablecer')}</button>}</span>
            <textarea rows={5} value={editPrompt} onChange={e => {setEditPrompt(e.target.value); setPromptEdited(true);}}/>
            <small className="muted">{promptEdited ? tr('Sent as is; the choices above no longer change it.', 'Enviado como está; as escolhas acima não mudam mais ele.', 'Se envía tal cual; las opciones de arriba ya no lo cambian.') : tr('Built from your choices; edit it to write your own.', 'Montado a partir das suas escolhas; edite para escrever o seu.', 'Se arma con tus opciones; edítalo para escribir el tuyo.')}</small></label>
        </details>
      </> : !editorsKnown ? <small className="muted">{tr('Looking for the image editors…', 'Procurando os editores de imagem…', 'Buscando los editores de imagen…')}</small> : <small className="muted">{tr('No image editor is installed on this ComfyUI (add one in Settings → Image editors); upload an edited frame instead.', 'Nenhum editor de imagem está instalado neste ComfyUI (adicione em Configurações → Editores de imagem); envie um quadro já editado.', 'No hay editor de imagen en este ComfyUI (añade uno en Ajustes → Editores de imagen); sube un fotograma editado.')}</small>}
      {edits.length > 0 && <div className="recent-edits"><div className="recent-edits-head"><span className="eyebrow muted">{tr('Recent edits', 'Edições recentes', 'Ediciones recientes')}</span><button type="button" className="text-link" title={tr('Delete the stored frame edits', 'Apague as edições de quadro armazenadas', 'Elimina las ediciones de fotograma guardadas')} onClick={clearEdits}>{tr('Clear', 'Limpar', 'Limpiar')}</button></div><div>{edits.map(e => <button key={e.id} title={e.instruction} aria-pressed={result?.edit === e.id} onClick={() => pick(e)}><img src={e.url} alt={e.instruction} loading="lazy"/></button>)}</div></div>}
      {error && <p className="validation" role="alert">{error}</p>}
    </div>
    </div>
    </div>
      <input hidden ref={upload} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => {const file = e.target.files?.[0]; if (file) setResult({blob: file, url: URL.createObjectURL(file)}); e.target.value = '';}}/>
    <div className="modal-actions first-frame-footer">
        {editor && frame && missing && !busy && <small className="muted first-frame-hint">{missing}</small>}
        {!image && onUseMany && (() => {
          // Frames edited here but not pinned yet: only pinned frames reach the generation, so they get one button.
          const pinnedIds = new Set((marks?.pins || []).map(p => p.id));
          const unpinned = [...Object.keys(draftsRef.current).filter(id => id !== target && !pinnedIds.has(id) && draftsRef.current[id].result), ...(result && !pinnedIds.has(target) ? [target] : [])];
          const others = unpinned.filter(id => id !== target).length;
          if (!batch && others > 0) return <div className="ff-batch">
            <small className="warn ff-batch-hint">{tr(`${others} other edited frame${others > 1 ? 's are' : ' is'} not pinned yet: only pinned frames go into the generation.`, `${others} outro${others > 1 ? 's' : ''} quadro${others > 1 ? 's' : ''} editado${others > 1 ? 's' : ''} ainda não fixado${others > 1 ? 's' : ''}: só os fixados entram na geração.`, `${others} otro${others > 1 ? 's' : ''} fotograma${others > 1 ? 's' : ''} editado${others > 1 ? 's' : ''} sin fijar: solo los fijados entran en la generación.`)}</small>
            <button type="button" className="primary" disabled={busy} onClick={() => pinBatch(unpinned)}>{tr(`Pin all ${unpinned.length} edited`, `Fixar os ${unpinned.length} editados`, `Fijar los ${unpinned.length} editados`)}</button>
            <span className="ff-batch-toggle"><button type="button" id="ff-batch" className="toggle" role="switch" aria-checked={batch} aria-label={tr('Add this frame to the batch', 'Incluir este quadro no lote', 'Incluir este fotograma en el lote')} onClick={() => setBatch(v => !v)}><span/></button><label htmlFor="ff-batch">{tr('Batch', 'Lote', 'Lote')}</label></span>
          </div>;
          const ids = batchIds(), edited = ids.filter(id => (id === target ? result : draftsRef.current[id]?.result));
          return <div className="ff-batch">
            <span className="ff-batch-toggle" title={tr('Edit several frames together, each with its own settings', 'Edite vários quadros juntos, cada um com suas configurações', 'Edita varios fotogramas juntos, cada uno con su configuración')}>
              <button type="button" id="ff-batch" className="toggle" role="switch" aria-checked={batch} aria-label={tr('Add this frame to the batch', 'Incluir este quadro no lote', 'Incluir este fotograma en el lote')} onClick={() => setBatch(v => !v)}><span/></button>
              <label htmlFor="ff-batch">{tr('Batch', 'Lote', 'Lote')}</label>{ids.length > 0 && <span className="mini-badge">{ids.length}</span>}</span>
            {ids.length === 1 && <small className="muted ff-batch-hint">{tr('Now open another frame on the timeline and turn Batch on there too: with 2 or more, "Edit N frames" and "Pin N edited" show here. This frame alone uses the buttons on the right.', 'Agora abra outro quadro na timeline e ligue o Lote nele também: com 2 ou mais aparecem aqui "Editar N quadros" e "Fixar N editados". Este quadro sozinho usa os botões à direita.', 'Ahora abre otro fotograma en la línea de tiempo y activa Lote ahí también: con 2 o más aparecen aquí "Editar N fotogramas" y "Fijar N editados". Este fotograma solo usa los botones de la derecha.')}</small>}
            {ids.length > 1 && <button type="button" className={edited.length ? 'quiet-button' : 'primary'} disabled={busy} onClick={editBatch}>{batchState ? tr(`Editing ${batchState}…`, `Editando ${batchState}…`, `Editando ${batchState}…`) : tr(`Edit ${ids.length} frames`, `Editar ${ids.length} quadros`, `Editar ${ids.length} fotogramas`)}</button>}
            {ids.length > 1 && edited.length > 0 && <button type="button" className="primary" disabled={busy} onClick={() => pinBatch()}>{tr(`Pin ${edited.length} edited`, `Fixar ${edited.length} editados`, `Fijar ${edited.length} editados`)}</button>}
          </div>;
        })()}
        <button className="quiet-button" disabled={!frame} onClick={() => upload.current?.click()}>{tr('Upload edited image', 'Enviar imagem editada', 'Subir imagen editada')}</button>
        {editor && <button className={result ? 'quiet-button' : 'primary'} disabled={!frame || !ready || busy} title={missing || undefined} onClick={edit}>{busy ? tr('Editing…', 'Editando…', 'Editando…') : tr(`Edit with ${editorName}`, `Editar com ${editorName}`, `Editar con ${editorName}`)}</button>}
        <button className={result || !editor ? 'primary' : 'quiet-button'} disabled={!frame || !result || busy} onClick={use}>{image ? tr('Use this picture', 'Usar esta imagem', 'Usar esta imagen') : keyframe ? tr('Pin this frame', 'Fixar este quadro', 'Fijar este fotograma') : tr('Use as first frame', 'Usar como primeiro quadro', 'Usar como primer fotograma')}</button>
    </div>
  </dialog>;
}
