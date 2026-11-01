// What each trained model is actually good at, shown as tags on the model picker.
// The tag ids come from the backend (MODELS[..]['tags']); this file only says what a tag means, in the
// interface language, and the backend reads the same JSON to check that every tag has words in every
// language. A model that can do something without having been trained for it must say so in the tag.
import type {Language} from './design-copy';
import DATA from './model-tags.json';

export type ModelTag = {tag: string; tip: string};
export const MODEL_TAGS = DATA as unknown as Record<Language, Record<string, ModelTag>>;
