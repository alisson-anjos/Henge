# Henge agent examples

An AI client (Claude Code, codex or any MCP client) can remake a clip end to end through the [Henge MCP](../../docs/MCP.md):
it reads the clip, casts the characters, makes and checks a keyframe after every camera cut, renders, reviews every
shot against the source, redoes what is worth redoing and writes a `result.json` with a grade per shot. The rules it
follows are in [`../AGENTS.md`](../AGENTS.md).

| file | what it is |
|---|---|
| `claude_mcp.json` | the server entry for Claude Code (`.mcp.json` in a project) or Claude Desktop; replace `/path/to/Henge` |
| `codex_config.toml` | the same for codex (`$CODEX_HOME/config.toml`) |
| `run_claude.sh` | runs a task unattended with Claude Code: the MCP, the rules and the task, nothing to set up by hand |
| `two-cut-swap/task.txt` | one person swapped across camera cuts, from a picture |
| `two-cut-swap/library-task.txt` | two people swapped with library characters |

## Run one

Start Henge (the studio on `http://127.0.0.1:8188`), then, from the Henge folder:

```bash
mcp/examples/run_claude.sh mcp/examples/two-cut-swap/task.txt ~/clips/street.mp4 ~/refs/character.png
```

In a task, `@SRC@` stands for the clip and `@PICTURE1@`, `@PICTURE2@`… for the pictures after it. The result, the
downloaded video and `<reference>_result.json` land in `./henge-results` (`HENGE_MCP_OUT`). The job also appears in the
studio's history, where you can open the comparison and redo shots by hand.

Interactively, add the server once (`claude mcp add henge -- uv run --script /path/to/Henge/mcp/henge_mcp.py`), put
`@/path/to/Henge/mcp/AGENTS.md` in your project's `CLAUDE.md`, start Claude Code with `MCP_TOOL_TIMEOUT=2000000` (a
`wait_for_job` call blocks for up to 30 minutes) and ask, for example:

> Swap the woman in the red coat in `~/clips/street.mp4` (0-12 s) for Vela from the library. Budget: 6 image edits.

The studio's own assistant follows the same steps (keyframes after cuts, a consistency check, `review_job` and a
grade per shot) without any of this: ask it in the studio chat.

## The character library

`HENGE_CHARS` (default `~/.henge/chars`) holds characters you reuse:

- `<Name>_photo.png`: an identity photo; `<Name>_sheet.png`: an optional character sheet (front, side, back, whole outfit);
- `lib_*.json`: `{"chars": {"Name": "who: age, build, hair, face"}, "outfits": {"Name": "the whole outfit, down to the shoes"}}`.

`characters()` lists them; a picture written `lib:Name` is the character's sheet (else its photo), and
`lib:Name/photo` / `lib:Name/sheet` pick one.

## What a run returns

`save_result` writes, next to the video:

```json
{"job": "…", "reference": "a1b2c3d4", "mode": "swap", "seconds": 12.0, "final": "/…/henge-results/a1b2c3d4.mp4",
 "status": "done", "cast": {"woman in the red coat": "Vela"},
 "shots": [{"shot": 1, "grade": "OK", "note": "clean"}, {"shot": 2, "grade": "MINOR", "note": "6.1-6.8 s: hair drifts lighter"}],
 "overall": "MINOR", "keyframes": [0, 4.2], "redone": {"2": "new seed"}, "image_edits": 3,
 "changed": "", "problems": "6.1-6.8 s: hair drifts lighter on the turn"}
```
