import { PROMPT_TEMPLATE, invalidReferences, h3PromptError } from '../../../lib/prompt';
export const runtime = 'nodejs';
export async function POST(request: Request) {
  const endpoint = process.env.VLM_CHAT_URL;
  const model = process.env.VLM_MODEL;
  if (!endpoint || !model) return Response.json({error:'Automatic prompting needs a VLM connection. Configure VLM_CHAT_URL and VLM_MODEL on the server.'},{status:503});
  try {
    const raw = await request.text();
    if (raw.length > 24_000_000) return Response.json({error:'Media payload exceeds 24 MB.'},{status:413});
    const body = JSON.parse(raw);
    if (!['motion','swap'].includes(body.mode) || typeof body.intent !== 'string' || !body.intent.trim() || body.intent.length > 12000) throw Error('Choose a mode and provide a brief of up to 12,000 characters.');
    if (!Array.isArray(body.pictures) || !body.pictures.length || body.pictures.length > 11 || !Array.isArray(body.frames) || !body.frames.length || body.frames.length > 6) throw Error('Provide 1–11 pictures and 1–6 guide frames.');
    const slots: number[] = [];
    const content: Record<string,unknown>[] = [{type:'text',text:`Mode: ${body.mode === 'swap' ? 'SWAP' : 'MOTION TRANSFER'}\nAudio conditioning: ${body.audioConditioning === true ? 'enabled, using guide video audio at generation time' : 'disabled'}. No audio is supplied to you; do not describe or infer sounds.\nUser intent: ${body.intent}`}];
    const addImage = (data: unknown) => {
      if (typeof data !== 'string' || !/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(data) || data.length > 3_000_000) throw Error('Invalid preview image.');
      content.push({type:'image_url', image_url:{url:data}});
    };
    for (const picture of body.pictures) {
      if (!Number.isInteger(picture.slot) || picture.slot < 1 || picture.slot > 11 || slots.includes(picture.slot)) throw Error('Invalid picture slot.');
      slots.push(picture.slot); content.push({type:'text',text:`Reference @Picture${picture.slot}:`}); addImage(picture.data);
    }
    for (const frame of body.frames) {
      if (typeof frame.time !== 'number' || !Number.isFinite(frame.time) || frame.time < 0) throw Error('Invalid frame timestamp.');
      content.push({type:'text',text:`Guide video sampled frame at ${frame.time.toFixed(2)} seconds (not a reference picture):`}); addImage(frame.data);
    }
    const response = await fetch(endpoint, {method:'POST',headers:{'Content-Type':'application/json',...(process.env.VLM_API_KEY ? {Authorization:`Bearer ${process.env.VLM_API_KEY}`} : {})},body:JSON.stringify({model,messages:[{role:'system',content:PROMPT_TEMPLATE},{role:'user',content}],temperature:.2,max_tokens:2600}),signal:AbortSignal.timeout(120000)});
    if (!response.ok) return Response.json({error:`VLM provider returned HTTP ${response.status}. Check the server connection and model.`},{status:502});
    const result = await response.json();
    const text = result.choices?.[0]?.message?.content;
    if (typeof text !== 'string' || !text.trim()) throw Error('The VLM returned no text prompt.');
    const prompt = text.trim().replace(/^Answer:\s*/i,'');
    const formatError = h3PromptError(prompt, body.mode);
    if (formatError) return Response.json({error: formatError}, {status: 422});
    if (invalidReferences(prompt,slots).length) throw Error('The VLM mentioned an unattached picture. Refine your brief and try again.');
    return Response.json({prompt});
  } catch (error) {
    return Response.json({error:error instanceof Error && error.name === 'TimeoutError' ? 'The VLM request timed out.' : 'Unable to generate a prompt. Check your media and VLM configuration.'},{status:400});
  }
}
