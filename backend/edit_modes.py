"""Fixed-recipe modes (Head Swap, Sharpness) and the VFX Edit FFP prompt.

Unlike Character Swap / Motion, these follow published workflows with a fixed prompt
(Alissonerdx/Minimax-H3-ComfyUI docs/head-swap.md and docs/lms.md), so planning
does not ask the VLM to compose the H3 prompt.
"""
import re
from PIL import Image,ImageOps

# mode -> (profile, min pictures, max pictures)
MODES={'swap':(None,1,11),'motion':(None,1,11),'headswap':('headswap',1,1),'sharpness':('sharpness',0,0)}
FIXED_RECIPE={'headswap','sharpness'}

LMS_CAPTION='Enhance this video with sharp, crisp details while preserving a natural photorealistic appearance.'

FACE_INSTRUCTION=('Describe this face in a short comma-separated attribute list, in exactly this style: "Male, oval face shape, '
    'average-sized head with strong jawline, light brown skin, dark eyes, black tousled hair, silver hoop earring." Cover, in order: '
    'gender, head/face shape and proportions (e.g. oval/round/square/heart-shaped, narrow/wide, jaw structure, whether the head reads '
    'as small/average/large relative to the shoulders), skin tone, eye color, hair color and style, and any distinctive features '
    '(facial hair, jewelry, makeup, glasses, etc.). Never name or guess real people, celebrities or fictional characters. Only output the description, nothing else.')

HEAD_SWAP_PROMPT="""head_swap:

subject_definitions:

<Subject 1> is the reference head identity from <Picture 1>, including the complete head, facial identity, facial structure, head shape, hairstyle, hairline, skin appearance, proportions, and all distinctive visual features.

Facial details of <Subject 1>:
{face}

<Subject 2> is the original person in <Video 1>, whose body, neck, clothing, pose, physical proportions below the head, actions, motion, timing, and interaction with the environment must remain unchanged.

<Video 1> is the source video for the target video edit, providing the original body performance, motion, camera movement, framing, timing, lighting, environment, scene composition, and temporal structure.

summary:

[video editing + reference generation]

The target video is an edited version of <Video 1>. Replace only the entire head of <Subject 2> with the reference head identity defined by <Subject 1> from <Picture 1>. Preserve the source video's body, clothing, performance, motion, camera behavior, environment, lighting, timing, and composition.

retention_analysis:

<Subject 1> (appears throughout the target video): attribute_transfer - the complete head identity from <Picture 1>, including facial identity, facial structure, hairstyle, head shape, proportions, skin appearance, and distinctive features, is transferred consistently onto the body of <Subject 2>.

<Subject 2> (appears throughout the target video): partially_preserved - the original body, neck position, clothing, pose, motion, gestures, actions, and physical performance are preserved, while only the original head is replaced.

<Video 1> (entire target timeline): partially_preserved - the original video timing, body motion, camera movement, framing, lighting, background, environment, scene composition, and temporal structure are preserved; only the subject's head appearance is modified.

detailed_description:

Preserve <Video 1> as the complete temporal and compositional foundation of the target video. <Subject 2> retains the exact original body, clothing, pose, body proportions, movement, gestures, actions, speed, timing, and interaction with the environment.

Replace only the entire original head of <Subject 2> with <Subject 1>, the reference head identity from <Picture 1>. Preserve the complete recognizable identity of <Subject 1>, including facial structure, skull and head shape, hairstyle, hairline, skin appearance, facial proportions, eyes, eyebrows, nose, mouth, jawline, ears, and distinctive identifying features.

The transferred head follows the original head motion and performance of <Subject 2> throughout <Video 1>, including head rotation, tilt, pitch, yaw, natural translation, facial orientation, gaze direction, and perspective changes. Maintain anatomically correct head scale and a seamless connection between the transferred head and the original neck.

Preserve the lighting conditions of <Video 1> on the transferred head. The head naturally responds to changes in illumination, shadows, highlights, color temperature, exposure, depth of field, motion blur, occlusion, camera angle, and perspective while continuously maintaining the identity established by <Picture 1>.

Maintain strong temporal consistency across every frame. The identity, facial geometry, hairstyle, head size, skin appearance, and distinguishing features of <Subject 1> remain stable during motion and viewpoint changes. Prevent identity drift, facial morphing, hairstyle changes, head-size fluctuations, geometry instability, texture crawling, temporal flickering, frame-to-frame inconsistency, or sudden changes in facial appearance.

Do not alter the body, clothing, hands, pose, gestures, action, background, objects, environment, camera trajectory, framing, lens behavior, scene timing, or composition inherited from <Video 1>. The final result should appear as though <Subject 1>'s head naturally belonged to <Subject 2>'s body during the original recorded performance.

overall_soundscape:

Preserve the original audiovisual timing and visible action structure of <Video 1>. No visual modifications are made outside the head replacement.

non_diegetic_music:
N/A"""

