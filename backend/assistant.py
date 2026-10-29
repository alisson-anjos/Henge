"""Studio assistant: an LLM that drives the Henge studio for the user.

The conversation is kept by the browser in a provider-neutral form and sent back on every step:
  {'role': 'user', 'text': str, 'images': [data_url]}
  {'role': 'assistant', 'text': str, 'tool_calls': [{'id', 'name', 'input'}], 'native': <provider blocks>}
  {'role': 'tool', 'results': [{'id', 'name', 'text', 'images': [data_url], 'is_error': bool}]}
The history is only ever appended to; Claude's own content blocks (thinking included) are kept in 'native' and
sent back unchanged.

Tools are of two kinds. Studio tools change what the user sees (mode, marks, prompt, Generate) and run in the
browser; job tools read and steer jobs on the bridge and run here. One step calls the model until it answers or asks
for studio tools, which the browser runs before the next step.

Providers: Claude through the official Anthropic SDK, and any OpenAI-compatible chat completions API (OpenAI, and
local servers such as LM Studio, Ollama or vLLM)."""
import base64
import json
import uuid
import re
from pathlib import Path

import requests

DEFAULTS = {'provider': 'local', 'model': 'henge-vlm', 'base_url': '', 'api_key': '', 'effort': 'medium',
            'image_enabled': False, 'image_model': 'gpt-image-2.5-flare', 'image_quality': 'medium', 'image_api_key': '',
            # Who marks people: 'sam' = SAM 3.1 detects and numbers them (find_people); 'vision' = the assistant points at
            # them with its own vision. Either way SAM segments and tracks from those points in every frame at generation.
            'marking': 'sam',
            # Who writes the prompts (picture descriptions, the plan, the H3 prompt): 'local' = the Qwen planner in
            # ComfyUI; 'assistant' = this provider and model.
            'planner': 'local'}
PROVIDERS = ('anthropic', 'openai', 'local')
# The built-in provider: the planner VLM (Qwen 3.5 9B) on the same ComfyUI / serverless path, so the assistant works
# without any API key. The bridge sets LOCAL_VLM(prompt, image_relative_path_or_None, max_tokens) -> text.
LOCAL_MODEL = 'henge-vlm'
LOCAL_VLM = None

SYSTEM = """You are the Henge studio assistant. Henge turns a guide video plus reference pictures into a new video with MiniMax H3. You operate the studio for the user: you see its state, look at frames, mark people, set options and start generations. The user watches the screen change as you work.

Modes: swap (Character Swap: a person in the video becomes the character in a picture), motion (Motion Transfer: a subject, including an object or vehicle, follows the guide's motion), headswap (only the head changes; one face picture), sharpness (sharpen the video; no pictures, no marks).

Guide representation (how marked people reach the model):
- original: the default. The video goes in as it is. Use this for ordinary swaps or motion transfer, including vehicles and objects. Multiple subjects may need marks to disambiguate reference assignments.
- 2d: each marked person is tracked and tinted with its color; mark_opacity 0.35 keeps the face and expression visible, 1 is a solid color. Best for keeping several people apart (swap, motion).
- 3d: each person becomes a colored 3D body with face. People only.
- mask: opt-in local replacement using SAM-tracked subject marks. Requires valid marks BEFORE selecting it. Never select mask automatically just because the user asks to replace something or preserve the scene. Without marks it cannot generate. Works in swap, motion and headswap.
TARA Motion Transfer works with original and marked guides; recommend its TARA-trained LoRA with the TARA method. Color-marked tests worked particularly well with this combination.

How to work:
1. Read the studio state. If the guide video or the pictures are missing, ask the user to attach them in the chat or in the studio. Chat videos are automatically loaded as the guide and chat images marked as generation references as reference Pictures in attachment order. Images the user marks as explanation (a frame with people numbered or circled, a sketch) are for you only: they are never Pictures; use them to understand who is who and where, then mark the real guide frames yourself.
2. Look before you act: view_pictures to see the references, then view_frame at the start, middle and end of the selection to understand the guide. Optional video-analysis tools exist only when their runtime is available; use ask_video only if it is listed. Never ask the user to configure Molmo to complete an ordinary edit: your own frame inspection is the fallback. When the user gives a photo of each person to replace (an explanation image of the performer, or a Picture that shows the same person), when available prefer match_people: it finds every person in every shot with local Molmo2 and marks them, one subject per person bound to its picture_slots; check its previews and fix a wrong or missing mark with mark_subject. Optional point_video uses local Molmo2 to propose marks from a target description. Call it per camera shot, inspect the returned preview points and use mark_subject to bind approved points to Pictures. Its object IDs are not global identities or Picture numbers. If they are unavailable, keep the existing manual/SAM marking workflow.
3. To bind people: first view_frame at a few times (start, middle, end) to learn who appears when, then call find_people at a time where everyone you need is visible and check that each number really is the person you mean (not a background figure) before marking; when the video has camera cuts, run find_people once per moment (after each cut) and mark each performer there too; before generating, read get_studio_state and confirm every subject has one mark per moment it appears and no performer has two subjects; it returns the frame with numbered people. Then mark_subject each person you need, with the matching picture slots. Marks must be inside the selected interval.
4. Choose original by default, especially for a single vehicle, object or person. For several subjects with ambiguous assignments, propose marks and a 2d guide. Use mask only when the user explicitly chooses a region-restricted edit and the subject is already marked. To mark an object such as a car, use view_frame with grid=true and mark_subject with x/y inside the object; find_people is for people. If a required mask cannot be prepared, explain the blocker; do not silently switch to original when the user explicitly required masking. With original, do not promise that background pixels remain identical. If find_people fails with two or more people, do not fall back to original silently: say so and ask the user to mark them with 'Mark in video' (or retry), because with original the model can swap who becomes whom.
For color-marked guides, recommend Motion Transfer TARA with the TARA method and explicit per-person reference descriptions; this was the best combination in our 2D color-mark tests. Character Swap may also work but can confuse reference assignments. Recommend this without silently changing the selected model or method.
5. Write the prompt with set_prompt only when the user asked for something the mode needs (motion and swap use the user's request; headswap and sharpness ignore it). Refer to pictures as @Picture1, @Picture2.
6. Before generate, call get_options and read get_studio_state. Check temporal_windows_ready and generation_blockers. Temporal windows are optional and off by default: do not enable them unless requested. If inherited settings block an ordinary generation, disable only the unrequested temporal_windows option, say what changed, and recheck. If the user requested windows, explain missing worker support or the specific incompatible setting instead of silently disabling it. Do not retry generate with unchanged blockers. Before generate, summarize what will run (mode, who becomes whom, guide, quality) in two or three lines. If the user has not asked you to generate, ask first.
7. Videos with camera cuts: people seen only after a cut are not recognised automatically. When marks are used, generate with auto-approve off, wait_for_job 'plan', get_job_shots, and for every shot that starts after a cut call find_people a little after its start and mark_subject each visible person with subject=<their number> (people can change places); then send_marks_to_job. Skip people who are not in that shot.
8. Settings are live, not a fixed list in this prompt. get_options returns the actual generation values and installed capabilities; use its keys with set_options and confirm the returned effective values. get_settings/set_settings access backend connection, assistant and optional video-analysis configuration; change them only when the user asks, never expose stored credentials. You can change anything the user can: options (get_options / set_options: model, TARA, turbo, steps...), interval, shots, output, project name, pictures and subjects. Say what you changed.
9. Jobs run in the background. After generate, check the job once; if it is still running, tell the user they can keep chatting and do not repeatedly poll. When they write again, the studio state contains the current job status. Once the plan is ready, inspect its color or mask preview; once the render is done, inspect the result.
10. Every generation has a visible 8-character reference such as #a1b2c3d4. The user may identify a generation with that reference; job tools accept it with or without # as well as the full id. When a generation starts, mention its visible reference so the user can refer to it later.
The studio state's selected_job is the generation selected on screen. When the user says "this generation", "essa geração" or an equivalent expression, use selected_job.id; do not ask them to copy its id.
11. If the user says an active generation looks wrong or that you made a mistake, inspect its state and call confirm_cancel_job to ask whether they want to cancel it. Criticism is not permission to cancel: only call cancel_job when that approval result is true. If they decline, leave it running and continue the conversation.
12. A completed generation can feed another mode: call use_generation_as_guide with its reference and the requested next mode, then configure that mode and ask before generating. Do not ask the user to download and upload a Henge result again.
13. The option adapt='auto' does not mean the reference was adapted. Never claim it was from get_options. Check get_job: plan.adaptation.used is the truth. When preview_available is true, call view_job_image before describing the prepared reference.
14. When the user asks you to create an original reference image, call generate_reference_image. Write a self-contained image prompt optimized for video character reference: a clearly visible subject, coherent identity, clean lighting and an uncluttered background. Prefer portrait for a character. The generated image is only a candidate: never claim it was added to the studio. Tell the user to click the button on the image to use it as the next Picture. Do not generate images unless the user asked for one.
15. A user message ending with [sent while you were still working on the previous request] arrived while you were working. Read it before your next action: if it changes the request, adapt what you are doing (or stop and ask); if it is unrelated, finish the current step and then answer it.
16. Default to the cheapest setup: set_quality 480p before generating (fastest and cheapest), keep the turbo LoRA and its step count, one take. Use a higher quality, more steps or no turbo only when the user asks for it ("720p", "best quality", "final version"), and say it costs more time. Sharpness is the exception: there the target resolution is the point, so keep what the user chose.

Be brief. Always answer in the language of the user's latest message, even when it differs from the interface or earlier messages. Write approval questions in that same language. Never invent people, pictures or results you have not seen."""

