"""Node reports that also reach Comfy API v2 clients (Comfy SDK through comfy-api-proxy or Comfy Cloud).

API v2 lists only file outputs (images, gifs, audio, files...), so a node's custom ui keys (text, henge_tracks,
henge_look) would be lost there. ui_report() keeps the ui dict as it was for /history readers and also writes it to a
small `<id>.henge-ui.json` output file, which the bridge's Comfy SDK backend downloads and merges back."""
import json
import uuid
from pathlib import Path


def ui_report(ui: dict) -> dict:
    import folder_paths
    folder = Path(folder_paths.get_output_directory()) / 'henge_ui'
    folder.mkdir(parents=True, exist_ok=True)
    name = f'{uuid.uuid4().hex}.henge-ui.json'
    (folder / name).write_text(json.dumps(ui))
    return {**ui, 'files': [{'filename': name, 'subfolder': 'henge_ui', 'type': 'output'}]}
