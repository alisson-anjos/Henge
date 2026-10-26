'use client';

import {useEffect, useRef, useState} from 'react';
import type {Picture} from '../lib/media';
import type {ClipRange} from './video-trim-modal';
import type {Language} from '../lib/design-copy';
import {SUBJECT_COLORS, videoPoint, type SubjectAnchor, type SubjectBinding, type GuideRepresentation} from '../lib/subject-bindings';
import styles from './subject-bindings.module.css';

const copy = {
  pt: {title: 'Personagens e referências', add: 'Adicionar personagem', select: 'Marcar no vídeo', selecting: 'Clique no personagem no vídeo', refs: 'Referências da mesma identidade', remove: 'Remover personagem', mode: 'Representação do guia', point: 'Ponto marcado', pending: 'Sem ponto', hint: 'Pause no frame desejado e marque o personagem. Você pode adicionar pontos em outros momentos para a mesma identidade.', empty: 'Vincule pessoas ou animais às suas referências por cor.', draft: 'Seleções salvas para o processamento futuro. Rastreamento e meshes ainda não são gerados aqui.', anchors: 'ponto(s)', name: 'Nome', color: 'Cor', colors: ['Vermelho', 'Azul', 'Verde', 'Amarelo', 'Magenta', 'Ciano', 'Laranja', 'Roxo']},
  en: {title: 'Subjects and references', add: 'Add subject', select: 'Mark in video', selecting: 'Click the subject in the video', refs: 'References of the same identity', remove: 'Remove subject', mode: 'Guide representation', point: 'Point selected', pending: 'No point', hint: 'Pause at the desired frame and select the subject. Add points at other times for the same identity.', empty: 'Link people or animals to their references by color.', draft: 'Selections saved for future processing. Tracking and meshes are not generated here yet.', anchors: 'point(s)', name: 'Name', color: 'Color', colors: ['Red', 'Blue', 'Green', 'Yellow', 'Magenta', 'Cyan', 'Orange', 'Purple']},
  es: {title: 'Personajes y referencias', add: 'Añadir personaje', select: 'Marcar en el vídeo', selecting: 'Haz clic en el personaje del vídeo', refs: 'Referencias de la misma identidad', remove: 'Eliminar personaje', mode: 'Representación de la guía', point: 'Punto marcado', pending: 'Sin punto', hint: 'Pausa en el fotograma deseado y marca el personaje. Añade puntos en otros momentos para la misma identidad.', empty: 'Vincula personas o animales con sus referencias por color.', draft: 'Selecciones guardadas para procesamiento futuro. El seguimiento y las mallas aún no se generan aquí.', anchors: 'punto(s)', name: 'Nombre', color: 'Color', colors: ['Rojo', 'Azul', 'Verde', 'Amarillo', 'Magenta', 'Cian', 'Naranja', 'Morado']},
};

export function SubjectVideo({url, range, subjects, pickingId, onAnchor, onDuration}: {url: string; range?: ClipRange; subjects: SubjectBinding[]; pickingId: string | null; onAnchor: (id: string, anchor: SubjectAnchor) => void; onDuration: (duration: number) => void}) {
  const player = useRef<HTMLVideoElement>(null), container = useRef<HTMLDivElement>(null);
  const [time, setTime] = useState(0), [size, setSize] = useState({width: 0, height: 0});
  useEffect(() => { const node = container.current; if (!node) return; const observer = new ResizeObserver(([entry]) => setSize({width: entry.contentRect.width, height: entry.contentRect.height})); observer.observe(node); return () => observer.disconnect(); }, []);
  useEffect(() => {if (pickingId) player.current?.pause();}, [pickingId]);
  useEffect(() => {if (range && player.current) { player.current.pause(); player.current.currentTime = range.start; setTime(range.start); }}, [range?.start, range?.end]);
  function pick(clientX: number, clientY: number) {
    const video = player.current, node = container.current;
    if (!video || !node || !pickingId || video.readyState < 2) return;
    video.pause(); const rect = node.getBoundingClientRect();
    const point = videoPoint(clientX - rect.left, clientY - rect.top, rect.width, rect.height, video.videoWidth, video.videoHeight);
    if (point) onAnchor(pickingId, {...point, time_seconds: video.currentTime, frame_width: video.videoWidth, frame_height: video.videoHeight});
  }
  const video = player.current;
  const scale = video?.videoWidth ? Math.min(size.width / video.videoWidth, size.height / video.videoHeight) : 0;
  return <div className={styles.player} ref={container}>
    <video ref={player} key={url} src={url} controls playsInline onLoadedMetadata={e => {const v = e.currentTarget; v.currentTime = range?.start || 0; onDuration(v.duration);}} onTimeUpdate={e => {const v = e.currentTarget; if (range && (v.currentTime >= range.end || v.currentTime < range.start - .05)) {v.pause(); v.currentTime = range.start;} setTime(v.currentTime);}}/>
    {subjects.flatMap((s, i) => s.anchors.filter(a => Math.abs(a.time_seconds - time) < .15).map((a, j) => <span key={`${s.id}-${j}`} className={styles.marker} style={{background: SUBJECT_COLORS.find(c => c.name === s.color)?.hex, left: (size.width - a.frame_width * scale) / 2 + a.x * a.frame_width * scale, top: (size.height - a.frame_height * scale) / 2 + a.y * a.frame_height * scale}}>{i + 1}</span>))}
    {pickingId && <button type="button" className={styles.pickSurface} aria-label="Select subject in video; Enter selects frame center" onClick={e => pick(e.clientX, e.clientY)} onKeyDown={e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault(); const rect = container.current?.getBoundingClientRect(); if (rect) pick(rect.left + rect.width / 2, rect.top + rect.height / 2);}}}/>}
  </div>;
}

