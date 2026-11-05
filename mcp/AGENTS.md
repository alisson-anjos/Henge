# Henge agent rules (the `henge` MCP)

You remake a video with the `henge` MCP tools: the people of a clip become other characters (Character Swap) or the
characters perform the clip's motion (Motion Transfer), while the shots, the camera, the motion and the soundtrack
stay. The task gives you the guide video and its interval, the cast (who becomes whom, with pictures or library
characters) and, optionally, your image-edit budget. You do the directing: plan the shots, cast, make and check the
keyframes, write the prompt, render, review every shot, fix what is worth fixing and deliver `save_result`.

When you run unattended (`claude -p`, `codex exec`) nobody answers questions mid-run: decide, do, and write down what
you decided in the result. Never finish before every shot with a replaced person has a reviewed take.
**Look at every image a tool returns** before the next step; never judge from a file name.

## Tools, in workflow order
| tool | what | cost |
|---|---|---|
| `status` | what the backend has: models, editors, turbos | free |
| `characters(names)` | the character library (`HENGE_CHARS`): descriptions, outfits, sheets and photos | free |
| `view_frame(video, time)` / `view_images(paths)` | look at a guide frame / several local images at once | free |
| `shot_plan(video, start, end)` | the shots a render makes, the camera cuts, `cuts_without_keyframe` | free (uploads the clip) |
| `find_people(video, time, kind)` | numbers the people in one frame; `kind='character'` for `edit_frame` | free (a SAM pass) |
| `edit_frame(video, time, op, character, pictures, editor)` | one keyframe: that person swapped in that frame | 1 image edit |
| `generate_image(prompt)` | a new picture (GPT Image, when enabled) | 1 image edit |
| `create_job(...)` | the generation: mode, pictures, prompt, `first_frame`, `keyframes`, `guide_normals` | GPU time |
| `wait_for_job(id, until)` | blocks up to `timeout` s; call again while it runs | free |
| `approve_job(id)` | render a plan that waits for review | GPU time |
| `review_job(id, shots)` | per shot: source frames over the result's, and the cut timing | free |
| `shot_prompt` / `redo_shot(id, shot, seed, prompt)` | read a shot's prompt / render one shot again | GPU time |
| `download_result(id)` / `save_result(id, result)` | the video / the deliverable | free |

Paths are local to the machine running the MCP server. A picture can also be `lib:Name` (the library character's sheet,
else its photo), `lib:Name/photo` or `lib:Name/sheet`.

## Budget (hard)
- At most **12 image edits per task** (`edit_frame` + `generate_image`, repaints included) unless the task sets another
  limit. Typical: 1 keyframe per shot with a replaced person, 1-2 repaints. Plan the keyframes before editing.
- One render at 480p (the default) before anything higher; 720p/1080p only when the task asks for it.
- A quota, billing or "disabled" error from an editor: stop editing, finish with what you have, and report it.

## 1. Read the clip
`status` first. Then `shot_plan` for the interval and `view_frame` at the start, the middle and a little after every
camera cut. Write down, per shot, who is in it (replaced or not) and what happens. If the detector missed or invented a
cut, note it: the keyframes follow the real cuts.

## 2. Cast
For each replaced person: the picture(s) and a one-line description of the character, **the whole outfit down to the
shoes**. Library characters: `characters(["Name"])` and use their description and outfit as they are. Make outfits
clearly different from each other or the model swaps identities. Whole-person replacement: face, hair, build and outfit
all change; never write "only the face" or "keep the original clothes". Keep faces visible: no sunglasses, masks or
helmets on a replacement. Extras and crowds stay as they are unless the task casts them.

**Mode.** Every replaced subject a person: Character Swap (`mode='swap'`) with an edited first frame and the normal-map
guide (the default with `first_frame`). Animals, objects or vehicles among them: Motion Transfer TARA
(`mode='motion'`, `options={'profile': 'motion_tara', 'conditioning_mode': 'tara'}`). If the task does not choose and a
person is watching, ask; unattended, pick by this rule and say so in the result.

## 3. Keyframes (strict)
A keyframe is a frame of the RESULT pinned at its time: the frame of the guide with the people already swapped. The model
follows the guide between keyframes, so the keyframes decide who is who.
- **The start** is always one: `first_frame` (the frame at `start`) for Character Swap.
- **One per shot that opens on a camera cut** and contains a replaced person (`shot_plan.cuts_without_keyframe`): a shot
  that opens on a cut has nothing else to start from, and a replaced person absent from every keyframe of a shot renders
  as the source person.
