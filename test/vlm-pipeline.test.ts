import assert from 'node:assert/strict';
import test from 'node:test';
import {performanceOnly, runPromptPipeline, subjectOnly, type VlmStage} from '../lib/vlm-pipeline.ts';
const final='motion_transfer: subject_definitions: <Subject 1> uses <Picture 2>. summary: [reference generation] Transfer. retention_analysis: Stable. detailed_description: [Shot 1] The subject moves. overall_soundscape: N/A non_diegetic_music: N/A';
test('reference images are isolated, guide is separate and composition is text only',async()=>{
 const seen:VlmStage[]=[];const replies=['beach','goblin','guide performance',final];
 const result=await runPromptPipeline({mode:'motion',intent:'Use @Picture2; setting @Picture1',pictures:[{slot:2,data:'goblin'},{slot:1,data:'beach'}],frames:[{time:1,data:'guide1'},{time:0,data:'guide0'}]},async stage=>{seen.push(stage);return replies.shift()!;});
 assert.deepEqual(seen.map(s=>s.images.map(i=>i.data)),[['beach'],['goblin'],['guide0','guide1'],[]]);
 assert.ok(seen[0].instruction.includes('ONLY this single image'));
 assert.ok(seen[3].instruction.includes('<Picture 1>: beach'));assert.ok(seen[3].instruction.includes('<Picture 2>: goblin'));
 assert.ok(seen[3].instruction.includes('guide performance'));assert.ok(seen[3].instruction.includes('do not copy source hoodie'));
 assert.equal(result.prompt,final);
});
test('missing request pictures fail before any VLM call',async()=>{
 let calls=0;
 await assert.rejects(()=>runPromptPipeline({mode:'motion',intent:'Use @Picture2',pictures:[{slot:1,data:'one'}],frames:[{time:0,data:'guide'}]},async()=>{calls++;return final;}),/unattached/);
 assert.equal(calls,0);
});
test('invalid generated prompt cannot silently enter execution',async()=>{
 await assert.rejects(()=>runPromptPipeline({mode:'motion',intent:'Use @Picture1',pictures:[{slot:1,data:'one'}],frames:[{time:0,data:'guide'}]},async stage=>stage.stage==='vlm_prompt'?'Replace someone.':'description'),/motion_transfer/);
});
test('a person picture loses its backdrop section; a scene picture stays whole',()=>{
 const person='**Identity:** An old man.\n**Clothing & Accessories:**\n*   **Headwear:** A flat cap.\n**Environment:** A dry desert.\n*   **Ground:** gravel.\n**Reference Role:** identity';
 assert.equal(subjectOnly(person),'**Identity:** An old man.\n**Clothing & Accessories:**\n*   **Headwear:** A flat cap.\n**Reference Role:** identity');
 assert.equal(subjectOnly('**Environment:** A beach at sunset.'),'**Environment:** A beach at sunset.');
});
test('the guide analysis keeps the performance but not the performers\' hair and wardrobe',()=>{
 const guide='**Subject 1: The Blonde Woman**\n*   **Appearance:** She has hair in two braids. She is wearing a blue bikini.\n*   **Action:** She raises her hand. The camera looks down.';
 assert.equal(performanceOnly(guide),'**Subject 1: The Woman**\n*   **Action:** She raises her hand. The camera looks down.');
});