/** What each guide representation sends to H3, in plain words. */
const MODES: Record<GuideRepresentation, Record<Language, string>> = {
  original: {
    en: 'Original: the guide video goes in as it is. Your marks only help the planner; the model does not see who is who, so with two or more people it can swap them.',
    pt: 'Original: o vídeo guia entra como está. As marcações só ajudam o planejamento; o modelo não vê quem é quem, então com duas ou mais pessoas ele pode trocá-las.',
    es: 'Original: el vídeo guía entra tal cual. Las marcas solo ayudan a planificar; el modelo no ve quién es quién, así que con dos o más personas puede intercambiarlas.'},
  '2d': {
    en: '2D: each marked person is tracked (SAM 3.1) and painted with a solid color in the guide; the prompt says which color becomes which reference. Best for keeping people apart; the guide face and expression are covered.',
    pt: '2D: cada pessoa marcada é rastreada (SAM 3.1) e pintada com uma cor sólida no guia; o prompt diz qual cor vira qual referência. Melhor para não trocar as pessoas; o rosto e a expressão do guia ficam cobertos.',
    es: '2D: cada persona marcada se sigue (SAM 3.1) y se pinta con un color sólido en la guía; el prompt dice qué color se vuelve qué referencia. Lo mejor para no confundir personas; la cara y la expresión de la guía quedan cubiertas.'},
  '3d': {
    en: '3D: each marked person becomes a colored 3D body with face (SAM 3D Body), so pose, hands and expression come through with the color. People only, not animals; slower.',
    pt: '3D: cada pessoa marcada vira um corpo 3D colorido com rosto (SAM 3D Body), então pose, mãos e expressão passam junto com a cor. Só pessoas, não animais; mais lento.',
    es: '3D: cada persona marcada se vuelve un cuerpo 3D de color con cara (SAM 3D Body), así que la pose, las manos y la expresión pasan con el color. Solo personas, no animales; más lento.'},
  mask: {
    en: 'Mask (Character Swap only): the video keeps its own pixels and only the area around the marked people is generated again. Good for keeping the scene untouched.',
    pt: 'Mask (só Character Swap): o vídeo mantém os próprios pixels e só a área em volta das pessoas marcadas é gerada de novo. Bom para não mexer no cenário.',
    es: 'Mask (solo Character Swap): el vídeo conserva sus píxeles y solo se regenera la zona alrededor de las personas marcadas. Bueno para no tocar el escenario.'},
};

