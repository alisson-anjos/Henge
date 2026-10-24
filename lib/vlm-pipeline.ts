import stages from './h3-vlm-stages.json' with {type:'json'};
import {PROMPT_TEMPLATE, h3PromptError, invalidReferences, nativePrompt, type Mode} from './prompt.ts';

type Media = {data:string; label:string};
export type VlmStage = {instruction:string; images:Media[]; maxTokens:number; stage:string};
export type VlmInput = {mode:Mode; intent:string; pictures:{slot:number;data:string}[]; frames:{time:number;data:string}[]; metadata?:Record<string,unknown>};

function fill(template:string, values:Record<string,string>):string {
  return template.replace(/\{(picture|request|inventory|guide_analysis|metadata)\}/g, (match,key)=>values[key]??match);
}

export async function runPromptPipeline(input:VlmInput, ask:(stage:VlmStage)=>Promise<string>) {
  const request=nativePrompt(input.intent);
  const pictures=[...input.pictures].sort((a,b)=>a.slot-b.slot), slots=pictures.map(p=>p.slot);
  if(invalidReferences(request,slots).length)throw Error('The request mentions an unattached picture.');
  async function call(stage:VlmStage) {
    const text=(await ask(stage)).trim().replace(/^Answer:\s*/i,'');
    if(!text)throw Error(`The VLM returned no text during ${stage.stage}.`);
    return text;
  }
  const descriptions:{slot:number;description:string}[]=[];
  for(const picture of pictures) {
    const instruction=fill(stages.reference_instruction,{picture:String(picture.slot),request});
    const description=await call({instruction,images:[{data:picture.data,label:`Picture ${picture.slot}`}],maxTokens:384,stage:`vlm_picture_${picture.slot}`});
    descriptions.push({slot:picture.slot,description});
  }
  const inventory=`Attached references: ${slots.length} (${slots.map(s=>`Picture ${s}`).join(', ')}).\n\n`+
    descriptions.map(p=>`<Picture ${p.slot}>: ${p.description}`).join('\n\n');
  const frames=[...input.frames].sort((a,b)=>a.time-b.time);
  const guide=await call({instruction:fill(stages.guide_instruction,{request}),images:frames.map((f,i)=>({data:f.data,label:`Guide Video 1 sampled frame ${i} at ${f.time.toFixed(3)} seconds; not a Picture`})),maxTokens:1024,stage:'vlm_guide'});
  const trigger=input.mode==='motion'?'motion_transfer':'body_swap';
  const labels=slots.map(s=>`<Picture ${s}>`).join(', ');
  const policy=PROMPT_TEMPLATE.replaceAll('@PictureN','<Picture N>').replaceAll('@Video1','<Video 1>');
  const instruction=`Task mode: ${trigger}. Begin exactly with ${trigger}:\nEXACT ATTACHED REFERENCE SET: ${labels}. There are ${slots.length} image(s). Use only these concrete Picture labels; do not output generic Picture N or invent another image. <Video 1> is the guide, not an extra Picture.\n`+policy+'\n'+
    fill(stages.composition_context,{request,inventory,guide_analysis:guide,metadata:JSON.stringify(input.metadata??{})})+'\n'+stages.final_audit;
  const prompt=await call({instruction,images:[],maxTokens:3072,stage:'vlm_prompt'});
  const formatError=h3PromptError(prompt,input.mode);
  if(formatError)throw Error(formatError);
  if(invalidReferences(prompt,slots).length)throw Error('The VLM mentioned an unattached picture.');
  return {prompt,reference_inventory:inventory,reference_descriptions:descriptions,guide_analysis:guide,pipeline_version:stages.version};
}