- Pick the frame where the replaced people are largest and sharp, the whole face visible, **at least 3 frames (0.15 s)
  after the cut**, and showing every replaced person of the shot.
- A **second keyframe in a shot** only if a replaced face turns from frontal to pure profile or back, or a replaced
  person enters who was not in the first one, and the new state lasts 2 s or more; keep the two at least 3 s apart.
  Never two keyframes of nearly the same framing (the result snaps between them).
- **Rapid cuts** between a few camera setups: one keyframe per setup per render shot, not per cut.
- Faces under ~50 px at 480p drift to strangers; a span with 5+ fast cuts follows none of them well: say so.

How: `find_people(video, t, kind='character')`, check each number is the person you mean, then
`edit_frame(video=..., time=t, op='swap', character=n, pictures=[...], editor='bfs_selective')` (or `'gpt_image'` when
`status` offers it; one person per call: chain a second swap with `image=<the first result>`).
Read every result: the right character in the right place, the outfit fully replaced (no hat, sunglasses or costume
left), composition and people count unchanged, nobody added, unreplaced people untouched, the source's light kept (a
backlit or shadowed figure stays dark). Repaint real failures only.

**Consistency.** Before `create_job`, `view_images` the first frame and every keyframe in time order and compare each
character across all of them: face, hair, outfit colours and patterns, build. Redo the one that differs (pass the
best-looking keyframe as an extra picture), naming the part and colour in the instruction.

## 4. Prompt and render
The prompt says who becomes whom: each replaced person by how they look and where they are in the SOURCE, then
`@Picture N` and the character's description and outfit. Name every picture. Visible talking or singing with an unknown
text: "speaks" / "sings", never invented words. A timed action (eyes open, a jump) says when ("at about 00:11").

`create_job(mode, video, pictures, prompt, start, end, first_frame=..., keyframes=[{"time": t, "image": path}, ...])`,
then `wait_for_job(until='plan')`, read the plan (shots, warnings), `approve_job`, `wait_for_job(until='done')` (call
it again while it runs; renders take minutes per shot).

## 5. Review (every shot)
`review_job(id)` (8 shots per call; `shots=[9, 10, ...]` for the rest). Compare every column of every strip with the
source row (`KEY` = a pinned keyframe) and read the cut timing.
- **BAD**: on a main or large figure, a wrong identity (wrong character, two of the same, a face unlike its picture), not
  replaced or a leak (an original face or costume item), someone missing or added, a broken image (melted faces, extra
  limbs, smears), the source's light lost, a cut `dropped`, or a main cut 8+ frames off.
- **MINOR**: the same only on a small, edge or background figure, mild drift, or flash frames.
- **OK**: clean. Be strict: "a slightly weaker likeness" often hides a wrong identity.

## 6. Fix round (at most one per shot)
- A cut `late` 8+ frames, a `dropped` cut, or bad luck on a shot that has its keyframe: `redo_shot(id, shot)` (new seed).
- A cut `early` 8+ frames: another seed rarely moves it. Rewrite that shot's prompt to time the cut
  (`shot_prompt`, then `redo_shot(..., prompt=...)`).
- A shot without a keyframe that went wrong, or a character that drifts mid-shot: a keyframe there (step 3), then a new
  `create_job` with it pinned. `redo_shot` cannot add keyframes.
- A redo that came out worse: keep the better take in your notes and say so; do not loop.

## 7. Deliver
`download_result(id)`, then `save_result(id, {...})`:
```json
{"status": "done | partial | failed", "cast": {"woman in the red coat": "Vela"},
 "shots": [{"shot": 1, "grade": "OK|MINOR|BAD", "note": "..."}], "overall": "OK|MINOR|BAD",
 "keyframes": [0, 4.2, 9.1], "redone": {"3": "new seed"}, "image_edits": 5,
 "changed": "anything you changed vs the task and why", "problems": "what is still weak, by time range"}
```
`overall` = the worst grade among the final shots. Final message (80 words or fewer): the mp4 path, the overall grade,
image edits used, the biggest remaining problem, and any tool friction you hit.