STUDIO_TOOLS = [
    {'name': 'get_studio_state', 'description': 'The current studio state: mode, guide video (duration, selected interval, size), pictures, marked subjects, guide representation, prompt, quality and the selected job.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'view_pictures', 'description': 'See the attached reference pictures (Picture 1, Picture 2...).',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'view_frame', 'description': 'See one frame of the guide video at a time in seconds (within the selected interval). grid=true draws a coordinate grid (x and y from 0 to 1, a line every 0.1) to read positions for mark_subject.',
     'input_schema': {'type': 'object', 'properties': {'time': {'type': 'number'}, 'grid': {'type': 'boolean'}}, 'required': ['time'], 'additionalProperties': False}},
    {'name': 'point_video', 'description': 'Use optional local Molmo2 to locate described people or objects in ONE guide shot (at most 30 seconds). Returns time-indexed normalized points and preview frames, not SAM masks. Inspect proposals, then use mark_subject with x/y/time and the correct Picture slots; reuse the same subject for more marks. Object IDs are local to this query and are not Picture IDs. Do not infer identity across camera cuts. Never claim all frames are segmented until SAM tracking has run.',
     'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string', 'description': 'Precise visual target, preferably an English pointing/tracking request'}, 'start': {'type': 'number'}, 'end': {'type': 'number'}}, 'required': ['query', 'start', 'end'], 'additionalProperties': False}},
    {'name': 'suggest_cuts', 'description': 'Let local Molmo2 choose where the shots split: natural breaks (end of a sentence, a pause between actions) plus camera cuts, within max_seconds per shot (default: the current shot length). Applies the split points to the studio unless apply=false; returns the resulting shots. Use it before generating long or dialogue-heavy guides, or when the user asks for shots of a given length.',
     'input_schema': {'type': 'object', 'properties': {'max_seconds': {'type': 'number'}, 'apply': {'type': 'boolean'}}, 'additionalProperties': False}},
    {'name': 'ask_video', 'description': 'Ask local Molmo2 a question about the guide video: it watches the whole interval with timestamps (frames you see with view_frame are single moments). Use it whenever you need to understand the video: a caption or timeline, how many people and where, who does or says what and when, camera moves and cuts, where an action starts or ends. Answers in text; timestamps are seconds from start. Changes nothing.',
     'input_schema': {'type': 'object', 'properties': {'question': {'type': 'string'}, 'start': {'type': 'number'}, 'end': {'type': 'number'}}, 'required': ['question'], 'additionalProperties': False}},
    {'name': 'match_people', 'description': 'Find people from their photos in EVERY shot of the selected interval (local Molmo2; cuts are detected) and mark them: one subject per person, one mark per shot where they appear, bound to picture_slots; SAM then tracks from the marks. photo is the exact file name of an explanation image from the chat, or "Picture N" for an attached Picture showing that same person. A person is only marked in a shot when found in two of its three keyframes and a reverse check agrees, so a missing shot means not found. apply=false only returns the proposals. Takes about a minute per shot; returns one preview per shot.',
     'input_schema': {'type': 'object', 'properties': {'people': {'type': 'array', 'minItems': 1, 'maxItems': 6, 'items': {'type': 'object', 'properties': {'photo': {'type': 'string'}, 'picture_slots': {'type': 'array', 'items': {'type': 'integer'}}, 'label': {'type': 'string'}}, 'required': ['photo', 'picture_slots'], 'additionalProperties': False}}, 'start': {'type': 'number'}, 'end': {'type': 'number'}, 'apply': {'type': 'boolean'}}, 'required': ['people'], 'additionalProperties': False}},
    {'name': 'find_people', 'description': 'Detect and number every person (or animal) in the guide frame at a time. Returns the frame with numbers drawn on each one; use the numbers with mark_subject.',
     'input_schema': {'type': 'object', 'properties': {'time': {'type': 'number'}, 'kind': {'type': 'string', 'enum': ['person', 'animal']}}, 'required': ['time'], 'additionalProperties': False}},
    {'name': 'set_mode', 'description': 'Switch the studio mode.',
     'input_schema': {'type': 'object', 'properties': {'mode': {'type': 'string', 'enum': ['swap', 'motion', 'headswap', 'sharpness']}}, 'required': ['mode'], 'additionalProperties': False}},
    {'name': 'set_prompt', 'description': 'Replace the request text in the prompt editor. Use @Picture1, @Picture2 for the pictures.',
     'input_schema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}},
    {'name': 'mark_subject', 'description': 'Mark a performer at a time where find_people ran: give person (its number) or, if find_people missed them, x and y (0-1 of the frame) on their body; SAM segments from that point. One subject per performer: marking again with the same picture_slots (or with subject) adds a mark to that subject, e.g. the same person after a camera cut. Mark every performer at every moment they appear after a cut.',
     'input_schema': {'type': 'object', 'properties': {'person': {'type': 'integer', 'description': 'number from find_people'}, 'x': {'type': 'number'}, 'y': {'type': 'number'},
                                                       'time': {'type': 'number', 'description': 'the time used in find_people'},
                                                       'picture_slots': {'type': 'array', 'items': {'type': 'integer'}}, 'label': {'type': 'string'}, 'subject': {'type': 'integer', 'description': 'existing subject number to add this mark to'}},
                      'required': ['time'], 'additionalProperties': False}},
    {'name': 'remove_subject', 'description': 'Remove one marked subject (its number in the studio state).',
     'input_schema': {'type': 'object', 'properties': {'subject': {'type': 'integer'}}, 'required': ['subject'], 'additionalProperties': False}},
    {'name': 'remove_pictures', 'description': 'Remove reference pictures: the given slots, or all of them when slots is empty.',
     'input_schema': {'type': 'object', 'properties': {'slots': {'type': 'array', 'items': {'type': 'integer'}}}, 'additionalProperties': False}},
    {'name': 'set_interval', 'description': 'Select the part of the guide video to use, in seconds of the source video.',
     'input_schema': {'type': 'object', 'properties': {'start': {'type': 'number'}, 'end': {'type': 'number'}}, 'required': ['start', 'end'], 'additionalProperties': False}},
    {'name': 'set_shots', 'description': "How long videos are split (split_points: seconds from the selection start where shots must end, [] clears them; suggest_cuts fills them): seconds per shot (2-20), cut_mode ('fit' = shot length ending at camera cuts, 'every' = a new shot at every cut, 'off' = fixed length) and context_frames carried between shots (0-48). With marks, cuts always start a new shot.",
     'input_schema': {'type': 'object', 'properties': {'split_points': {'type': 'array', 'items': {'type': 'number'}}, 'seconds': {'type': 'number'}, 'cut_mode': {'type': 'string', 'enum': ['fit', 'every', 'off']}, 'context_frames': {'type': 'integer'}}, 'additionalProperties': False}},
    {'name': 'set_output', 'description': 'Output audio and frame rate: keep_audio (the source audio in the result), audio_conditioning (the guide audio drives the generation), timeline_fps.',
     'input_schema': {'type': 'object', 'properties': {'keep_audio': {'type': 'boolean'}, 'audio_conditioning': {'type': 'boolean'}, 'timeline_fps': {'type': 'number'}}, 'additionalProperties': False}},
    {'name': 'set_project', 'description': 'Name the project (shown in History).',
     'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name'], 'additionalProperties': False}},
    {'name': 'get_options', 'description': 'The generation options now (model profile, method, turbo, steps, cfg, seed, structure guidance, reference adaptation, reference preparation, sharpness upscale...) and what is installed: models, turbos, bases, upscalers, TARA.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'get_settings', 'description': 'Read backend settings for connection, assistant or molmo. Stored API keys are redacted. These are server settings, not browser generation options.',
     'input_schema': {'type': 'object', 'properties': {'section': {'type': 'string', 'enum': ['connection', 'assistant', 'molmo']}}, 'required': ['section'], 'additionalProperties': False}},
    {'name': 'set_settings', 'description': 'Patch backend connection, assistant or molmo settings only when the user requests that change. Use get_settings first. Switching connection is blocked during active generations. Does not change browser generation options.',
     'input_schema': {'type': 'object', 'properties': {'section': {'type': 'string', 'enum': ['connection', 'assistant', 'molmo']}, 'settings': {'type': 'object'}}, 'required': ['section', 'settings'], 'additionalProperties': False}},
    {'name': 'set_options', 'description': "Patch generation options from get_options.options. All returned option keys are writable; nested patches preserve other fields. Check live capabilities and generation_blockers, then read the effective values back. Includes temporal_windows, regional_attention, mask, seed, model/method/turbo, guide_clip, source_blur, all Sharpness/refiner settings and reference preparation. Never invent option keys or assume an unsupported feature is ready.",
     'input_schema': {'type': 'object', 'properties': {'options': {'type': 'object'}}, 'required': ['options'], 'additionalProperties': False}},
    {'name': 'send_marks_to_job', 'description': "Copy the studio's current marked subjects to a job that waits for approval (after adding marks in shots that start after a cut); its color/mask preview is rebuilt.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'select_job', 'description': 'Show a job in the generation panel (its plan, previews, result).',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'use_generation_as_guide', 'description': "Load a completed generation's result as the guide video for another mode. Use this for a second pass such as Swap -> Sharpness. This changes the studio but does not start the next generation.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['swap', 'motion', 'headswap', 'sharpness']}}, 'required': ['job_id', 'mode'], 'additionalProperties': False}},
    {'name': 'confirm_cancel_job', 'description': "Show an approval card inside the chat before cancelling an active generation. question and both button labels must use the language of the user's latest message and the question must include the reason and visible generation reference. This only asks; it never cancels. Call cancel_job only if approved=true.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'question': {'type': 'string'}, 'approve_label': {'type': 'string'}, 'decline_label': {'type': 'string'}}, 'required': ['job_id', 'question', 'approve_label', 'decline_label'], 'additionalProperties': False}},
    {'name': 'clear_subjects', 'description': 'Remove every marked subject.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'set_guide', 'description': 'Set the guide representation. Default original, including vehicles/objects. Mask is opt-in and requires existing subject marks; never use it automatically. For 2d also set mark opacity (0.1-1).',
     'input_schema': {'type': 'object', 'properties': {'representation': {'type': 'string', 'enum': ['original', '2d', '3d', 'mask']}, 'mark_opacity': {'type': 'number'}},
                      'required': ['representation'], 'additionalProperties': False}},
    {'name': 'set_quality', 'description': 'Output resolution (short side). 1440p and 2160p are only for sharpness.',
     'input_schema': {'type': 'object', 'properties': {'quality': {'type': 'string', 'enum': ['480p', '720p', '1080p', '1440p', '2160p']}}, 'required': ['quality'], 'additionalProperties': False}},
    {'name': 'set_auto_approve', 'description': 'Whether a generation runs straight after planning (true) or stops at the plan for review (false, recommended when you want to check previews).',
     'input_schema': {'type': 'object', 'properties': {'enabled': {'type': 'boolean'}}, 'required': ['enabled'], 'additionalProperties': False}},
    {'name': 'generate', 'description': 'Press Generate with the current studio state. Returns the new job id.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]
JOB_TOOLS = [
    {'name': 'generate_reference_image', 'description': 'Generate one original candidate reference image with the configured OpenAI image model. The result appears in the chat; the user must explicitly choose to add it as the next Picture.',
     'input_schema': {'type': 'object', 'properties': {'prompt': {'type': 'string'}, 'aspect_ratio': {'type': 'string', 'enum': ['portrait', 'square', 'landscape']}}, 'required': ['prompt'], 'additionalProperties': False}},
    {'name': 'get_job', 'description': 'Status, stage, message, plan summary, prompt and warnings of a job. job_id accepts the full id or its visible 8-character generation reference, with or without #.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'wait_for_job', 'description': "Check whether a background job reached the plan review ('plan') or finished ('done'). Returns immediately; if it is still running, tell the user and let them keep chatting instead of polling.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'until': {'type': 'string', 'enum': ['plan', 'done']}}, 'required': ['job_id', 'until'], 'additionalProperties': False}},
    {'name': 'view_job_video', 'description': "See a few frames of a job video: 'marks' (2d color guide at full opacity), 'mask' (latent mask preview), 'guide' (prepared guide), 'result' or 'comparison'.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'which': {'type': 'string', 'enum': ['marks', 'mask', 'guide', 'result', 'comparison']}, 'frames': {'type': 'integer'}},
                      'required': ['job_id', 'which'], 'additionalProperties': False}},
    {'name': 'view_job_image', 'description': "See a generated analysis image from a job. 'adapted_reference' is the adapted appearance/pose reference (made by the image editor) and exists only when the plan actually adapted the reference.",
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'which': {'type': 'string', 'enum': ['adapted_reference']}}, 'required': ['job_id', 'which'], 'additionalProperties': False}},
    {'name': 'set_job_mark_opacity', 'description': 'Change the 2d mark opacity of a job waiting for approval.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'opacity': {'type': 'number'}}, 'required': ['job_id', 'opacity'], 'additionalProperties': False}},
    {'name': 'get_job_shots', 'description': 'How a job splits the video into shots: index, start and end (seconds in the source), and whether each starts after a camera cut (people may have moved or changed there).',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'redo_shot', 'description': 'Render one shot (1-based) of a finished job again with a new seed (or the given one) and join the video again; the other shots are kept. job_id accepts the visible generation reference. Then wait_for_job done.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'shot': {'type': 'integer'}, 'seed': {'type': 'integer'}}, 'required': ['job_id', 'shot'], 'additionalProperties': False}},
    {'name': 'retry_job', 'description': 'Run a failed or cancelled job again.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'approve_job', 'description': 'Approve a plan waiting for review so the video renders.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
    {'name': 'cancel_job', 'description': 'Cancel a job.',
     'input_schema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id'], 'additionalProperties': False}},
]
TOOLS = STUDIO_TOOLS + JOB_TOOLS
VISION_MARKING = """
Marking mode: you mark people yourself (the user turned off SAM detection for marking). There is no find_people.
To bind people: view_frame with grid=true at a few times (one per scene after each camera cut), decide who is who
from the frames, the reference Pictures and any explanation images the user sent, then mark_subject with x and y
(0-1, read on the grid) on the middle of that person's torso, clear of other people. mark_subject answers with the
frame and your point drawn on it: check that the dot sits on the right person and mark again if not. SAM then
segments and tracks each person from your points in every frame at generation. Mark only the people the user wants
changed; leave everyone else unmarked. A Picture whose person does not appear in the selected interval stays
unmarked: say so instead of binding it to someone else."""

MOLMO_TOOLS = {'ask_video', 'point_video', 'match_people', 'suggest_cuts'}


def system_for(cfg: dict) -> str:
    availability = ('\nOptional Molmo video tools are available.' if cfg.get('molmo_available') else
                    '\nOptional Molmo video tools are unavailable. Inspect the guide with view_frame; do not call ask_video, point_video, match_people or suggest_cuts. Do not request Molmo configuration for an ordinary edit.')
    return SYSTEM + availability + (VISION_MARKING if cfg.get('marking') == 'vision' else '')

def tools_for(cfg: dict) -> list:
    out = []
    for t in TOOLS:
        if t['name'] in MOLMO_TOOLS and not cfg.get('molmo_available'):
            continue
        if t['name'] == 'find_people' and cfg.get('marking') == 'vision':
            continue
        if t['name'] == 'mark_subject' and cfg.get('marking') == 'vision':
            t = {**t, 'description': 'Mark a performer with x and y (0-1 of the frame, read on the view_frame grid) on their torso at a time. Returns the frame with your point drawn: check it. SAM segments and tracks from that point. One subject per performer: marking again with the same picture_slots (or with subject) adds a mark to that subject, e.g. the same person after a camera cut.'}
        out.append(t)
    return out

STUDIO_NAMES = {t['name'] for t in STUDIO_TOOLS}
JOB_NAMES = {t['name'] for t in JOB_TOOLS}


def load_config(path: Path) -> dict:
    try:
        stored = json.loads(path.read_text()) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def public_config(cfg: dict) -> dict:
    """The config for the browser: keys are never sent back, only whether they are saved."""
    key = cfg.get('api_key') or ''
    image_key = cfg.get('image_api_key') or ''
    return {**{k: v for k, v in cfg.items() if k not in ('api_key', 'image_api_key')}, 'has_key': bool(key),
            'key_hint': f'…{key[-4:]}' if len(key) > 8 else '', 'has_image_key': bool(image_key),
            'image_key_hint': f'…{image_key[-4:]}' if len(image_key) > 8 else ''}


def save_config(path: Path, update: dict) -> dict:
    cfg = load_config(path)
    for k in ('provider', 'model', 'base_url', 'effort', 'image_model', 'image_quality'):
        if k in update and isinstance(update[k], str):
            cfg[k] = update[k].strip()
    if isinstance(update.get('image_enabled'), bool):
        cfg['image_enabled'] = update['image_enabled']
    if isinstance(update.get('api_key'), str) and update['api_key'].strip():
        cfg['api_key'] = update['api_key'].strip()
    if update.get('clear_key'):
        cfg['api_key'] = ''
    if isinstance(update.get('image_api_key'), str) and update['image_api_key'].strip():
        cfg['image_api_key'] = update['image_api_key'].strip()
    if update.get('clear_image_key'):
        cfg['image_api_key'] = ''
    if update.get('marking') in ('sam', 'vision'):
        cfg['marking'] = update['marking']
    if update.get('planner') in ('local', 'assistant'):
        cfg['planner'] = update['planner']
    if cfg['provider'] not in PROVIDERS:
        raise ValueError('Unknown provider')
    if isinstance(update.get('api_key'), str) and update['api_key'].strip() and key_hint(cfg['provider'], cfg['api_key']):
        raise ValueError(key_hint(cfg['provider'], cfg['api_key']))
    if cfg['effort'] not in ('', 'low', 'medium', 'high', 'xhigh', 'max'):   # '' = the model's default
        raise ValueError('Unknown effort')
    if not cfg['model']:
        raise ValueError('Choose a model')
    if cfg['image_quality'] not in ('low', 'medium', 'high', 'auto'):
        raise ValueError('Unknown image quality')
    if not cfg['image_model']:
        raise ValueError('Choose an image model')
    if cfg['base_url'] and not re.match(r'^https?://', cfg['base_url']):
        raise ValueError('The base URL must start with http:// or https://')
    path.write_text(json.dumps(cfg, indent=2))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return cfg


def _split_data_url(url: str) -> tuple[str, str]:
    m = re.match(r'^data:(image/[a-z+]+);base64,(.+)$', url, re.S)
    if not m:
        raise ValueError('Images must be data URLs')
    return m.group(1), m.group(2)


def repair_tool_history(messages: list) -> list:
    """Make interrupted browser tool turns valid for both model APIs.

    A reload, cancellation, or closed approval can persist an assistant tool call
    before the browser has appended its result. OpenAI rejects the whole history
    in that state, so close missing calls explicitly and discard orphan results.
    """
    repaired, pending = [], {}
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in {'user', 'assistant', 'tool'}:
            continue
        role = message['role']
        if pending and role != 'tool':
            repaired.append({'role': 'tool', 'results': [
                {'id': call_id, 'name': name, 'text': 'Tool execution was interrupted before a result was returned.', 'images': [], 'is_error': True}
                for call_id, name in pending.items()]})
            pending = {}
        if role == 'assistant':
            calls = [c for c in message.get('tool_calls') or [] if isinstance(c, dict) and c.get('id') and c.get('name')]
            clean = {**message, 'tool_calls': calls}
            repaired.append(clean)
            pending = {str(c['id']): str(c['name']) for c in calls}
        elif role == 'tool':
            if not pending:
                continue
            supplied = {str(r.get('id')): r for r in message.get('results') or [] if isinstance(r, dict) and str(r.get('id')) in pending}
            results = [supplied.get(call_id) or {'id': call_id, 'name': name, 'text': 'Tool execution was interrupted before a result was returned.', 'images': [], 'is_error': True}
                       for call_id, name in pending.items()]
            repaired.append({'role': 'tool', 'results': results})
            pending = {}
        else:
            repaired.append(message)
    if pending:
        repaired.append({'role': 'tool', 'results': [
            {'id': call_id, 'name': name, 'text': 'Tool execution was interrupted before a result was returned.', 'images': [], 'is_error': True}
            for call_id, name in pending.items()]})
    return repaired


# --- Claude (official Anthropic SDK) ---

def _to_anthropic(messages: list) -> list:
    out = []
    for m in messages:
        if m['role'] == 'user':
            content = [{'type': 'image', 'source': {'type': 'base64', 'media_type': t, 'data': d}} for t, d in map(_split_data_url, m.get('images') or [])]
            out.append({'role': 'user', 'content': content + [{'type': 'text', 'text': m.get('text') or '…'}]})
        elif m['role'] == 'assistant':
            if m.get('native') and m.get('native_provider') == 'anthropic':
                out.append({'role': 'assistant', 'content': m['native']})
            else:
                content = ([{'type': 'text', 'text': m['text']}] if m.get('text') else []) + [{'type': 'tool_use', 'id': c['id'], 'name': c['name'], 'input': c['input']} for c in m.get('tool_calls') or []]
                out.append({'role': 'assistant', 'content': content or [{'type': 'text', 'text': '…'}]})
        elif m['role'] == 'tool':
            blocks = []
            for r in m['results']:
                inner = [{'type': 'text', 'text': r.get('text') or 'done'}] + [{'type': 'image', 'source': {'type': 'base64', 'media_type': t, 'data': d}} for t, d in map(_split_data_url, r.get('images') or [])]
                blocks.append({'type': 'tool_result', 'tool_use_id': r['id'], 'content': inner, **({'is_error': True} if r.get('is_error') else {})})
            out.append({'role': 'user', 'content': blocks})
    # A message the user queued while tools ran follows the tool results: one user turn, results first.
    merged = []
    for m in out:
        if merged and m['role'] == 'user' and merged[-1]['role'] == 'user':
            merged[-1] = {'role': 'user', 'content': merged[-1]['content'] + m['content']}
        else:
            merged.append(m)
    return merged


def _call_anthropic(cfg: dict, messages: list) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=cfg['api_key'] or None, **({'base_url': cfg['base_url']} if cfg['base_url'] else {}))
    tools = tools_for(cfg)
    tools[-1] = {**tools[-1], 'cache_control': {'type': 'ephemeral'}}   # tools + system are the stable prefix
    kwargs = dict(model=cfg['model'], max_tokens=16000, system=[{'type': 'text', 'text': system_for(cfg)}], tools=tools,
                  messages=_to_anthropic(messages), **({'output_config': {'effort': cfg['effort']}} if cfg['effort'] else {}))
    try:
        # Claude Opus 5.5 / Sonnet 5.5 / Fable 5.1: if a safety classifier declines, the API reruns on a fallback model.
        response = client.beta.messages.create(betas=['server-side-fallback-2026-07-01'], extra_body={'fallbacks': 'default'}, **kwargs)
    except anthropic.BadRequestError as e:
        if 'fallback' not in str(e).lower():
            raise
        response = client.beta.messages.create(**kwargs)   # models or gateways without fallbacks
    if response.stop_reason == 'refusal':
        return {'text': 'The model declined this request.', 'tool_calls': [], 'native': None}
    native = [b.model_dump(exclude_none=True) for b in response.content]
    text = '\n'.join(b.text for b in response.content if b.type == 'text').strip()
    calls = [{'id': b.id, 'name': b.name, 'input': b.input} for b in response.content if b.type == 'tool_use']
    return {'text': text, 'tool_calls': calls, 'native': native, 'native_provider': 'anthropic'}


# --- OpenAI-compatible chat completions (OpenAI, LM Studio, Ollama, vLLM...) ---

def _to_openai(messages: list, system: str = SYSTEM) -> list:
    out = [{'role': 'system', 'content': system}]
    for m in messages:
        if m['role'] == 'user':
            parts = [{'type': 'text', 'text': m.get('text') or '…'}] + [{'type': 'image_url', 'image_url': {'url': u}} for u in m.get('images') or []]
            out.append({'role': 'user', 'content': parts if m.get('images') else (m.get('text') or '…')})
        elif m['role'] == 'assistant':
            msg = {'role': 'assistant', 'content': m.get('text') or None}
            if m.get('tool_calls'):
                msg['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': json.dumps(c['input'])}} for c in m['tool_calls']]
            out.append(msg)
        elif m['role'] == 'tool':
            images = []
            for r in m['results']:
                out.append({'role': 'tool', 'tool_call_id': r['id'], 'content': ('ERROR: ' if r.get('is_error') else '') + (r.get('text') or 'done')})
                images += [(r['name'], u) for u in r.get('images') or []]
            if images:
                # Tool messages carry text only in this API: the pictures follow as a user message.
                out.append({'role': 'user', 'content': [{'type': 'text', 'text': 'Images returned by the tools above, in order: ' + ', '.join(n for n, _ in images)}]
                            + [{'type': 'image_url', 'image_url': {'url': u}} for _, u in images]})
    return out


