import policy from './h3-prompt-policy.json' with {type: 'json'};

export type Mode = "motion" | "swap";
export const MAX_PICTURES = 11;
export function nativePrompt(text: string): string {
  return text.replace(/@Picture(1[01]|[1-9])\b/g, (_, n) => `<Picture ${n}>`)
    .replace(/@Video1\b/g, "<Video 1>");
}
export function invalidReferences(text: string, slots: number[]): string[] {
  return [...new Set(text.match(/@Picture\d+\b|<Picture\s+\d+>/g) || [])]
    .filter(tag => !slots.includes(Number(tag.match(/\d+/)?.[0])));
}
export const H3_SECTIONS = policy.sections;
export const PROMPT_TEMPLATE = policy.rules.map(rule => rule
  .replaceAll('{picture}', '@PictureN')
  .replaceAll('{video}', '@Video1')).join('\n');

export function h3PromptError(text: string, mode: Mode): string | null {
  const trigger = mode === 'motion' ? 'motion_transfer:' : 'body_swap:';
  if (!text.startsWith(trigger)) return `The generated prompt must start with ${trigger}`;
  const matches = [...text.matchAll(/\b(subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):/g)];
  if (matches.length !== H3_SECTIONS.length || matches.some((m, i) => m[1] !== H3_SECTIONS[i])) return 'The generated prompt must contain all six H3 sections in order.';
  if (matches.some((m, i) => !text.slice(m.index! + m[0].length, matches[i + 1]?.index ?? text.length).trim())) return 'The generated H3 sections must not be empty.';
  return null;
}
