# Drive Henge from your own AI (MCP)

Henge has a built-in studio assistant (the chat in the studio) that needs an API key in its settings. If you
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

## Tools

| Tool | What it does |
|---|---|
| `status` | Online or not, the backend in use, installed models, turbos and upscalers |
| `find_people` | Numbers the people (or animals) in one frame of a local video and shows the frame |
| `create_job` | Starts a generation from local files: mode, guide video, pictures, prompt, interval, quality, subjects, options |
| `wait_for_job` | Waits until the plan is ready for review (`plan`) or the job finishes (`done`) |
| `get_job`, `list_jobs` | Status, stage, plan and errors |
| `approve_job`, `cancel_job`, `retry_job` | Act on a job |
| `download_result` | Saves the result, the side-by-side comparison or the full bundle (with the exact ComfyUI graphs) |

Jobs also appear in the web UI's history, so you can follow them there too.

## Example

> Using Henge, swap the woman on the left in `~/clips/dance.mp4` (seconds 2 to 8) for `~/refs/robot.png`
> at 480p. Show me the plan before rendering.

The client calls `find_people` at 2 s, picks the person on the left, calls `create_job` with
`mode: "swap"`, the picture and `subjects: [{"picture_slots": [1], "x": …, "y": …, "time": 2}]`, waits for the
plan, shows it to you, then `approve_job`, `wait_for_job` and `download_result`.

The modes:

- `swap` (Character Swap): people in the guide become the pictures. 1–11 pictures.
- `motion` (Motion Transfer): the pictures perform the guide's motion. 1–11 pictures.
- `headswap`: exactly one face picture.
- `sharpness`: the video only; restores detail and can upscale to 1440p/2160p.
