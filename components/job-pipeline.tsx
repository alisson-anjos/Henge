'use client';
import type {Language} from '../lib/design-copy';
import {formatEta} from '../lib/job-status';
import type {GenerationJob} from './generation-panel';

/** Where a job is in Henge's pipeline, as a vertical timeline: analyze -> review -> prepare -> generate -> ready.
 * Each step is done, active, waiting, failed or skipped, with a short detail line. */
type StepState = 'done' | 'active' | 'waiting' | 'failed' | 'skipped' | 'todo';

const ANALYZE = /^(planning|vlm_|find_people|subject_looks|translate)/;
const PREPARE = /^(preparing|reference_|reference_edit|mask_preview|marks_preview)/;

/** Index of the step the job is on (0..4) and whether it is waiting in a queue there. */
function position(job: GenerationJob): {at: number; waiting: boolean} {
  const stage = job.stage || '';
  switch (job.status) {
    case 'queued_plan': case 'waiting_gpu': return {at: job.plan ? 2 : 0, waiting: true};
    case 'awaiting_approval': case 'queued_mask': return {at: 1, waiting: false};
    case 'queued_render': case 'queued_redo': return {at: 2, waiting: true};
    case 'completed': return {at: 5, waiting: false};
  }
  if (stage.startsWith('h3_segment_') || (job.segment && job.total_segments)) return {at: 3, waiting: false};
  if (PREPARE.test(stage)) return {at: 2, waiting: false};
  if (ANALYZE.test(stage) || !job.plan) return {at: 0, waiting: false};
  return {at: job.result_url ? 4 : 3, waiting: false};
}

export default function JobPipeline({job, lang}: {job: GenerationJob; lang: Language}) {
  const tr = (en: string, pt: string, es: string) => ({en, pt, es})[lang];
  const {at, waiting} = position(job);
  const failed = job.status === 'failed', cancelled = job.status === 'cancelled';
  const autoApproved = !!job.options?.auto_approve && at > 1;
  const shots = job.total_segments ? `${tr('shot', 'trecho', 'tramo')} ${Math.min(job.segment || 0, job.total_segments)}/${job.total_segments}` : '';
  const pct = job.progress ? `${Math.round(job.progress * 100)}%` : '';
  const eta = job.eta_seconds ? `~${formatEta(job.eta_seconds)} ${tr('left', 'restantes', 'restantes')}` : '';
  const queue = tr('in the queue', 'na fila', 'en cola');
  const steps: {label: string; detail: (s: StepState) => string}[] = [
    {label: tr('Analyze video and pictures', 'Analisar vídeo e imagens', 'Analizar vídeo e imágenes'),
     detail: s => s === 'active' ? (waiting ? queue : tr('the planner watches the guide and reads each picture', 'o planejador assiste o guia e lê cada imagem', 'el planificador ve la guía y lee cada imagen')) : s === 'done' ? tr('plan written', 'plano escrito', 'plan escrito') : ''},
    {label: tr('Review the plan', 'Revisar o plano', 'Revisar el plan'),
     detail: s => s === 'active' ? tr('check it below, then Generate video', 'confira abaixo e clique em Gerar vídeo', 'revísalo abajo y pulsa Generar vídeo') : s === 'skipped' ? tr('auto-approved', 'aprovado automaticamente', 'aprobado automáticamente') : s === 'done' ? tr('approved', 'aprovado', 'aprobado') : ''},
    {label: tr('Prepare references', 'Preparar referências', 'Preparar referencias'),
     detail: s => s === 'active' ? (waiting ? queue : tr('background removal, marks, reference adaptation if needed', 'remoção de fundo, marcações, adaptação da referência se preciso', 'quitar fondo, marcas, adaptación de la referencia si hace falta')) : ''},
    {label: tr('Generate the video', 'Gerar o vídeo', 'Generar el vídeo'),
     detail: s => s === 'active' ? [shots, pct, eta].filter(Boolean).join(' · ') || tr('starting', 'começando', 'empezando') : s === 'done' && job.total_segments ? `${job.total_segments} ${job.total_segments > 1 ? tr('shots', 'trechos', 'tramos') : tr('shot', 'trecho', 'tramo')}` : ''},
    {label: tr('Join, add audio, finish', 'Juntar, pôr áudio, finalizar', 'Unir, añadir audio, terminar'),
     detail: s => s === 'done' && job.run_seconds ? `${tr('total', 'total', 'total')} ${formatEta(job.run_seconds)}` : ''},
  ];
  const stateOf = (i: number): StepState => {
    if (i === 1 && autoApproved) return 'skipped';
    if (i < at) return 'done';
    if (i === at) return failed ? 'failed' : cancelled ? 'todo' : 'active';
    return 'todo';
  };
  return <ol className={'job-pipeline' + (failed ? ' failed' : cancelled ? ' cancelled' : '')} aria-label={tr('Progress', 'Progresso', 'Progreso')}>
    {steps.map((step, i) => {
      const s = stateOf(i), detail = s === 'failed' ? tr('stopped here', 'parou aqui', 'se detuvo aquí') : step.detail(s);
      return <li key={i} className={s} aria-current={s === 'active' ? 'step' : undefined}>
        <span className="pipeline-dot" aria-hidden="true">{s === 'done' || s === 'skipped' ? '✓' : s === 'failed' ? '!' : s === 'active' ? <i/> : i + 1}</span>
        <span className="pipeline-text"><strong>{step.label}</strong>{detail && <small>{detail}</small>}
          {s === 'active' && i === 3 && job.progress > 0 && <span className="pipeline-bar"><b style={{width: `${Math.round(job.progress * 100)}%`}}/></span>}</span>
      </li>;
    })}
  </ol>;
}
