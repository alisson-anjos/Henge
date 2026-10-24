"""Fixed-recipe modes: Head Swap and Sharpness (LMS).

Unlike Character Swap / Motion, these follow published workflows with a fixed prompt
(Alissonerdx/Minimax-H3-ComfyUI docs/head-swap.md and docs/lms.md), so planning
does not ask the VLM to compose the H3 prompt.
"""
from PIL import Image,ImageOps

# mode -> (profile, min pictures, max pictures)
MODES={'swap':(None,1,11),'motion':(None,1,11),'headswap':('headswap',1,1),'sharpness':('sharpness',0,0)}
FIXED_RECIPE={'headswap','sharpness'}

LMS_CAPTION='Enhance this video with sharp, crisp details while preserving a natural photorealistic appearance.'

FACE_INSTRUCTION=('Describe this face in a short comma-separated attribute list, in exactly this style: "Male, oval face shape, '
    'average-sized head with strong jawline, light brown skin, dark eyes, black tousled hair, silver hoop earring." Cover, in order: '
    'gender, head/face shape and proportions (e.g. oval/round/square/heart-shaped, narrow/wide, jaw structure, whether the head reads '
    'as small/average/large relative to the shoulders), skin tone, eye color, hair color and style, and any distinctive features '
    '(facial hair, jewelry, makeup, glasses, etc.). Only output the description, nothing else.')

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

def head_swap_prompt(face_details):
    face=' '.join(str(face_details).split()).strip().strip('"')
    if not face:raise ValueError('The VLM returned no facial details for Picture 1')
    return HEAD_SWAP_PROMPT.format(face=face[:1200])

def fixed_plan(mode,prompt,summary,description=''):
    """A reviewed-plan shaped record so the UI and generate() treat every mode alike."""
    roles=[{'slot':1,'role':'identity','description':description}] if mode=='headswap' else []
    return {'prompt':prompt,'summary':summary,'picture_roles':roles,'source_kind':'human','target_kind':'human',
            'use_fibo':False,'fibo_instruction':'','fibo_picture_slots':[],'preparation_recommended':False,
            'preparation_reason':'','warnings':[],'preserve_objects':[],'representation':'original'}

def head_reference(source,dest,size=256):
    """Head Swap workflow: the face reference is letterboxed (black pad, centered) to 256x256."""
    with Image.open(source) as image:
        ImageOps.pad(image.convert('RGB'),(size,size),method=Image.LANCZOS,color=(0,0,0)).save(dest)
    return dest
