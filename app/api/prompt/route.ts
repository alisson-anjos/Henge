import {runPromptPipeline} from '../../../lib/vlm-pipeline';
import {unauthorized} from '../../../lib/access';
export const runtime = 'nodejs';
export async function POST(request: Request) {
  const denied = unauthorized(request); if (denied) return denied;
  const endpoint=process.env.VLM_CHAT_URL, model=process.env.VLM_MODEL;
  if(!endpoint||!model)return Response.json({error:'Automatic prompting needs a VLM connection. Configure VLM_CHAT_URL and VLM_MODEL on the server.'},{status:503});
  try {
    const raw=await request.text();
    if(raw.length>24_000_000)return Response.json({error:'Media payload exceeds 24 MB.'},{status:413});
    const body=JSON.parse(raw);
    if(!['motion','swap'].includes(body.mode)||typeof body.intent!=='string'||!body.intent.trim()||body.intent.length>12000)throw Error('Choose a mode and provide a brief of up to 12,000 characters.');
    if(!Array.isArray(body.pictures)||!body.pictures.length||body.pictures.length>11||!Array.isArray(body.frames)||!body.frames.length||body.frames.length>12)throw Error('Provide 1–11 pictures and 1–12 guide frames.');
    const slots:number[]=[];
    const validImage=(data:unknown)=>typeof data==='string'&&/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(data)&&data.length<=3_000_000;
    for(const p of body.pictures) {
      if(!Number.isInteger(p.slot)||p.slot<1||p.slot>11||slots.includes(p.slot)||!validImage(p.data))throw Error('Invalid reference picture or slot.');
      slots.push(p.slot);
    }
    for(const f of body.frames)if(typeof f.time!=='number'||!Number.isFinite(f.time)||f.time<0||!validImage(f.data))throw Error('Invalid guide frame or timestamp.');
    const result=await runPromptPipeline({...body,metadata:{sampled_timestamps:body.frames.map((f:{time:number})=>f.time),audio_supplied_to_vlm:false}},async stage=>{
      const content:Record<string,unknown>[]=[{type:'text',text:stage.instruction}];
      for(const image of stage.images)content.push({type:'text',text:image.label},{type:'image_url',image_url:{url:image.data}});
      const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',...(process.env.VLM_API_KEY?{Authorization:`Bearer ${process.env.VLM_API_KEY}`}:{})},body:JSON.stringify({model,messages:[{role:'user',content}],temperature:.1,max_tokens:stage.maxTokens}),signal:AbortSignal.any([request.signal,AbortSignal.timeout(120000)])});
      if(!response.ok)throw Error(`VLM provider returned HTTP ${response.status} during ${stage.stage}.`);
      const data=await response.json();const text=data.choices?.[0]?.message?.content;
      if(typeof text!=='string')throw Error(`The VLM returned no text during ${stage.stage}.`);
      return text;
    });
    return Response.json(result);
  } catch(error) {
    return Response.json({error:error instanceof Error&&error.name==='TimeoutError'?'The VLM request timed out.':error instanceof Error?error.message:'Unable to generate a prompt.'},{status:400});
  }
}
