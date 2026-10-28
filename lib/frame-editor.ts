/** Names reported by the backend. An older/missing identifier must not imply a different model. */
export const frameEditorNames: Record<string, string> = {klein3: 'FLUX.3 Klein', klein: 'FLUX.2 Klein'};
export function frameEditorName(editor: unknown, fallback: string): string {
  return typeof editor === 'string' ? frameEditorNames[editor] || fallback : fallback;
}