NOT_CHAT = re.compile(r'embed|tts|whisper|transcribe|dall-e|image|moderation|realtime|audio|search|computer-use|babbage|davinci|sora', re.I)


def key_hint(provider: str, key: str) -> str:
    """Why a key cannot work with this provider, judged by its format (the key itself is never echoed)."""
    if provider == 'anthropic' and key.startswith('sk-ant-oat'):
        return 'This is a Claude subscription token (from Claude Code), not an API key. Create an API key at console.anthropic.com → API Keys (sk-ant-api…).'
    if provider == 'anthropic' and key.startswith(('sk-proj', 'sk-svcacct')):
        return 'This is an OpenAI key. Choose OpenAI as the provider, or paste an Anthropic API key (sk-ant-api…).'
    if provider == 'openai' and key.startswith('sk-ant'):
        return 'This is an Anthropic key. Choose Claude as the provider, or paste an OpenAI key.'
    return ''


def list_models(saved: dict, draft: dict) -> list:
    """Model ids the provider in the settings draft offers, newest first. The saved key is used only for the same
    provider and URL it was saved for, so it is never sent to another server."""
    provider = draft.get('provider') or saved['provider']
    base_url = (draft.get('base_url') if isinstance(draft.get('base_url'), str) else saved['base_url']).strip()
    key = (draft.get('api_key') or '').strip()
    if not key and provider == saved['provider'] and base_url == saved['base_url']:
        key = saved['api_key']
    if provider == 'local':
        return [{'id': LOCAL_MODEL, 'name': 'Henge VLM (Qwen 3.5 9B, built-in)'}]
    if provider == 'anthropic':
        import anthropic
        hint = key_hint(provider, key)
        if hint: raise ValueError(hint)
        # An OpenAI URL left over from the previous provider is not Anthropic's.
        if 'api.openai.com' in base_url: base_url = ''
        client = anthropic.Anthropic(api_key=key or None, **({'base_url': base_url} if base_url else {}))
        try: return [{'id': m.id, 'name': m.display_name} for m in client.models.list(limit=100)]
        except anthropic.AuthenticationError: raise ValueError('Anthropic rejected this key. Use an API key from console.anthropic.com → API Keys (it starts with sk-ant-api).')
    base = (base_url or 'https://api.openai.com/v1').rstrip('/')
    r = requests.get(base + '/models', headers={'Authorization': f'Bearer {key}'} if key else {}, timeout=20)
    if not r.ok:
        raise ValueError(f'{base}/models: HTTP {r.status_code}: {r.text[:200]}')
    rows = sorted(r.json().get('data') or [], key=lambda m: -(m.get('created') or 0))
    official = 'api.openai.com' in base
    return [{'id': m['id'], 'name': m['id']} for m in rows if m.get('id') and not (official and NOT_CHAT.search(m['id']))]


