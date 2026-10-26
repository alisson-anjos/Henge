import type {Language} from './design-copy';
const statuses: Record<string, [string,string,string]> = {
  queued_plan: ['Waiting for analysis','Aguardando análise','Esperando análisis'],
  queued_render: ['Waiting to generate','Aguardando geração','Esperando generación'],
  queued_redo: ['Shot queued to be redone','Trecho na fila para refazer','Tramo en cola para rehacer'],
  queued_mask: ['Updating the preview','Atualizando a prévia','Actualizando la vista previa'],
  waiting_gpu: ['Waiting for the GPU','Aguardando a GPU','Esperando la GPU'],
  running: ['In progress','Em andamento','En curso'],
  awaiting_approval: ['Ready to review','Pronto para revisar','Listo para revisar'],
  completed: ['Video ready','Vídeo pronto','Vídeo listo'],
  failed: ['Could not finish','Não foi possível concluir','No se pudo completar'],
  cancelled: ['Cancelled','Cancelado','Cancelado'],
};
const stages: Record<string, [string,string,string]> = {
  planning: ['Analyzing your edit','Analisando sua edição','Analizando tu edición'],
  preparing: ['Preparing generation','Preparando geração','Preparando generación'],
  vlm_guide: ['Analyzing the guide video','Analisando o vídeo guia','Analizando el vídeo guía'],
  vlm_prompt: ['Preparing your description','Preparando sua descrição','Preparando tu descripción'],
  vlm_route: ['Checking reference preparation','Verificando a preparação das referências','Revisando la preparación de referencias'],
  fibo_edit: ['Adapting the reference','Adaptando a referência','Adaptando la referencia'],
};
function translate(labels: [string,string,string], lang: Language) {return labels[lang === 'pt' ? 1 : lang === 'es' ? 2 : 0];}
export function jobStatusLabel(status: string, lang: Language) {return translate(statuses[status] || statuses.running,lang);}
export function jobStageLabel(stage: string, lang: Language) {
  if (stage.startsWith('vlm_picture_')) return translate(['Analyzing reference pictures','Analisando as imagens de referência','Analizando las imágenes de referencia'],lang);
  if (stage.startsWith('h3_segment_')) return translate(['Generating video','Gerando vídeo','Generando vídeo'],lang);
  return translate(stages[stage] || ['Processing your request','Processando seu pedido','Procesando tu solicitud'],lang);
}
export const formatEta = (seconds: number) => seconds >= 90 ? `${Math.floor(seconds / 60)}m ${String(Math.round(seconds % 60)).padStart(2, '0')}s` : `${Math.max(1, Math.round(seconds))}s`;
export const formatSpeed = (secondsPerStep: number) => secondsPerStep >= 1 ? `${secondsPerStep.toFixed(1)} s/it` : `${(1 / secondsPerStep).toFixed(2)} it/s`;
