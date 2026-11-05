# Drive Henge from your own AI (MCP)

Henge has a built-in studio assistant (the chat in the studio), with a built-in planner VLM or an optional external provider. If you
would rather use the AI client you already have — Claude Code, Claude Desktop, Cursor, Codex, or any other
[MCP](https://modelcontextprotocol.io) client — connect it to Henge with the MCP server in
[`mcp/henge_mcp.py`](../mcp/henge_mcp.py). Your client then creates and follows generations with your own
subscription or local model; Henge needs no assistant key.

The MCP server only calls Henge's HTTP API (the UI address, port 8188), so it works with any backend Henge is
set to: your ComfyUI, the Comfy SDK or RunPod Serverless. It runs on the computer where your media files are;
Henge can be on the same machine or on a pod.

## Requirements

- Henge running and reachable (open `http://127.0.0.1:8188` in a browser to check).
- [`uv`](https://docs.astral.sh/uv/) — it installs the server's two dependencies (`mcp`, `requests`) by itself.
- `ffmpeg` and `ffprobe` on the PATH.

## Add it to your client

**Claude Code** (from the Henge folder):

```sh
claude mcp add henge -- uv run --script /path/to/Henge/mcp/henge_mcp.py
```

**Claude Desktop, Cursor and other clients** (`claude_desktop_config.json`, `.cursor/mcp.json`, …):

```json
{
  "mcpServers": {
    "henge": {
      "command": "uv",
      "args": ["run", "--script", "/path/to/Henge/mcp/henge_mcp.py"],
      "env": {"HENGE_URL": "http://127.0.0.1:8188"}
    }
  }
}
```

On Windows use a path like `C:/AI/Henge/mcp/henge_mcp.py`.

| Variable | Default | |
|---|---|---|
| `HENGE_URL` | `http://127.0.0.1:8188` | Henge's address, e.g. `https://<pod id>-8188.proxy.runpod.net` |
| `HENGE_PASSWORD` | — | the studio login, if one is turned on |
| `HENGE_MCP_OUT` | `./henge-results` | where `download_result` saves files |
| `HENGE_CHARS` | `~/.henge/chars` | the character library: `<Name>_photo.png`, `<Name>_sheet.png`, `lib_*.json` |

## Tools

| Tool | What it does |
|---|---|
| `status` | Live backend inventory, model/turbo/base/upscaler availability, temporal-window support and optional video-analysis readiness |
| `get_settings`, `set_settings` | Read or patch backend connection, assistant and Molmo configuration; stored credentials remain redacted |
| `view_frame` | Inspect a guide frame without Molmo or a GPU |
| `pointing_status` | Check optional Molmo availability before using its tools |
| `ask_video`, `point_video`, `match_people`, `suggest_cuts` | Optional Molmo video analysis, point proposals, matching and shot suggestions |
| `find_people` | Numbers the people (or animals) in one frame of a local video and shows the frame |
| `create_job` | Starts a generation from local files: mode, guide video, pictures, prompt, interval, quality, subjects, options; `first_frame` and `keyframes` (`[{time, image}]`, edited frames of the result pinned at their times) with the normal-map guide (`guide_normals`); `generate_audio` keeps the soundtrack H3 generates; `background` (a picture) puts a new background behind the people that follows the camera |
| `shot_plan` | How a render splits the interval: shots, camera cuts, and the cuts that still need a keyframe |
| `edit_frame` | Edits one guide frame (or an earlier edit) with an image editor (BFS Body Swap Selective, H3 Image, GPT Image, Qwen-Image, FIBO, FLUX Klein); `character` from `find_people(kind='character')` picks who is swapped; saves a PNG |
| `view_images` | Shows several local images at once, to check that every character looks the same in the first frame and all keyframes |
| `generate_image` | A new picture from a description with GPT Image (enabled with a key in the assistant settings) |
| `wait_for_job` | Waits until the plan is ready for review (`plan`) or the job finishes (`done`) |
| `get_job`, `list_jobs` | Status, stage, plan and errors |
| `approve_job`, `cancel_job`, `retry_job` | Act on a job |
| `review_job` | Per shot, the source frames over the same frames of the result (KEY marks a pinned keyframe), and where the result's camera cuts land against the source's (on time, early/late by n frames, dropped, extra) |
| `redo_shot`, `shot_prompt` | Render one shot of a finished job again (new seed, or a rewritten shot prompt) / read that prompt |
| `characters` | The character library (`HENGE_CHARS`): descriptions, outfits, photos and sheets; `lib:Name` works as a picture path |
| `download_result` | Saves the result, the side-by-side comparison or the full bundle (with the exact ComfyUI graphs) |
| `save_result` | Writes `<reference>_result.json` with the agent's verdict: a grade per shot, keyframes, redos and remaining problems |

Jobs also appear in the web UI's history, so you can follow them there too.

## Example

> Using Henge, swap the woman on the left in `~/clips/dance.mp4` (seconds 2 to 8) for `~/refs/robot.png`
> at 480p. Show me the plan before rendering.

The client calls `find_people` at 2 s, picks the person on the left, calls `create_job` with
`mode: "swap"`, the picture and `subjects: [{"picture_slots": [1], "x": …, "y": …, "time": 2}]`, waits for the
plan, shows it to you, then `approve_job`, `wait_for_job` and `download_result`.

More examples you can ask for:

> Make the woman in `~/clips/rooftop.mp4` perform as `~/refs/dancer.png`, on the beach in `~/refs/beach.jpg`
> (new background), with generated audio.

> Sharpen `~/out/swap.mp4` to 1080p.

The modes:

- `swap` (Character Swap): people in the guide become the pictures. 1–11 pictures.
- `motion` (Motion Transfer): the pictures perform the guide's motion. 1–11 pictures.
- `headswap`: exactly one face picture.
- `sharpness`: the video only; restores detail and can upscale to 1440p/2160p.

## A whole remake, unattended

[`mcp/AGENTS.md`](../mcp/AGENTS.md) holds the rules an agent follows to remake a clip end to end: read the clip, cast,
a keyframe after every camera cut with a consistency check, render, `review_job` every shot with a strict grade, one fix
round, `save_result`. [`mcp/examples/`](../mcp/examples/README.md) has the client configs, task examples and
`run_claude.sh`, which runs a task with Claude Code and those rules in one command.

## Keyframes

Character Swap and Motion Transfer can pin edited frames of the result anywhere in the clip, not only the first frame:

1. `shot_plan(video)`: the shots and camera cuts; `cuts_without_keyframe` lists where a keyframe helps most (a shot that
   opens on a cut has nothing else to start from).
2. For each time: `find_people(video, t, kind='character')`, then `edit_frame(video=..., time=t, op='swap', character=n,
   pictures=[...], editor='bfs_selective')` (or `'gpt_image'` when it is enabled).
3. `view_images([...])` with the first frame and every keyframe: check that each character looks the same in all of them.
4. `create_job(..., first_frame=..., keyframes=[{"time": t, "image": path}, ...])`.

## Configuration and defaults

Read `status` before choosing features. `temporal_windows_ready` is the worker's reported support, not a promise
that any combination is valid. Temporal windows default to disabled and cannot be combined with Causal or regional
attention. The `refiner_full` scope additionally needs Sharpness, Open-H3 Refiner and 1080p or 2K output.

`create_job.options` passes all backend generation settings through to the normal API validator, including model
profile, Guide Latents/TARA, turbo, seed, attention, mask settings, regional attention, temporal windows and
Sharpness/refiner options. Use `upscale_method`, not `upscale`. Additional arguments expose `guide_representation`,
`mark_opacity`, `processing`, `audio_conditioning` and `first_frame_slot`.

Character Swap with an edited `first_frame` uses the **normal-map guide** by default (`guide_normals=true`): the guide becomes
a MoGe-2 surface-normal map, so it carries only shapes, poses, motion and camera, and the look of every person and of the
place comes from the edited frame, which goes in as a reference and as the keyframe at frame 0. It is the recommended way
to swap several people (swap each of them in the first frame, e.g. with the BFS Body Swap Selective editor) or to change
the background (edit it in the frame too). Pass `guide_normals=false` for the plain guide and `first_frame_mode`.

Use `guide_representation="original"` by default, including vehicles and objects. Masking is an explicit choice
that requires subject anchors bound to reference pictures. Do not choose it automatically for an ordinary
replacement request. With Original, unchanged background pixels are not guaranteed. A requested mask must not be
silently removed to get past validation.

Molmo is optional. Check `pointing_status` first; if unavailable, inspect `view_frame` at several times and use
your client's vision. `find_people` detects people or animals, not vehicles. Molmo configuration is not required
for ordinary generation.

`get_settings(section="all")` reads the `connection`, `assistant` and `molmo` sections. To change a section, call
`set_settings(section=..., settings={...})`. Existing backend validation, environment locks and active-job
connection protection still apply; stored API keys are not returned. These are persistent bridge settings.
Generation options passed to `create_job` apply to that job. The MCP server does not edit another browser's local
draft, theme or language; the built-in assistant uses the live studio tools to change those generation controls.

When updating Henge features, update both the assistant tool instructions and MCP documentation. Assistant
`get_options` reads current UI generation values and capabilities; nested option patches preserve other values
and unknown top-level keys are rejected. Optional Molmo tools are exposed to the built-in assistant only when
configured, and stale unavailable tool calls are rejected before reaching the browser.

## Choosing a replacement mode

For multiple replacements, recommend Motion Transfer TARA: its LoRA was trained for multiple people, objects and
vehicles. Use `mode="motion"`, `options.profile="motion_tara"` and `options.conditioning_mode="tara"` together. Character Swap may work as an alternative only when all replaced subjects are people. Inspect frames
and references before deciding which alternatives apply.

The built-in studio assistant uses `choose_replacement_mode` to show an in-chat choice card when the current
request does not explicitly choose a mode. It waits for a click, applies that mode (including the TARA profile and method for Motion Transfer TARA), and stops the edit if cancelled.
The external MCP client asks the same question in its own conversation before `create_job`; the MCP server does
not open the browser's choice card. Respect a mode already explicitly chosen for that request.

## Pika turbo and sampler options

`status.samplers` lists supported H3 sampler choices. `sampler_name="auto"` preserves the default Euler behavior
for existing turbos and chooses LCM for `turbo="pika6"`. The Pika preset is six steps, CFG 1 and the H3 Ref2VA base.
At six steps, manual sigmas match the Comfy workflow; a different step count uses the model's normal scheduler.
An explicit sampler override changes the sampler without replacing the six-step sigmas. Open-H3 stage-2 sampling
remains independent. Pika is downloaded by default, but must be installed and reported by the worker to be usable.
See [Pika integration](pika-h3-flex.md).

## Model installs and version status

- `get_models`: public catalog, installed files and installation progress, without waking a worker.
- `install_model(model_id)`: explicitly install a catalogued file on local ComfyUI or the existing worker volume.
- `cancel_model_installation`: stop an install and keep its partial data for retry.
- `refresh_worker_inventory`: explicitly wake the worker to report capabilities/files; Serverless GPU time is billed.
- `get_updates`: running version, GitHub changelog and code-update availability, without updating anything.

Installations are blocked during active generation. A newly installed file is not a code or node update.
See [model and update controls](models-and-updates.md).