def _call_openai(cfg: dict, messages: list) -> dict:
    base = (cfg['base_url'] or 'https://api.openai.com/v1').rstrip('/')
    tools = [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'], 'parameters': t['input_schema']}} for t in tools_for(cfg)]
    headers = {'Authorization': f"Bearer {cfg['api_key']}"} if cfg['api_key'] else {}
    body = {'model': cfg['model'], 'messages': _to_openai(messages, system_for(cfg)), 'tools': tools}
    # OpenAI's current models take max_completion_tokens and reject max_tokens; local servers (LM Studio, Ollama,
    # vLLM) still read max_tokens. Start with the one the server is likely to take, switch once if it refuses.
    limits = ['max_completion_tokens', 'max_tokens'] if 'api.openai.com' in base else ['max_tokens', 'max_completion_tokens']
    for i, name in enumerate(limits):
        r = requests.post(base + '/chat/completions', headers=headers, timeout=300, json={**body, name: 8192})
        if r.ok or i or r.status_code != 400 or name not in r.text:
            break
    if not r.ok:
        raise RuntimeError(f'{base} HTTP {r.status_code}: {r.text[:400]}')
    msg = r.json()['choices'][0]['message']
    calls = []
    for c in msg.get('tool_calls') or []:
        try:
            args = json.loads(c['function'].get('arguments') or '{}')
        except json.JSONDecodeError:
            args = {'_invalid_json': c['function'].get('arguments')}
        calls.append({'id': c['id'], 'name': c['function']['name'], 'input': args})
    return {'text': (msg.get('content') or '').strip(), 'tool_calls': calls, 'native': None}


# --- Built-in VLM (no native tool calling): tools are described in the prompt and called with a JSON object ---

LOCAL_PROTOCOL = """

You are running on the built-in Henge VLM. You have no native tool calls. To use tools, reply with ONLY one JSON
object and nothing else:
{"tool_calls": [{"name": "<tool name>", "input": {<arguments matching its parameters>}}]}
You may call several tools at once. When you need no tool, reply in plain text to the user, in the user's language.
Never invent tool results or the studio state: at the start of every new user request call get_studio_state first.
Refer to pictures as "Picture N". The text you give set_prompt is always in English, whatever language the user
speaks. Tools:
"""


def _tool_line(t: dict) -> str:
    props = t['input_schema'].get('properties', {}); req = set(t['input_schema'].get('required', []))
    args = ', '.join(f"{k}{'' if k in req else '?'}: {v.get('type', 'any')}" for k, v in props.items())
    return f"- {t['name']}({args}): {t['description'][:300]}"


def _local_images(messages: list, limit: int = 4) -> list:
    """The newest images (from the last user or tool turn that has any), at most `limit`."""
    for m in reversed(messages):
        urls = m.get('images') or [u for r in m.get('results', []) for u in r.get('images') or []]
        if urls:
            return urls[-limit:]
    return []


def _local_prompt(cfg: dict, messages: list) -> str:
    lines = [system_for(cfg) + LOCAL_PROTOCOL + '\n'.join(_tool_line(t) for t in tools_for(cfg)), '', 'Conversation so far:']
    for m in messages[-24:]:
        if m['role'] == 'user':
            lines.append('USER: ' + (m.get('text') or '') + (f" [{len(m['images'])} image(s) attached]" if m.get('images') else ''))
        elif m['role'] == 'assistant':
            calls = m.get('tool_calls') or []
            lines.append('ASSISTANT: ' + (json.dumps({'tool_calls': [{'name': c['name'], 'input': c['input']} for c in calls]}) if calls else (m.get('text') or '')))
        elif m['role'] == 'tool':
            for r in m['results']:
                lines.append(f"TOOL {r['name']}: " + ('ERROR: ' if r.get('is_error') else '') + (r.get('text') or 'done')[:2000]
                             + (f" [{len(r['images'])} image(s)]" if r.get('images') else ''))
    lines.append('ASSISTANT:')
    return '\n'.join(lines)


def repair_json(text: str) -> str:
    """Close the brackets a small model forgot ('...true}]}' for '...true}}]}'): a closer that does not match the open
    bracket first closes the inner ones; missing closers are added at the end."""
    out, stack, quoted, escaped = [], [], False, False
    for ch in text:
        if quoted:
            out.append(ch); escaped = ch == '\\' and not escaped
            if ch == '"' and not escaped: quoted = False
            if ch != '\\': escaped = False
            continue
        if ch == '"': quoted = True
        elif ch in '{[': stack.append(ch)
        elif ch in '}]':
            want = '{' if ch == '}' else '['
            while stack and stack[-1] != want:
                out.append('}' if stack.pop() == '{' else ']')
            if stack: stack.pop()
        out.append(ch)
    out += ['}' if b == '{' else ']' for b in reversed(stack)]
    return ''.join(out)


def parse_local_reply(text: str) -> dict:
    """The built-in VLM's reply -> {'text', 'tool_calls'}: a JSON object with tool_calls (bare or in a code fence),
    else plain text."""
    clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())

    def calls_in(candidate: str) -> list:
        for attempt in (candidate, repair_json(candidate)):
            try:
                data = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            calls = data.get('tool_calls') if isinstance(data, dict) else None
            if isinstance(calls, list):
                return [{'id': 'call_' + uuid.uuid4().hex[:12], 'name': str(c.get('name')), 'input': c.get('input') if isinstance(c.get('input'), dict) else {}}
                        for c in calls if isinstance(c, dict) and c.get('name')]
        return []

    start = clean.find('{')
    while start >= 0:
        depth, end = 0, len(clean)
        for i in range(start, len(clean)):
            depth += {'{': 1, '}': -1}.get(clean[i], 0)
            if depth == 0:
                end = i + 1; break
        # A balanced object, or (a forgotten brace) the rest of the reply, repaired.
        out = calls_in(clean[start:end]) or (calls_in(clean[start:]) if end != len(clean) else [])
        if out:
            return {'text': clean[:start].strip(), 'tool_calls': out}
        start = clean.find('{', start + 1)
    return {'text': text.strip(), 'tool_calls': []}