# Character Swap v1.1 published recipe (workflows/minimax_h3_character_swap_workflow_native_nodes_v1.1.json):
# a one-line body_swap prompt; only {details} comes from the VLM, and the guide performer is never described.
CHARACTER_INSTRUCTION=("Analyze the character in this reference image and describe the character's complete visible appearance from head to toe "
    "as one detailed, comma-separated attribute list, in this exact order: 1. gender, apparent height, body type, physique, shoulder width, waist "
    "and body proportions; 2. head and face shape, jawline, facial structure, skin tone, eye color and distinctive facial characteristics; "
    "3. hair color, hairstyle, length, texture, beard, mustache and other facial hair; 4. upper-body clothing with garment types, exact colors, fit, "
    "fabric, textures, collars, sleeves, buttons, zippers, pockets, logos, patterns and layers; 5. lower-body clothing with colors, materials, fit and "
    "design details; 6. footwear; 7. all visible accessories; 8. distinctive features such as tattoos, scars, wrinkles or makeup. "
    "Describe only what is visually identifiable; never invent unseen body parts, clothing or accessories; omit what cannot be determined. "
    "Never name or guess real people, celebrities, actors or fictional characters; describe appearance only. "
    "Do not describe the background, camera, lighting or image composition. Start with the gender (\"Male, ...\" or \"Female, ...\"), "
    "with no article before it and no full stop after it. Output only the comma-separated list, on one line, nothing else.")

CHARACTER_SWAP_PROMPT=("body_swap: subject_definitions: <Subject 1> is the {details} shown in <Picture 1>, whose identity, face, head, hair or fur, skin, "
    "body shape, proportions and clothing define the character in the target video. The guide video provides the scene and the performance: its "
    "background, environment, lighting, camera, framing, body pose, hand and arm movement, head rotation, gaze direction, lip movement and facial "
    "expression, frame by frame; only the main subject of the guide video is replaced: its face, hair, body and clothing become <Subject 1>.  "
    "summary: [video generation + reference] Replace the guide subject with <Subject 1>, keeping the scene, camera and the complete motion and "
    "performance of the guide video.  detailed_description: [Shot 1] <Subject 1> takes the exact place of the guide subject and moves with the same "
    "timing, body pose, gestures, head motion, gaze, speech and facial expressions, while keeping the complete identity from <Picture 1>: facial "
    "structure, hair or fur, skin, body shape and clothing stay stable in every frame. The background, lighting, colors and camera of the guide "
    "video are preserved. Prevent identity drift, clothing changes, texture crawling and flicker.")

EMPTY_ITEMS={'none','n/a','na','null','unknown','not visible','-',''}
def clean_details(details,limit):
    """A VLM description, made safe for the prompt: one line, without empty list items ('none', 'n/a') and without
    the same item repeated (a small VLM can loop on 'none, none, none...' until its token limit)."""
    text=' '.join(str(details).split()).strip().strip('"')
    out=[];seen=[]
    for sentence in re.split(r'(?<=;)\s*',text):
        items=[]
        for item in sentence.split(','):
            word=item.strip();key=word.lower().rstrip('.;').strip()
            if key in EMPTY_ITEMS or (items and key==items[-1].lower().rstrip('.;').strip()) or seen.count(key)>=2:continue
            items.append(word);seen.append(key)
        if items:out.append(', '.join(items))
    return ' '.join(out).rstrip('.,; ')[:limit]

def character_swap_prompt(details):
    text=clean_details(details,2000)
    if not text or text.lower() in ('details','{details}'):raise ValueError('The VLM returned no character description for Picture 1')
    return CHARACTER_SWAP_PROMPT.format(details=text)

def head_swap_prompt(face_details):
    face=' '.join(str(face_details).split()).strip().strip('"')
    if not face:raise ValueError('The VLM returned no facial details for Picture 1')
    return HEAD_SWAP_PROMPT.format(face=face[:1200])

def fixed_plan(mode,prompt,summary,description=''):
    """A reviewed-plan shaped record so the UI and generate() treat every mode alike."""
    roles=[{'slot':1,'role':'identity','description':description}] if mode=='headswap' else []
    return {'prompt':prompt,'summary':summary,'picture_roles':roles,'source_kind':'human','target_kind':'human',
            'adapt_reference':False,'adapt_instruction':'','adapt_picture_slots':[],'preparation_recommended':False,
            'preparation_reason':'','warnings':[],'preserve_objects':[],'representation':'original'}

def head_reference(source,dest,size=256):
    """Head Swap workflow: the face reference is letterboxed (black pad, centered) to 256x256."""
    with Image.open(source) as image:
        ImageOps.pad(image.convert('RGB'),(size,size),method=Image.LANCZOS,color=(0,0,0)).save(dest)
    return dest

def character_reference(source,mask,dest,megapixels=.5,gray=(128,128,128)):
    """Character Swap v1.1 reference: foreground over #808080, scaled to 0.5 MP (aspect kept)."""
    with Image.open(source) as image,Image.open(mask) as alpha:
        rgb=image.convert('RGB');alpha=alpha.convert('L').resize(rgb.size,Image.BILINEAR)
        flat=Image.composite(rgb,Image.new('RGB',rgb.size,gray),alpha)
    scale=(megapixels*1024*1024/(flat.width*flat.height))**.5
    flat.resize((max(32,round(flat.width*scale)),max(32,round(flat.height*scale))),Image.LANCZOS).save(dest)
    return dest

