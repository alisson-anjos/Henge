import type {Language} from './design-copy';

export const colorGuideRecommendation: Record<Language, string> = {
  en: 'For color marks, we recommend Motion Transfer TARA with the TARA method and an explicit prompt for each character. For multiple subjects, Motion Transfer TARA was trained for this task. Character Swap is an alternative only when all subjects are people, but does not always keep each person assigned to the correct reference.',
  pt: 'Para marcações de cor, recomendamos Motion Transfer TARA com o método TARA e um prompt explícito para cada personagem. Motion Transfer TARA foi treinado para trocas de vários sujeitos. Character Swap é uma alternativa somente quando todos são pessoas, mas nem sempre mantém cada pessoa associada à referência certa.',
  es: 'Para marcas de color, recomendamos Motion Transfer TARA con el método TARA y un prompt explícito para cada personaje. Motion Transfer TARA fue entrenado para reemplazar varios sujetos. Character Swap es una alternativa solo cuando todos son personas, pero no siempre mantiene a cada persona vinculada a la referencia correcta.',
};

export const multiCharacterPromptNotice: Record<Language, string> = {
  en: 'Prompts are extremely important for Character Swap with multiple characters. Describe each reference clearly and state which marked person it replaces. Identity follows the marked person even when they change position, move to the foreground, or turn their back.',
  pt: 'Para Character Swap com múltiplos personagens, os prompts são extremamente importantes. Descreva cada referência com clareza e indique qual pessoa marcada ela substitui. A identidade acompanha a pessoa marcada, mesmo quando ela muda de posição, passa para a frente ou fica de costas.',
  es: 'Los prompts son extremadamente importantes para Character Swap con varios personajes. Describe cada referencia con claridad e indica a qué persona marcada sustituye. La identidad sigue a la persona marcada aunque cambie de posición, pase al primer plano o se dé la vuelta.',
};
