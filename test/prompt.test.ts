import assert from 'node:assert/strict';
import test from 'node:test';
import {h3PromptError, invalidReferences, nativePrompt, PROMPT_TEMPLATE} from '../lib/prompt.ts';

const valid = 'motion_transfer: subject_definitions: <Subject 1> uses @Picture2; <Subject 2> is the scene in @Picture1. summary: [reference generation] Transfer the guide performance. retention_analysis: Stable identities. detailed_description: [Shot 1] Preserve timing in the new scene. overall_soundscape: N/A non_diegetic_music: N/A';
test('H3 format keeps scene and character numbering independent', () => {
  assert.equal(h3PromptError(valid, 'motion'), null);
  assert.deepEqual(invalidReferences(valid, [1, 2]), []);
  assert.ok(nativePrompt(valid).includes('<Subject 1> uses <Picture 2>'));
});
test('short, reordered, empty and wrong-trigger generated prompts are rejected', () => {
  assert.ok(h3PromptError('motion_transfer: Replace the performer.', 'motion'));
  assert.ok(h3PromptError(valid.replace('summary:', 'detailed_description:'), 'motion'));
  assert.ok(h3PromptError(valid.replace('overall_soundscape: N/A', 'overall_soundscape:'), 'motion'));
  assert.ok(h3PromptError(valid, 'swap'));
});
test('all editor reference slots remain stable', () => {
  assert.equal(nativePrompt('@Picture1 @Picture11 @Video1'), '<Picture 1> <Picture 11> <Video 1>');
  assert.deepEqual(invalidReferences('@Picture2 @Picture11', [2]), ['@Picture11']);
});
test('prompt policy does not force the implementation or original scene', () => {
  assert.ok(PROMPT_TEMPLATE.includes('Kawarimi'));
  assert.ok(PROMPT_TEMPLATE.includes('replace the entire source environment'));
  assert.ok(PROMPT_TEMPLATE.includes('Inspect each labelled reference independently'));
});