FFP_INSTRUCTION=("Rewrite this video edit request as ONE concise English sentence for a video editing model. First state the edit, "
    "then state what must remain unchanged (for example identity, pose, motion, clothing, framing, lighting and background), but never "
    "ask to preserve the very thing being changed. Keep every <Picture N> label exactly as written and do not invent others. Do not mention "
    "<Video 1>. Return only the sentence. Request: {request}")

def ffp_prompt(sentence,first_frame=None):
    """Published VFX Edit rules: start with vfx_edit:, one sentence; an attached first frame must be named and its role explained."""
    text='vfx_edit: '+re.sub(r'^\s*(vfx_edit:)?\s*','',sentence.strip()).strip().strip('"').strip()
    if first_frame:text+=f' <Picture {first_frame}> is the edited first frame of the video: propagate its changes through the whole clip while keeping the original motion, timing and camera.'
    return text


def character_figure_instruction(count,description=''):
    """Adaptation instruction for a human guide driving an animal. <image_1>..<image_count> show the animal; the image after
    them is the guide's first frame, used only for the pose. One full-body humanoid figure on plain gray: a sheet with
    several figures, or animal leg proportions, let the video model put paws or extra bodies in the wrong places."""
    images=', '.join(f'<image_{i}>' for i in range(1,count+1));pose=f'<image_{count+1}>'
    subject=f'the animal in {images}'+(f' ({description.strip().rstrip(".")})' if description.strip() else '')
    return (f'Full-body portrait of {subject} redrawn as an anthropomorphic, upright bipedal character with a human body '
            'structure: human-proportioned torso, full-length arms ending in hands, and long human-length legs with the '
            'knees halfway down, standing on two feet. Keep its exact animal head and face, fur or skin colors, patterns, '
            'markings and every distinguishing feature; paw markings belong only on the hands and feet. '
            f'Give it the same body pose as the person in {pose}: facing direction, arm and leg positions. Take nothing '
            f'else from {pose}: not the face, hair, clothes, body shape or background. Exactly one figure, head to feet '
            'large in frame. Plain flat neutral gray background, no scenery, no floor, no props, no text, soft even '
            'studio lighting.')


def multi_swap_prompt(subjects,representation='2d',labels=False):
    """Character Swap with two or more marked people (the BFS two-character recipe, in the v1.1 body_swap format).
    subjects: [(color, picture_slots, details)] in Subject order. Each subject is defined by its picture and the color
    that marks the person it replaces; the tints are named as editing markers to remove; nothing describes the guide
    performers (their looks would leak)."""
    if len(subjects)<2:raise ValueError('The multi-person template needs at least two subjects')
    # labels: the 2D guide also writes each person's <Picture N> over them (experimental); the prompt names those tags
    # in the binding and as markers to remove, so they are not copied into the video.
    labels=labels and representation=='2d'
    mark='tint' if representation=='2d' else 'color'
    marked='tinted' if representation=='2d' else 'colored'
    defs=[];swaps=[];names=[]
    for i,(color,slots,details) in enumerate(subjects,1):
        pictures=' and '.join(f'<Picture {n}>' for n in slots)
        text=clean_details(details,1500) or 'the character'
        defs.append(f'<Subject {i}> is the character shown in {pictures}: {text}. Their identity, face, hair, body shape, proportions and clothing define the {color}-marked replacement.')
        tag=f" tagged {pictures.replace(' and ',' / ')}" if labels else ''
        swaps.append(f'the {color}-{marked} person{tag} with <Subject {i}>');names.append(f'<Subject {i}>')
    colors=' and '.join(c for c,_,_ in subjects)
    replace='Replace '+', '.join(swaps[:-1])+' and '+swaps[-1]
    markers=f'the translucent {colors} {mark}s and the <Picture> text tags written over them are' if labels else f'the translucent {colors} {mark}s are'
    remove='Remove the temporary color markers and text tags completely: no text, letters or labels anywhere in the video. ' if labels else 'Remove the temporary color markers completely. '
    return (f"body_swap: subject_definitions: {' '.join(defs)} In the guide video, {markers} temporary editing markers, not character appearance. "
            f"{replace}. The guide video provides the scene, framing and the complete performance: body pose, gestures, head motion, gaze, speech and facial expressions.  "
            f"summary: [video generation + references] {replace}, preserving the guide's camera, framing, timing and motion exactly.  "
            f"detailed_description: [Shot 1] {', '.join(names[:-1])} and {names[-1]} take the exact places of the marked people and move with the same timing, body pose, gestures, head motion, gaze, speech and facial expressions; "
            f"each one follows its own marked person through position changes, occlusion and cuts. {remove}"
            f"Keep the framing of the guide: do not widen the shot or add people who are not in the guide; no inset, no small full-body figure, no picture-in-picture. "
            f"Preserve the background, lighting and camera. Prevent identity drift, clothing changes, texture crawling and flicker.")