def _call_local(cfg: dict, messages: list) -> dict:
    if LOCAL_VLM is None:
        raise RuntimeError('The built-in VLM is not available on this bridge')
    return {**parse_local_reply(LOCAL_VLM(_local_prompt(cfg, messages), _local_images(messages), 2048)), 'native': None}


def complete(cfg: dict, instruction: str, image: Path | None = None, max_tokens: int = 2048) -> str:
    """One planner request (no tools): an instruction and an optional image, answered with plain text. Used when the
    assistant's model writes the prompts instead of the local planner."""
    data = None
    if image is not None:
        mime = 'image/png' if image.suffix.lower() == '.png' else 'image/webp' if image.suffix.lower() == '.webp' else 'image/jpeg'
        data = (mime, base64.b64encode(image.read_bytes()).decode())
    # Reasoning models spend part of the budget thinking: never give them less than 4096 tokens.
    budget = max(max_tokens, 4096)
    if cfg['provider'] == 'local':
        if LOCAL_VLM is None:
            raise RuntimeError('The built-in VLM is not available on this bridge')
        return LOCAL_VLM(instruction, [jpeg_data_url(image)] if image is not None else [], budget).strip()
    if cfg['provider'] == 'anthropic':
        import anthropic
        client = anthropic.Anthropic(api_key=cfg['api_key'] or None, **({'base_url': cfg['base_url']} if cfg['base_url'] else {}))
        content = ([{'type': 'image', 'source': {'type': 'base64', 'media_type': data[0], 'data': data[1]}}] if data else []) + [{'type': 'text', 'text': instruction}]
        response = client.messages.create(model=cfg['model'], max_tokens=budget, messages=[{'role': 'user', 'content': content}])
        if response.stop_reason == 'refusal':
            raise RuntimeError('The assistant model declined this planning request')
        return '\n'.join(b.text for b in response.content if b.type == 'text').strip()
    base = (cfg['base_url'] or 'https://api.openai.com/v1').rstrip('/')
    headers = {'Authorization': f"Bearer {cfg['api_key']}"} if cfg['api_key'] else {}
    content = [{'type': 'text', 'text': instruction}] + ([{'type': 'image_url', 'image_url': {'url': f'data:{data[0]};base64,{data[1]}'}}] if data else [])
    body = {'model': cfg['model'], 'messages': [{'role': 'user', 'content': content}]}
    limits = ['max_completion_tokens', 'max_tokens'] if 'api.openai.com' in base else ['max_tokens', 'max_completion_tokens']
    for i, name in enumerate(limits):
        r = requests.post(base + '/chat/completions', headers=headers, timeout=300, json={**body, name: budget})
        if r.ok or i or r.status_code != 400 or name not in r.text:
            break
    if not r.ok:
        raise RuntimeError(f'{base} HTTP {r.status_code}: {r.text[:400]}')
    return (r.json()['choices'][0]['message'].get('content') or '').strip()


