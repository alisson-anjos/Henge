"""The native-workflow prompt sequence: one picture/call, guide only, text composition."""
import json,re
from pathlib import Path
from prompt_policy import H3_POLICY

STAGES=json.loads((Path(__file__).resolve().parents[1]/'lib/h3-vlm-stages.json').read_text())


def fill(template,**values):
    # One pass: placeholders inside model/user descriptions remain plain data.
    return re.sub(r'\{(picture|request|inventory|guide_analysis|metadata)\}',lambda m:str(values.get(m[1],m[0])),template)


HEADING=re.compile(r'^\s*(?:#+\s*)?\*{0,2}([A-Za-z][\w /&()-]{1,60}?)\*{0,2}\s*:')
SCENE=re.compile(r'environment|background|backdrop|setting|location|surroundings|scene',re.I)
PERSON=re.compile(r'identity|face|physique|clothing|hair|outfit|body',re.I)


def subject_only(description):
    """Drop the backdrop sections of a person/character picture's description, so the composer cannot take
    a photo's background for the target scene. A picture without person sections (a scene) stays whole."""
    lines=description.splitlines()
    headings=[HEADING.match(line) for line in lines]
    if not any(m and PERSON.search(m[1]) for m in headings):return description
    kept=[];skipping=False
    for line,m in zip(lines,headings):
        if m and not re.match(r'\s*[-*\u2022]\s',line):skipping=bool(SCENE.search(m[1]))
        if not skipping:kept.append(line)
    return re.sub(r'\n{3,}','\n\n','\n'.join(kept)).strip()


WARDROBE=re.compile(r"\b(?:wear|wears|wearing|worn|dressed|attire|outfits?|cloth(?:es|ing)|garments?|bikini|swimsuit|dress|skirt|shirt|t-shirt|jacket|hoodie|pants|shorts|jeans|hair|haired|braids?|ponytail|hairstyle|makeup)\b",re.I)
HAIR_COLOR=re.compile(r'\b(?:blonde|blond|brunette|red-haired|redheaded|dark-haired|fair-haired)\s+',re.I)


def performance_only(observation):
    """Drop the sentences of the guide analysis that describe the source performers' hair or wardrobe: the
    references replace them, and a small VLM otherwise copies them onto the target (braids, a bikini)."""
    kept=[]
    for line in observation.splitlines():
        head=re.match(r'\s*(?:[-*\u2022]\s+)?(?:\*\*[^*]+\*\*:?)?\s*',line)[0];body=line[len(head):]
        sentences=[x for x in re.split(r'(?<=[.!?])\s+',body) if not WARDROBE.search(x)]
        if body.strip() and not sentences:continue
        kept.append(head+' '.join(sentences))
    return HAIR_COLOR.sub('','\n'.join(kept))


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
               '\n\n'.join(f"<Picture {x['slot']}>: {subject_only(x['description'])}" for x in descriptions))
    observation=ask(fill(STAGES['guide_instruction'],request=request),guide,'vlm_guide',1024)
    prompt=request
    if enhance:
        prompt=ask(composition_instruction(mode,request,slots,inventory,performance_only(observation) if slots else observation,metadata),None,'vlm_prompt',3072)
    return dict(prompt=prompt,reference_inventory=inventory,reference_descriptions=descriptions,guide_analysis=observation,metadata=metadata,pipeline_version=STAGES['version'])
