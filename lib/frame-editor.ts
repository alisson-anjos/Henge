/** Names reported by the backend. An older/missing identifier must not imply a different model. */
export const frameEditorNames: Record<string, string> = {h3image: 'H3 Image (Pruna)', fibo: 'FIBO 2.0', qwen21: 'Qwen-Image 2.1', klein3: 'FLUX.3 Klein', klein: 'FLUX.2 Klein', bfs: 'BFS Body Swap (Qwen 2.1)', bfs_selective: 'BFS Body Swap Selective (Qwen 2.1)', gpt_image: 'GPT Image (OpenAI)'};
export function frameEditorName(editor: unknown, fallback: string): string {
  return typeof editor === 'string' ? frameEditorNames[editor] || fallback : fallback;
}
