import type {Mode} from './prompt';
import type {SubjectBinding, GuideRepresentation} from './subject-bindings';

export type DirectionRequest = {
  schema_version: number;
  project: string;
  mode: Mode;
  quality: string;
  processing: {
    mode: 'context_window' | 'single';
    max_shots: number;
    requested_seconds_per_shot: number;
    frames_per_shot: number;
    timeline_fps: number;
    frame_grid: string;
    trim_to_source_length: boolean;
    join: string;
    execution_status: string;
    context_frames: number;
  };
  audio_conditioning: {enabled: boolean; source: string | null};
  output_audio: {keep_source: boolean};
  prompt: string;
  editor_prompt: string;
  subject_guidance?: {representation: GuideRepresentation; bindings: SubjectBinding[]; status: 'selection_only'; marker_colors_are_output_appearance: false};
  video: {name: string; source_signature?: string; conditioning: string; source_duration?: number; start_seconds: number; end_seconds: number; duration: number};
  pictures: {slot: number; token: string; name: string}[];
  generation_status: 'not_submitted';
};

export type SavedDirection = {
  id: string;
  created: string;
  request: DirectionRequest;
  thumbnail: string;
  rating: number;
  tags: string[];
};
export const HISTORY_KEY = 'henge-history-v1';
export const FEEDBACK = ['identity', 'motion', 'artifacts', 'prompt'] as const;
export const HISTORY_LIMIT = 30;

// Only restore directions this app understands; saved browser data is not trusted input.
export function readHistory(raw: string | null): SavedDirection[] {
  try {
    const entries: unknown = JSON.parse(raw || '[]');
    if (!Array.isArray(entries)) return [];
    return entries.filter((value): value is SavedDirection => {
      if (!value || typeof value !== 'object') return false;
      const item = value as SavedDirection, r = item.request;
      return typeof item.id === 'string' && typeof item.created === 'string'
        && Number.isFinite(Date.parse(item.created)) && !!r
        && typeof r.project === 'string' && ['swap', 'motion', 'headswap', 'sharpness'].includes(r.mode)
        && ['480p', '720p', '1080p'].includes(r.quality)
        && typeof r.editor_prompt === 'string' && typeof r.prompt === 'string'
        && !!r.video && typeof r.video.name === 'string'
        && Number.isFinite(r.video.start_seconds) && Number.isFinite(r.video.end_seconds)
        && r.video.start_seconds >= 0 && r.video.end_seconds > r.video.start_seconds
        && Number.isFinite(r.video.duration) && r.video.duration > 0
        && !!r.processing && Number.isFinite(r.processing.requested_seconds_per_shot)
        && r.processing.requested_seconds_per_shot > 0
        && Number.isFinite(r.processing.timeline_fps) && r.processing.timeline_fps > 0
        && !!r.audio_conditioning && typeof r.audio_conditioning.enabled === 'boolean'
        && !!r.output_audio && typeof r.output_audio.keep_source === 'boolean'
        && Array.isArray(r.pictures) && r.pictures.length <= 11
        && r.pictures.every(p => Number.isInteger(p.slot) && p.slot >= 1 && p.slot <= 11 && typeof p.name === 'string')
        && typeof item.thumbnail === 'string'
        && (item.thumbnail === '' || /^data:image\/jpeg;base64,[a-z0-9+/=]+$/i.test(item.thumbnail))
        && Number.isInteger(item.rating) && item.rating >= 0 && item.rating <= 5
        && Array.isArray(item.tags) && item.tags.every(t => (FEEDBACK as readonly string[]).includes(t));
    }).slice(0, HISTORY_LIMIT);
  } catch { return []; }
}

export function downloadJSON(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'}));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
