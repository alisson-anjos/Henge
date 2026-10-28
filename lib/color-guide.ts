import type {Language} from './design-copy';

export const colorGuideRecommendation: Record<Language, string> = {
  en: 'For color marks, we recommend Motion Transfer TARA with the TARA method and an explicit prompt for each character. This gave the best result in our 2D color-mark tests. Character Swap can also work, but does not always keep each person assigned to the correct reference.',
  pt: 'Para marcações de cor, recomendamos Motion Transfer TARA com o método TARA e um prompt explícito para cada personagem. Essa combinação deu o melhor resultado nos nossos testes com marcações 2D. Character Swap também pode funcionar, mas nem sempre mantém cada pessoa associada à referência certa.',
  es: 'Para marcas de color, recomendamos Motion Transfer TARA con el método TARA y un prompt explícito para cada personaje. Esta combinación dio el mejor resultado en nuestras pruebas con marcas 2D. Character Swap también puede funcionar, pero no siempre mantiene a cada persona vinculada a la referencia correcta.',
};