def call_model(cfg: dict, messages: list) -> dict:
    messages = repair_tool_history(messages)
    if cfg['provider'] == 'anthropic':
        return _call_anthropic(cfg, messages)
    if cfg['provider'] == 'local':
        return _call_local(cfg, messages)
    return _call_openai(cfg, messages)


def jpeg_data_url(path: Path) -> str:
    return 'data:image/jpeg;base64,' + base64.b64encode(Path(path).read_bytes()).decode()


def step(cfg: dict, messages: list, run_job_tool, max_rounds: int = 8) -> dict:
    """Run the model until it answers or needs studio tools. Job tools run here through run_job_tool(name, input) ->
    (text, images). Returns the appended history and, when needed, the studio calls for the browser plus the job
    results to send back with theirs (all results of one turn go in one message)."""
    messages = repair_tool_history(messages)
    available = {t['name'] for t in tools_for(cfg)}
    for _ in range(max_rounds):
        reply = call_model(cfg, messages)
        messages.append({'role': 'assistant', **reply})
        if not reply['tool_calls']:
            return {'messages': messages, 'studio_calls': [], 'job_results': [], 'done': True}
        job_results = []
        for c in reply['tool_calls']:
            if c['name'] not in available:
                job_results.append({'id': c['id'], 'name': c['name'], 'text': f"Tool {c['name']} is unavailable. Use view_frame to inspect the guide and the currently listed tools.", 'images': [], 'is_error': True})
            elif c['name'] in JOB_NAMES:
                try:
                    text, images = run_job_tool(c['name'], c['input'])
                    job_results.append({'id': c['id'], 'name': c['name'], 'text': text, 'images': images})
                except Exception as e:  # the model sees the error and can recover
                    job_results.append({'id': c['id'], 'name': c['name'], 'text': str(e)[:800], 'images': [], 'is_error': True})
            elif c['name'] not in STUDIO_NAMES:
                job_results.append({'id': c['id'], 'name': c['name'], 'text': f"Unknown tool {c['name']}", 'images': [], 'is_error': True})
        studio = [c for c in reply['tool_calls'] if c['name'] in STUDIO_NAMES and c['name'] in available]
        if studio:
            return {'messages': messages, 'studio_calls': studio, 'job_results': job_results, 'done': False}
        messages.append({'role': 'tool', 'results': job_results})
    return {'messages': messages, 'studio_calls': [], 'job_results': [], 'done': True}