export default function SubjectBindings({subjects, onChange, representation, onRepresentation, pictures, lang, pickingId, onPick, onPrompt, mode, markOpacity = 1, onMarkOpacity}: {subjects: SubjectBinding[]; onChange: (value: SubjectBinding[]) => void; representation: GuideRepresentation; onRepresentation: (value: GuideRepresentation) => void; pictures: Picture[]; lang: Language; pickingId: string | null; onPick: (id: string | null) => void; onPrompt: () => void; mode?: string; markOpacity?: number; onMarkOpacity?: (value: number) => void}) {
  const t = copy[lang];
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const warning = representation === 'original' && subjects.length > 1
    ? tr('With Original, the colors never reach the model. To keep each person on the right reference, use 2D (or 3D for people).', 'Com Original, as cores não chegam ao modelo. Para manter cada pessoa na referência certa, use 2D (ou 3D para pessoas).', 'Con Original, los colores no llegan al modelo. Para mantener cada persona con su referencia, usa 2D (o 3D para personas).')
    : representation === 'mask' && mode && mode !== 'swap' ? tr('Mask works only in Character Swap. Choose 2D or 3D here.', 'Mask só funciona no Character Swap. Escolha 2D ou 3D aqui.', 'Mask solo funciona en Character Swap. Elige 2D o 3D aquí.')
    : representation !== 'original' && !subjects.length ? tr('Add and mark at least one subject: 2D, 3D and Mask need it.', 'Adicione e marque pelo menos um personagem: 2D, 3D e Mask precisam disso.', 'Añade y marca al menos un personaje: 2D, 3D y Mask lo necesitan.')
    : '';
  function patch(id: string, change: Partial<SubjectBinding>) {onChange(subjects.map(s => s.id === id ? {...s, ...change} : s));}
  function add() {const color = SUBJECT_COLORS.find(c => !subjects.some(s => s.color === c.name)); if (!color) return; const id = crypto.randomUUID(); onChange([...subjects, {id, label: `${lang === 'en' ? 'Subject' : 'Personagem'} ${subjects.length + 1}`, color: color.name, picture_slots: [], anchors: []}]); onPick(id);}
  const complete = subjects.length > 0 && subjects.every(s => s.anchors.length && s.picture_slots.length && s.picture_slots.every(n => pictures.some(p => p.slot === n)));
  return <section className={`${styles.panel} surface`} aria-label={t.title}>
    <div className={styles.heading}><h2>{t.title}</h2><div className={styles.modes} role="group" aria-label={t.mode}>{(['original', '2d', '3d', 'mask'] as const).map(value => <button type="button" key={value} title={MODES[value][lang]} aria-pressed={representation === value} disabled={value === 'mask' && !!mode && mode !== 'swap' && representation !== 'mask'} onClick={() => onRepresentation(value)}>{value === 'original' ? (lang === 'pt' ? 'Original' : lang === 'es' ? 'Original' : 'Original') : value.toUpperCase()}</button>)}</div></div>
    <p className={styles.modeHelp}>{MODES[representation][lang]}</p>
    {warning && <p className={styles.warning} role="alert">{warning}</p>}
    {representation === '2d' && onMarkOpacity && <label className={styles.opacity}><span>{tr('Mark opacity', 'Opacidade da marcação', 'Opacidad de la marca')} <b className="mono">{Math.round(markOpacity * 100)}%</b></span>
      <input type="range" min="0.1" max="1" step="0.05" value={markOpacity} onChange={e => onMarkOpacity(Number(e.target.value))}/>
      <small>{tr('Lower: the guide person shows through the tint (face and expression kept, more of their look can leak). 100%: solid color. You can try it on the real guide before approving.', 'Menor: a pessoa do guia aparece sob a tinta (rosto e expressão mantidos, mas parte da aparência dela pode vazar). 100%: cor sólida. Dá para testar no guia real antes de aprovar.', 'Menor: la persona de la guía se ve bajo el tinte (cara y expresión se mantienen, pero parte de su aspecto puede filtrarse). 100%: color sólido. Puedes probarlo en la guía real antes de aprobar.')}</small></label>}
    <p>{pickingId ? t.selecting : subjects.length ? t.hint : t.empty}</p>
    <div className={styles.list}>{subjects.map((s, index) => <article key={s.id} className={styles.subject} style={{borderLeftColor: SUBJECT_COLORS.find(c => c.name === s.color)?.hex}}>
      <div className={styles.subjectHeading}><strong>{index + 1}</strong><input aria-label={`${t.name} ${index + 1}`} value={s.label} maxLength={80} onChange={e => patch(s.id, {label: e.target.value})}/><button type="button" aria-label={`${t.remove} ${index + 1}`} onClick={() => {onChange(subjects.filter(x => x.id !== s.id)); if (pickingId === s.id) onPick(null);}}>×</button></div>
      <div className={styles.colors} role="group" aria-label={`${t.color} ${index + 1}`}>{SUBJECT_COLORS.map((c, i) => <button type="button" key={c.name} title={t.colors[i]} aria-label={t.colors[i]} aria-pressed={s.color === c.name} disabled={subjects.some(x => x.id !== s.id && x.color === c.name)} style={{background: c.hex}} onClick={() => patch(s.id, {color: c.name})}>{s.color === c.name ? '✓' : ''}</button>)}</div>
      <button type="button" className={styles.pickButton} aria-pressed={pickingId === s.id} onClick={() => onPick(pickingId === s.id ? null : s.id)}>{pickingId === s.id ? t.selecting : t.select} · {s.anchors.length ? `${s.anchors.length} ${t.anchors}` : t.pending}</button>
      <fieldset><legend>{t.refs}</legend><div className={styles.references}>{pictures.map(p => <label key={p.slot}><input type="checkbox" checked={s.picture_slots.includes(p.slot)} onChange={e => patch(s.id, {picture_slots: e.target.checked ? [...s.picture_slots, p.slot].sort((a, b) => a - b) : s.picture_slots.filter(n => n !== p.slot)})}/><img src={p.url} alt={`Picture ${p.slot}`}/><span>Picture {p.slot}</span></label>)}</div></fieldset>
    </article>)}</div>
    <div className={styles.actions}><button type="button" onClick={add} disabled={subjects.length >= SUBJECT_COLORS.length}>+ {t.add}</button><button type="button" disabled={!complete} onClick={onPrompt}>{lang === 'pt' ? 'Ver prompt por cores' : lang === 'es' ? 'Ver prompt por colores' : 'View color prompt'}</button></div>
    <small>{lang === 'pt' ? 'As marcações e referências são enviadas ao backend; confira o guia preparado antes de avaliar o resultado.' : lang === 'es' ? 'Las marcas y referencias se envían al backend; revisa la guía preparada.' : 'Selections and references are sent to the backend; review the prepared guide.'}</small>
  </section>;
}
