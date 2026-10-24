"""The native-workflow prompt sequence: one picture/call, guide only, text composition."""
import json,re
from pathlib import Path
from prompt_policy import H3_POLICY

STAGES=json.loads((Path(__file__).resolve().parents[1]/'lib/h3-vlm-stages.json').read_text())


def fill(template,**values):
    # One pass: placeholders inside model/user descriptions remain plain data.
    return re.sub(r'\{(picture|request|inventory|guide_analysis|metadata)\}',lambda m:str(values.get(m[1],m[0])),template)


def reference_instruction(slot,request):return fill(STAGES['reference_instruction'],picture=slot,request=request)


def composition_instruction(mode,request,slots,inventory,guide_analysis,metadata):
    trigger='motion_transfer' if mode=='motion' else 'body_swap'
    labels=', '.join(f'<Picture {slot}>' for slot in slots)
    return (f'Task mode: {trigger}. Begin exactly with {trigger}:\n'
            f'EXACT ATTACHED REFERENCE SET: {labels}. There are {len(slots)} image(s). '
            'Use only these concrete Picture labels; do not output generic Picture N or invent another image. '
            '<Video 1> is the guide, not an extra Picture.\n'+H3_POLICY+'\n'+
            fill(STAGES['composition_context'],request=request,inventory=inventory,guide_analysis=guide_analysis,metadata=json.dumps(metadata,ensure_ascii=False))+
            '\n'+STAGES['final_audit'])


def prompt_pipeline(ask,request,mode,pictures,guide,metadata,enhance=True):
    """ask(instruction, image, stage, tokens) is local Comfy or external VLM.

    Pictures is an ordered list of (exact slot, isolated analysis image). The
    final call has NO image, only independently grounded descriptions.
    """
    descriptions=[]
    for slot,image in pictures:
        text=ask(reference_instruction(slot,request),image,f'vlm_picture_{slot}',384)
        descriptions.append(dict(slot=slot,description=text))
    slots=[slot for slot,_ in pictures]
    inventory=(f"Attached references: {len(slots)} ({', '.join(f'Picture {s}' for s in slots)}).\n\n"+
               '\n\n'.join(f"<Picture {x['slot']}>: {x['description']}" for x in descriptions))
    observation=ask(fill(STAGES['guide_instruction'],request=request),guide,'vlm_guide',1024)
    prompt=request
    if enhance:
        prompt=ask(composition_instruction(mode,request,slots,inventory,observation,metadata),None,'vlm_prompt',3072)
    return dict(prompt=prompt,reference_inventory=inventory,reference_descriptions=descriptions,guide_analysis=observation,metadata=metadata,pipeline_version=STAGES['version'])
